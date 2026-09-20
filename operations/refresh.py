"""Canonical incremental Source-to-Product refresh command.

This module is intentionally an application-level coordinator. It reuses the
existing collector, Analysis, resolution, intelligence, signal, event,
priority, feed, lifecycle, and Product services without duplicating their
semantic rules.
"""

from __future__ import annotations

import argparse
import asyncio
import inspect
import json
import time
from collections import Counter
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, or_, select

from ai import (
    OpenAICompatibleThesisComparator,
    OpenAIOpinionExtractor,
    OpinionProcessingService,
)
from collectors.xueqiu import (
    AuthenticationRequired,
    BrowserDependencyMissing,
    CdpNotAvailable,
    ManualVerificationRequired,
    NavigationFailed,
    NetworkUnavailable,
    NoContent,
    ParseFailed,
    PlaywrightXueqiuBrowser,
    RateLimitedOrBlocked,
    XueqiuCollectorError,
    XueqiuFeedAdapter,
)
from collectors.xueqiu.smoke import browser_config
from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
)
from contracts import (
    CollectionCoverageStatus,
    CollectionMode,
    CollectionRunCreate,
    CollectionRunStatus,
    CollectionTransport,
    EventAnalysisStatus,
    FeedCollectionRequest,
    OperationalRefreshRunCreate,
    OperationalRefreshStatus,
    OperationalRefreshTrigger,
)
from contracts.collection_provenance import utc_now
from database.models import (
    Asset,
    AttentionOccurrence,
    CollectionObservation,
    CollectionRun,
    CrossInvestorAssetAlignment,
    CrossInvestorAssetSnapshot,
    CrossInvestorConsensusEvidence,
    EventAnalysis,
    IntelligenceEvent,
    IntelligenceEventEvidence,
    IntelligenceEventPriority,
    IntelligenceFeedItem,
    Investor,
    OperationalRefreshRun,
    Opinion,
    RawEvent,
    Signal,
    ThesisChange,
)
from database.repositories import (
    CollectionObservationRepository,
    CollectionRunRepository,
    OperationalRefreshRunRepository,
)
from database.session import SessionFactory
from database.unit_of_work import (
    SqlAlchemyAttentionUnitOfWork,
    SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork,
    SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork,
    SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
    SqlAlchemyThesisChangeUnitOfWork,
)
from ingestion import FeedIngestionService
from intelligence import (
    AttentionOccurrenceService,
    CrossInvestorAssetAlignmentService,
    CrossInvestorAssetSnapshotService,
    CrossInvestorConsensusEvidenceService,
    StateUpdateService,
    ThesisChangeService,
)
from intelligence.events import IntelligenceEventAggregator
from intelligence.feed import IntelligenceFeedService
from intelligence.feed.lifecycle import FeedLifecycleService
from intelligence.investor_product import InvestorIntelligenceProductService
from intelligence.priority import IntelligencePriorityService
from intelligence.product import AssetIntelligenceProductService
from operations.locking import OperationalRefreshLock
from pipeline import AnalysisBackfillRunner, AnalysisRecoveryCandidate, AnalysisRecoveryProgress
from resolution import AssetRecoveryService
from signal_engine import SignalGenerator


class RefreshStage(StrEnum):
    COLLECTION = "COLLECTION"
    ANALYSIS = "ANALYSIS"
    RESOLUTION = "RESOLUTION"
    DOMAIN_STATE = "DOMAIN_STATE"
    CROSS_INVESTOR = "CROSS_INVESTOR"
    SIGNALS = "SIGNALS"
    EVENTS = "INTELLIGENCE_EVENTS"
    PRIORITY = "PRIORITY"
    FEED = "FEED"
    FEED_LIFECYCLE = "FEED_LIFECYCLE"
    PRODUCT_VERIFICATION = "PRODUCT_VERIFICATION"


class RefreshStageError(RuntimeError):
    """A hard failure at a known operational stage."""

    def __init__(self, stage: RefreshStage, code: str, message: str) -> None:
        super().__init__(message)
        self.stage = stage
        self.code = code


@dataclass(frozen=True, slots=True)
class CollectionStageResult:
    run_id: UUID | None
    observed_event_ids: tuple[UUID, ...] = ()
    new_event_ids: tuple[UUID, ...] = ()
    new_events: int = 0
    existing_events: int = 0
    received_items: int = 0
    stop_reason: str | None = None


@dataclass
class _OperationalExecution:
    session: Any
    lock: OperationalRefreshLock
    run_id: UUID


@dataclass
class RefreshSummary:
    """JSON-safe operational result printed by the canonical command."""

    started_at: datetime
    result: str = "FAILED"
    finished_at: datetime | None = None
    stages: dict[str, dict[str, object]] = field(default_factory=dict)
    counts: dict[str, object] = field(default_factory=dict)
    database_before: dict[str, int] = field(default_factory=dict)
    database_after: dict[str, int] = field(default_factory=dict)
    errors: list[dict[str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, object]:
        return {
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "result": self.result,
            "stages": self.stages,
            "counts": self.counts,
            "database_before": self.database_before,
            "database_after": self.database_after,
            "errors": self.errors,
            "warnings": self.warnings,
        }


_COUNT_MODELS = {
    "assets": Asset,
    "investors": Investor,
    "collection_runs": CollectionRun,
    "collection_observations": CollectionObservation,
    "operational_refresh_runs": OperationalRefreshRun,
    "raw_events": RawEvent,
    "event_analyses": EventAnalysis,
    "opinions": Opinion,
    "attention_occurrences": AttentionOccurrence,
    "thesis_changes": ThesisChange,
    "cross_investor_snapshots": CrossInvestorAssetSnapshot,
    "cross_investor_alignments": CrossInvestorAssetAlignment,
    "cross_investor_consensus": CrossInvestorConsensusEvidence,
    "signals": Signal,
    "intelligence_events": IntelligenceEvent,
    "intelligence_event_evidence": IntelligenceEventEvidence,
    "priorities": IntelligenceEventPriority,
    "feed_items": IntelligenceFeedItem,
}

_HARD_ANALYSIS_CODES = {
    "AUTHENTICATION_ERROR",
    "CONFIGURATION_ERROR",
    "UNSUPPORTED_CAPABILITY",
}


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _enum_value(value: object) -> object:
    return getattr(value, "value", value)


def _safe_message(error: Exception) -> str:
    message = str(error).replace("\r", " ").replace("\n", " ").strip()
    for secret in ("LLM_API_KEY", "XUEQIU_STORAGE_STATE_PATH", "DATABASE_URL"):
        message = message.replace(secret, "<redacted-setting>")
    return message[:500]


def _failure_code(error: Exception) -> str:
    value = getattr(error, "code", None) or getattr(error, "error_code", None)
    value = _enum_value(value)
    return str(value or type(error).__name__)


def _collection_failure(error: Exception) -> tuple[str, bool]:
    if isinstance(error, AuthenticationRequired):
        return "COLLECTION_AUTH_REQUIRED", True
    if isinstance(error, (RateLimitedOrBlocked, ManualVerificationRequired)):
        return "COLLECTION_RISK_CONTROLLED", True
    if isinstance(error, CdpNotAvailable):
        return "CDP_UNAVAILABLE", True
    if isinstance(error, (NetworkUnavailable, NavigationFailed)):
        return "COLLECTION_NETWORK_FAILURE", True
    if isinstance(error, (ParseFailed, BrowserDependencyMissing)):
        return "COLLECTION_PARSER_FAILURE", True
    if isinstance(error, NoContent):
        return "SOURCE_NO_OP", False
    if isinstance(error, XueqiuCollectorError):
        return "COLLECTION_FAILED", True
    return "COLLECTION_FAILED", True


class OperationalRefreshService:
    """Coordinate one bounded, database-driven refresh through Product."""

    def __init__(
        self,
        session_factory: Callable[[], Any] = SessionFactory,
        *,
        stage_observer: Callable[[RefreshStage], None] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._stage_observer = stage_observer

    async def run(
        self,
        *,
        max_batches: int = 1,
        since: datetime | None = None,
        until: datetime | None = None,
        only_author_ids: Iterable[str] = (),
        headless: bool = False,
        cdp_endpoint: str | None = None,
        skip_collection: bool = False,
        raw_event_ids: Iterable[UUID] = (),
        batch_size: int = 10,
        analysis_concurrency: int = 4,
        attention_concurrency: int = 4,
        trigger: OperationalRefreshTrigger = OperationalRefreshTrigger.MANUAL,
        require_cdp: bool = False,
    ) -> RefreshSummary:
        normalized_trigger = OperationalRefreshTrigger(trigger)
        execution = self._begin_execution(normalized_trigger)
        started_at = utc_now()
        summary = RefreshSummary(started_at=started_at)
        if execution is None:
            summary.result = OperationalRefreshStatus.SKIPPED_ALREADY_RUNNING.value
            summary.finished_at = started_at
            summary.database_before = self._database_counts()
            summary.database_after = summary.database_before
            summary.warnings.append("Another refresh is already running.")
            summary.counts["operational_run_status"] = (
                OperationalRefreshStatus.SKIPPED_ALREADY_RUNNING.value
            )
            return summary

        summary.counts["operational_run_id"] = str(execution.run_id)
        if require_cdp and not cdp_endpoint:
            summary.database_before = self._database_counts()
            summary.errors.append(
                {
                    "stage": RefreshStage.COLLECTION.value,
                    "code": "CDP_UNAVAILABLE",
                    "message": "An authenticated CDP endpoint is required for scheduled refresh.",
                }
            )
            summary.result = OperationalRefreshStatus.FAILED.value
            summary.finished_at = utc_now()
            summary.database_after = self._database_counts()
            self._finish_execution(execution, summary)
            return summary
        partial_failure = False
        collection: CollectionStageResult | None = None
        target_event_ids: tuple[UUID, ...] = ()
        affected_assets: set[UUID] = set()
        affected_investors: set[UUID] = set()

        try:
            summary.database_before = self._database_counts()
            collection = await self._execute_stage(
                summary,
                RefreshStage.COLLECTION,
                lambda: (
                    self._skip_collection(raw_event_ids)
                    if skip_collection
                    else self._collect(
                        max_batches=max_batches,
                        since=since,
                        until=until,
                        only_author_ids=tuple(only_author_ids),
                        headless=headless,
                        cdp_endpoint=cdp_endpoint,
                    )
                ),
            )
            target_event_ids = collection.observed_event_ids
            affected_investors.update(self._investor_ids_for_events(target_event_ids))
            summary.counts["collection"] = self._collection_dict(collection)

            analysis = await self._execute_stage(
                summary,
                RefreshStage.ANALYSIS,
                lambda: self._analyze(
                    target_event_ids,
                    batch_size=batch_size,
                    concurrency=analysis_concurrency,
                ),
            )
            partial_failure |= bool(analysis["partial"])
            summary.counts["analysis"] = analysis["counts"]

            resolution = await self._execute_stage(
                summary,
                RefreshStage.RESOLUTION,
                lambda: self._materialize_resolution(
                    target_event_ids,
                    batch_size=batch_size,
                ),
            )
            partial_failure |= bool(resolution["partial"])
            summary.counts["resolution"] = resolution["counts"]

            domain = await self._execute_stage(
                summary,
                RefreshStage.DOMAIN_STATE,
                lambda: self._derive_domain(
                    target_event_ids,
                    attention_concurrency=attention_concurrency,
                ),
            )
            partial_failure |= bool(domain["partial"])
            affected_assets.update(domain["affected_assets"])
            affected_investors.update(domain["affected_investors"])
            summary.counts["domain_state"] = domain["counts"]

            cross_investor = await self._execute_stage(
                summary,
                RefreshStage.CROSS_INVESTOR,
                lambda: self._derive_cross_investor(affected_assets),
            )
            partial_failure |= bool(cross_investor["partial"])
            affected_assets.update(cross_investor["affected_assets"])
            summary.counts["cross_investor"] = cross_investor["counts"]

            signals = await self._execute_stage(
                summary,
                RefreshStage.SIGNALS,
                lambda: self._generate_signals(affected_assets),
            )
            summary.counts["signals"] = signals

            events = await self._execute_stage(
                summary,
                RefreshStage.EVENTS,
                lambda: self._aggregate_events(affected_assets),
            )
            summary.counts["events"] = events

            event_ids = tuple(UUID(value) for value in events["event_ids"])
            priorities = await self._execute_stage(
                summary,
                RefreshStage.PRIORITY,
                lambda: self._materialize_priorities(event_ids),
            )
            summary.counts["priorities"] = priorities

            priority_ids = tuple(UUID(value) for value in priorities["priority_ids"])
            feed = await self._execute_stage(
                summary,
                RefreshStage.FEED,
                lambda: self._materialize_feed(priority_ids),
            )
            summary.counts["feed"] = feed

            lifecycle = await self._execute_stage(
                summary,
                RefreshStage.FEED_LIFECYCLE,
                self._apply_feed_lifecycle,
            )
            summary.counts["feed_lifecycle"] = lifecycle

            product = await self._execute_stage(
                summary,
                RefreshStage.PRODUCT_VERIFICATION,
                lambda: self._verify_product(
                    affected_assets,
                    affected_investors,
                ),
            )
            partial_failure |= bool(product["partial"])
            summary.counts["product"] = product
        except RefreshStageError as exc:
            summary.errors.append(
                {
                    "stage": exc.stage.value,
                    "code": exc.code,
                    "message": _safe_message(exc),
                }
            )
            summary.result = "FAILED"
        else:
            summary.result = "PARTIAL_FAILURE" if partial_failure else "SUCCESS"
        finally:
            summary.finished_at = utc_now()
            summary.database_after = self._database_counts()
            summary.counts["affected_assets"] = sorted(str(value) for value in affected_assets)
            summary.counts["affected_investors"] = sorted(
                str(value) for value in affected_investors
            )
            summary.counts["llm_requests"] = self._llm_request_counts()
            self._finish_execution(execution, summary)
        return summary

    def _begin_execution(
        self,
        trigger: OperationalRefreshTrigger,
    ) -> _OperationalExecution | None:
        session = self._session_factory()
        lock = OperationalRefreshLock(session)
        if not lock.try_acquire():
            session.close()
            with self._session_factory() as skipped_session:
                OperationalRefreshRunRepository(skipped_session).create_skipped(
                    trigger=trigger,
                    started_at=utc_now(),
                    summary_json={"reason": "SKIPPED_ALREADY_RUNNING"},
                )
                skipped_session.commit()
            return None
        try:
            run = OperationalRefreshRunRepository(session).create_run(
                OperationalRefreshRunCreate(
                    trigger=trigger,
                    started_at=utc_now(),
                )
            )
            session.commit()
            return _OperationalExecution(session=session, lock=lock, run_id=run.id)
        except Exception:
            lock.release()
            session.close()
            raise

    def _finish_execution(
        self,
        execution: _OperationalExecution,
        summary: RefreshSummary,
    ) -> None:
        status = OperationalRefreshStatus(summary.result)
        failure_stage = None
        failure_code = None
        if summary.errors:
            failure_stage = summary.errors[0].get("stage")
            failure_code = summary.errors[0].get("code")
        elif status is OperationalRefreshStatus.PARTIAL_FAILURE:
            partial_stages = [
                stage for stage, value in summary.stages.items() if value.get("status") == "PARTIAL"
            ]
            failure_stage = partial_stages[0] if partial_stages else None
            failure_code = "PARTIAL_FAILURE"
        try:
            OperationalRefreshRunRepository(execution.session).finish_run(
                execution.run_id,
                finished_at=summary.finished_at or utc_now(),
                status=status,
                failure_stage=failure_stage,
                failure_code=failure_code,
                summary_json=summary.as_dict(),
            )
            execution.session.commit()
        finally:
            execution.lock.release()
            execution.session.close()

    async def _execute_stage(
        self,
        summary: RefreshSummary,
        stage: RefreshStage,
        operation: Callable[[], object],
    ) -> Any:
        if self._stage_observer is not None:
            self._stage_observer(stage)
        started = time.perf_counter()
        try:
            value = operation()
            if inspect.isawaitable(value):
                value = await value
        except RefreshStageError as exc:
            summary.stages[stage.value] = {
                "status": "FAILED",
                "duration_seconds": round(time.perf_counter() - started, 6),
                "error": {
                    "code": exc.code,
                    "type": type(exc).__name__,
                    "message": _safe_message(exc),
                },
            }
            raise
        except Exception as exc:
            summary.stages[stage.value] = {
                "status": "FAILED",
                "duration_seconds": round(time.perf_counter() - started, 6),
                "error": {
                    "code": _failure_code(exc),
                    "type": type(exc).__name__,
                    "message": _safe_message(exc),
                },
            }
            raise RefreshStageError(stage, "STAGE_FAILED", _safe_message(exc)) from exc
        summary.stages[stage.value] = {
            "status": "SUCCESS",
            "duration_seconds": round(time.perf_counter() - started, 6),
        }
        if isinstance(value, Mapping) and value.get("partial"):
            summary.stages[stage.value]["status"] = "PARTIAL"
        return value

    def _database_counts(self) -> dict[str, int]:
        with self._session_factory() as session:
            return {
                name: int(session.scalar(select(func.count()).select_from(model)) or 0)
                for name, model in _COUNT_MODELS.items()
            }

    def _investor_ids_for_events(self, event_ids: Sequence[UUID]) -> set[UUID]:
        if not event_ids:
            return set()
        with self._session_factory() as session:
            return set(
                session.scalars(select(RawEvent.investor_id).where(RawEvent.id.in_(event_ids)))
            )

    def _llm_request_counts(self) -> dict[str, int]:
        extractor = getattr(self, "_opinion_extractor", None)
        comparator = getattr(self, "_thesis_comparator", None)
        return {
            "opinion_analysis": int(getattr(extractor, "request_count", 0)),
            "opinion_retries": int(getattr(extractor, "retry_count", 0)),
            "thesis_comparison": int(getattr(comparator, "request_count", 0)),
            "thesis_retries": int(getattr(comparator, "retry_count", 0)),
        }

    @staticmethod
    def _collection_dict(result: CollectionStageResult) -> dict[str, object]:
        return {
            "run_id": str(result.run_id) if result.run_id else None,
            "received_items": result.received_items,
            "new_events": result.new_events,
            "existing_events": result.existing_events,
            "observed_event_ids": [str(value) for value in result.observed_event_ids],
            "new_event_ids": [str(value) for value in result.new_event_ids],
            "stop_reason": result.stop_reason,
        }

    @staticmethod
    def _skip_collection(raw_event_ids: Iterable[UUID]) -> CollectionStageResult:
        ids = tuple(dict.fromkeys(raw_event_ids))
        if not ids:
            raise RefreshStageError(
                RefreshStage.COLLECTION,
                "SKIP_COLLECTION_REQUIRES_RAW_EVENT_ID",
                "--skip-collection requires at least one --raw-event-id",
            )
        return CollectionStageResult(
            run_id=None,
            observed_event_ids=ids,
            new_event_ids=(),
            stop_reason="SKIPPED_COLLECTION",
        )

    async def _collect(
        self,
        *,
        max_batches: int,
        since: datetime | None,
        until: datetime | None,
        only_author_ids: tuple[str, ...],
        headless: bool,
        cdp_endpoint: str | None,
    ) -> CollectionStageResult:
        request = FeedCollectionRequest(
            max_batches=max_batches,
            since=since,
            until=until,
            only_author_ids=only_author_ids,
        )
        transport = (
            CollectionTransport.BROWSER_CDP if cdp_endpoint else CollectionTransport.BROWSER_SESSION
        )
        with self._session_factory() as session:
            run = CollectionRunRepository(session).create_run(
                CollectionRunCreate(
                    source="xueqiu",
                    adapter_name="xueqiu_following_feed",
                    collection_mode=CollectionMode.FEED,
                    transport=transport,
                    started_at=utc_now(),
                    coverage_status=CollectionCoverageStatus.UNKNOWN,
                    requested_window_start=since,
                    requested_window_end=until,
                    scope_type="FOLLOWING_FEED",
                    parameters_json={
                        "max_batches": max_batches,
                        "only_author_ids": list(only_author_ids),
                    },
                )
            )
            session.commit()
            run_id = run.id

        browser = PlaywrightXueqiuBrowser(
            browser_config(headless=headless, cdp_endpoint=cdp_endpoint)
        )
        try:
            batches = await browser.fetch_following_feed_batches(request)
            items = [
                item async for item in XueqiuFeedAdapter(browser).collect_batches(batches, request)
            ]
        except Exception as exc:
            code, hard_failure = _collection_failure(exc)
            if code == "SOURCE_NO_OP":
                self._close_collection_run(
                    run_id,
                    status=CollectionRunStatus.COMPLETED,
                    stop_reason=code,
                    summary_json={"received_items": 0, "new_events": 0, "existing_events": 0},
                )
                return CollectionStageResult(
                    run_id=run_id,
                    stop_reason=code,
                )
            self._close_collection_run(
                run_id,
                status=(
                    CollectionRunStatus.ABORTED
                    if code in {"COLLECTION_AUTH_REQUIRED", "COLLECTION_RISK_CONTROLLED"}
                    else CollectionRunStatus.FAILED
                ),
                stop_reason=code,
            )
            if hard_failure:
                raise RefreshStageError(
                    RefreshStage.COLLECTION,
                    code,
                    _safe_message(exc),
                ) from exc
            raise

        stop_reason = browser.last_following_stop_reason or (
            "MAX_BATCHES" if len(batches) >= max_batches else "NO_PROGRESS"
        )
        try:
            with self._session_factory() as session:
                ingestion = await FeedIngestionService(
                    session,
                    collection_observation_repository=CollectionObservationRepository(session),
                    collection_run_id=run_id,
                ).ingest(items)
                self._close_collection_run(
                    run_id,
                    status=(
                        CollectionRunStatus.ABORTED
                        if stop_reason in {"RISK_CONTROL", "AUTH_REQUIRED", "MANUAL_STOP"}
                        else CollectionRunStatus.COMPLETED
                    ),
                    stop_reason=stop_reason,
                    summary_json={
                        "received_items": len(items),
                        "new_events": ingestion.inserted_event_count,
                        "existing_events": ingestion.duplicate_event_count,
                    },
                    session=session,
                )
                session.commit()
        except Exception as exc:
            self._close_collection_run(
                run_id,
                status=CollectionRunStatus.FAILED,
                stop_reason="COLLECTION_INGESTION_FAILED",
            )
            raise RefreshStageError(
                RefreshStage.COLLECTION,
                "COLLECTION_INGESTION_FAILED",
                _safe_message(exc),
            ) from exc

        observed_ids = tuple(dict.fromkeys(ingestion.event_ids))
        new_ids = tuple(result.event_id for result in ingestion.event_results if result.created)
        return CollectionStageResult(
            run_id=run_id,
            observed_event_ids=observed_ids,
            new_event_ids=tuple(dict.fromkeys(new_ids)),
            new_events=ingestion.inserted_event_count,
            existing_events=ingestion.duplicate_event_count,
            received_items=len(items),
            stop_reason=stop_reason,
        )

    def _close_collection_run(
        self,
        run_id: UUID,
        *,
        status: CollectionRunStatus,
        stop_reason: str,
        summary_json: dict[str, object] | None = None,
        session: Any | None = None,
    ) -> None:
        owns_session = session is None
        active_session = session or self._session_factory()
        try:
            repository = CollectionRunRepository(active_session)
            if status is CollectionRunStatus.COMPLETED:
                repository.finish_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=stop_reason,
                    summary_json=summary_json,
                )
            elif status is CollectionRunStatus.ABORTED:
                repository.abort_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=stop_reason,
                    summary_json=summary_json,
                )
            else:
                repository.fail_run(
                    run_id,
                    ended_at=utc_now(),
                    stop_reason=stop_reason,
                    summary_json=summary_json,
                )
            if owns_session:
                active_session.commit()
        finally:
            if owns_session:
                active_session.close()

    def _analysis_candidates(
        self,
        event_ids: Sequence[UUID],
        analysis_version: str,
    ) -> tuple[AnalysisRecoveryCandidate, ...]:
        if not event_ids:
            return ()
        with self._session_factory() as session:
            statement = (
                select(RawEvent.id, EventAnalysis.status)
                .outerjoin(
                    EventAnalysis,
                    and_(
                        EventAnalysis.event_id == RawEvent.id,
                        EventAnalysis.analysis_version == analysis_version,
                    ),
                )
                .where(RawEvent.id.in_(event_ids))
                .order_by(RawEvent.published_time, RawEvent.id)
            )
            return tuple(
                AnalysisRecoveryCandidate(event_id=event_id, status=status)
                for event_id, status in session.execute(statement)
            )

    async def _analyze(
        self,
        event_ids: Sequence[UUID],
        *,
        batch_size: int,
        concurrency: int,
    ) -> dict[str, object]:
        policy = get_production_analysis_policy()
        candidates = self._analysis_candidates(event_ids, policy.active_analysis_version)
        missing = tuple(item for item in candidates if item.status is None)
        existing_failed = sum(item.status is EventAnalysisStatus.FAILED for item in candidates)
        if not missing:
            analysis_ids = self._active_analysis_ids(event_ids, policy.active_analysis_version)
            return {
                "partial": bool(existing_failed),
                "analysis_ids": analysis_ids,
                "counts": {
                    "processed": 0,
                    "success": 0,
                    "partial": 0,
                    "no_opinion": 0,
                    "failed": 0,
                    "existing_failed": existing_failed,
                    "reused": len(candidates) - existing_failed,
                    "llm_requests": 0,
                },
            }

        self._opinion_extractor = OpenAIOpinionExtractor.from_settings()
        processor = OpinionProcessingService(
            self._opinion_extractor,
            lambda: SqlAlchemyOpinionUnitOfWork(self._session_factory),
            production_policy=policy,
        )
        results: dict[UUID, object] = {}
        errors: dict[UUID, Exception] = {}
        catastrophic = asyncio.Event()

        async def process_one(event_id: UUID) -> object:
            if catastrophic.is_set():
                raise RuntimeError("ANALYSIS_ABORTED_AFTER_HARD_FAILURE")
            try:
                result = await processor.process(
                    event_id,
                    analysis_spec=policy.active_spec,
                )
            except Exception as exc:
                errors[event_id] = exc
                if _failure_code(exc) in _HARD_ANALYSIS_CODES:
                    catastrophic.set()
                raise
            results[event_id] = result
            return result

        def progress(_: AnalysisRecoveryProgress) -> None:
            return None

        recovery = await AnalysisBackfillRunner(
            process_one,
            batch_size=batch_size,
            max_concurrency=concurrency,
        ).run(missing, progress_callback=progress)
        hard_error = next(
            (error for error in errors.values() if _failure_code(error) in _HARD_ANALYSIS_CODES),
            None,
        )
        if hard_error is not None:
            raise RefreshStageError(
                RefreshStage.ANALYSIS,
                _failure_code(hard_error),
                _safe_message(hard_error),
            ) from hard_error

        status_counts: Counter[str] = Counter()
        for result in results.values():
            status_counts[str(_enum_value(getattr(result, "status", "UNKNOWN"))).lower()] += 1
        analysis_ids = self._active_analysis_ids(event_ids, policy.active_analysis_version)
        return {
            "partial": bool(recovery.failed or existing_failed),
            "analysis_ids": analysis_ids,
            "counts": {
                "processed": recovery.attempted,
                "success": status_counts["processed"],
                "partial": status_counts["partially_resolved"],
                "no_opinion": status_counts["no_opinion"],
                "failed": recovery.failed,
                "existing_failed": existing_failed,
                "reused": recovery.reused,
                "llm_requests": self._opinion_extractor.request_count,
                "llm_retries": self._opinion_extractor.retry_count,
                "failure_codes": dict(recovery.failure_codes),
            },
        }

    def _active_analysis_ids(
        self,
        event_ids: Sequence[UUID],
        analysis_version: str,
    ) -> tuple[UUID, ...]:
        if not event_ids:
            return ()
        with self._session_factory() as session:
            statement = (
                select(EventAnalysis.id)
                .where(
                    EventAnalysis.event_id.in_(event_ids),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status != EventAnalysisStatus.FAILED,
                )
                .order_by(EventAnalysis.id)
            )
            return tuple(session.scalars(statement))

    def _active_opinion_rows(
        self,
        event_ids: Sequence[UUID],
        analysis_version: str,
    ) -> tuple[tuple[UUID, UUID, UUID], ...]:
        if not event_ids:
            return ()
        with self._session_factory() as session:
            statement = (
                select(Opinion.id, Opinion.investor_id, Opinion.asset_id)
                .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                .where(
                    Opinion.event_id.in_(event_ids),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status.in_(
                        [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                    ),
                )
                .order_by(Opinion.id)
            )
            return tuple(session.execute(statement))

    def _materialize_resolution(
        self,
        event_ids: Sequence[UUID],
        *,
        batch_size: int,
    ) -> dict[str, object]:
        del batch_size
        policy = get_production_analysis_policy()
        analysis_ids = self._active_analysis_ids(event_ids, policy.active_analysis_version)
        if not analysis_ids:
            return {
                "partial": False,
                "counts": {
                    "analyses": 0,
                    "resolved_references": 0,
                    "unresolved_references": 0,
                    "created": 0,
                    "reused": 0,
                    "failed": 0,
                },
            }

        recovery = AssetRecoveryService(lambda: SqlAlchemyOpinionUnitOfWork(self._session_factory))
        created = reused = resolved = unresolved = 0
        failures: list[str] = []
        for analysis_id in analysis_ids:
            try:
                result = recovery.recover(analysis_id=analysis_id)
            except Exception as exc:
                failures.append(f"{analysis_id}:{type(exc).__name__}")
                continue
            created += result.created_count
            reused += result.reused_count
            resolved += len(result.resolved_asset_ids)
            unresolved += len(result.unresolved_assets)
        return {
            "partial": bool(failures),
            "counts": {
                "analyses": len(analysis_ids),
                "resolved_references": resolved,
                "unresolved_references": unresolved,
                "created": created,
                "reused": reused,
                "failed": len(failures),
                "failure_items": failures,
            },
        }

    async def _derive_domain(
        self,
        event_ids: Sequence[UUID],
        *,
        attention_concurrency: int,
    ) -> dict[str, object]:
        policy = get_production_analysis_policy()
        effective_policy = policy.as_effective_policy()
        opinion_rows = self._active_opinion_rows(event_ids, policy.active_analysis_version)
        opinion_ids = tuple(row[0] for row in opinion_rows)
        affected_assets = {row[2] for row in opinion_rows}
        affected_investors = {row[1] for row in opinion_rows}
        affected_pairs = {(row[1], row[2]) for row in opinion_rows}

        state_updater = StateUpdateService(
            lambda: SqlAlchemyStateUnitOfWork(self._session_factory),
            effective_policy,
        )
        state_failures: list[str] = []
        state_changed = 0
        for opinion_id in opinion_ids:
            try:
                result = state_updater.update(opinion_id)
            except Exception as exc:
                state_failures.append(f"{opinion_id}:{type(exc).__name__}")
                continue
            affected_assets.add(result.after.asset_id)
            affected_investors.add(result.after.investor_id)
            if result.projection_changed:
                state_changed += 1

        attention = AttentionOccurrenceService(
            lambda: SqlAlchemyAttentionUnitOfWork(self._session_factory),
            effective_policy,
            attention_policy_version=get_production_attention_policy_version(),
        )
        attention_results = await self._bounded_event_calls(
            event_ids,
            attention.rebuild_event,
            attention_concurrency,
        )
        attention_failures: list[str] = []
        attention_created = attention_updated = attention_deleted = 0
        for event_id, result in zip(event_ids, attention_results, strict=True):
            if isinstance(result, Exception):
                attention_failures.append(f"{event_id}:{type(result).__name__}")
                continue
            attention_created += result.created_count
            attention_updated += result.updated_count
            attention_deleted += result.deleted_count
            affected_assets.update(result.affected_asset_ids)

        thesis_created = thesis_reused = 0
        thesis_failures: list[str] = []
        thesis_opinion_ids = self._opinion_ids_for_pairs(
            affected_pairs,
            policy.active_analysis_version,
        )
        if thesis_opinion_ids:
            self._thesis_comparator = OpenAICompatibleThesisComparator.from_settings()
            thesis = ThesisChangeService(
                lambda: SqlAlchemyThesisChangeUnitOfWork(self._session_factory),
                effective_policy,
                self._thesis_comparator,
            )
            for opinion_id in thesis_opinion_ids:
                try:
                    result = await thesis.process(opinion_id)
                except Exception as exc:
                    thesis_failures.append(f"{opinion_id}:{type(exc).__name__}")
                    continue
                thesis_created += int(result.created)
                thesis_reused += int(not result.created)
                affected_assets.add(result.asset_id)
                affected_investors.add(result.investor_id)

        return {
            "partial": bool(state_failures or attention_failures or thesis_failures),
            "affected_assets": affected_assets,
            "affected_investors": affected_investors,
            "counts": {
                "opinions": len(opinion_ids),
                "state_updated": state_changed,
                "state_failed": len(state_failures),
                "attention_created": attention_created,
                "attention_updated": attention_updated,
                "attention_deleted": attention_deleted,
                "attention_failed": len(attention_failures),
                "thesis_created": thesis_created,
                "thesis_reused": thesis_reused,
                "thesis_failed": len(thesis_failures),
                "state_failure_items": state_failures,
                "attention_failure_items": attention_failures,
                "thesis_failure_items": thesis_failures,
            },
        }

    async def _bounded_event_calls(
        self,
        event_ids: Sequence[UUID],
        operation: Callable[[UUID], object],
        concurrency: int,
    ) -> list[object]:
        if concurrency < 1:
            raise ValueError("attention_concurrency must be at least 1")
        semaphore = asyncio.Semaphore(concurrency)

        async def run_one(event_id: UUID) -> object:
            async with semaphore:
                try:
                    return await asyncio.to_thread(operation, event_id)
                except Exception as exc:
                    return exc

        return list(await asyncio.gather(*(run_one(event_id) for event_id in event_ids)))

    def _opinion_ids_for_pairs(
        self,
        pairs: set[tuple[UUID, UUID]],
        analysis_version: str,
    ) -> tuple[UUID, ...]:
        if not pairs:
            return ()
        predicates = [
            and_(Opinion.investor_id == investor_id, Opinion.asset_id == asset_id)
            for investor_id, asset_id in pairs
        ]
        with self._session_factory() as session:
            statement = (
                select(Opinion.id)
                .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                .where(
                    or_(*predicates),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status.in_(
                        [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                    ),
                )
                .order_by(Opinion.id)
            )
            return tuple(session.scalars(statement))

    def _raw_event_time_bounds(self) -> tuple[datetime | None, datetime | None]:
        with self._session_factory() as session:
            earliest, latest = session.execute(
                select(func.min(RawEvent.published_time), func.max(RawEvent.published_time))
            ).one()
        return (
            _utc(earliest) if earliest is not None else None,
            _utc(latest) if latest is not None else None,
        )

    def _derive_cross_investor(self, asset_ids: set[UUID]) -> dict[str, object]:
        if not asset_ids:
            return {
                "partial": False,
                "affected_assets": set(),
                "counts": {
                    "assets": 0,
                    "snapshots": 0,
                    "alignments": 0,
                    "consensus": 0,
                    "skipped_single_investor": 0,
                    "failed": 0,
                },
            }
        window_start, window_end = self._raw_event_time_bounds()
        if window_start is None or window_end is None:
            return {
                "partial": False,
                "affected_assets": set(),
                "counts": {
                    "assets": 0,
                    "snapshots": 0,
                    "alignments": 0,
                    "consensus": 0,
                    "skipped_single_investor": 0,
                    "failed": 0,
                },
            }

        snapshot_service = CrossInvestorAssetSnapshotService.from_production(
            lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(self._session_factory)
        )
        alignment_service = CrossInvestorAssetAlignmentService(
            lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(self._session_factory)
        )
        consensus_service = CrossInvestorConsensusEvidenceService(
            lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(self._session_factory)
        )
        snapshots = []
        snapshot_failures: list[str] = []
        for asset_id in sorted(asset_ids, key=lambda value: value.int):
            try:
                snapshots.append(
                    snapshot_service.calculate(
                        asset_id,
                        window_start,
                        window_end,
                        as_of=window_end,
                    )
                )
            except Exception as exc:
                snapshot_failures.append(f"{asset_id}:{type(exc).__name__}")

        alignments = consensus = skipped = 0
        alignment_failures: list[str] = []
        consensus_failures: list[str] = []
        for snapshot in snapshots:
            if snapshot.attention_investor_count < 2:
                skipped += 1
                continue
            try:
                alignment = alignment_service.calculate(snapshot.id)
                alignments += 1
            except Exception as exc:
                alignment_failures.append(f"{snapshot.id}:{type(exc).__name__}")
                continue
            try:
                consensus_service.calculate(snapshot.id, alignment.id)
                consensus += 1
            except Exception as exc:
                consensus_failures.append(f"{snapshot.id}:{type(exc).__name__}")
        failures = snapshot_failures + alignment_failures + consensus_failures
        return {
            "partial": bool(failures),
            "affected_assets": set(asset_ids),
            "counts": {
                "assets": len(asset_ids),
                "snapshots": len(snapshots),
                "alignments": alignments,
                "consensus": consensus,
                "skipped_single_investor": skipped,
                "failed": len(failures),
                "window_start": window_start.isoformat(),
                "window_end": window_end.isoformat(),
                "failure_items": failures,
            },
        }

    def _generate_signals(self, asset_ids: set[UUID]) -> dict[str, int]:
        result = SignalGenerator.from_production(self._session_factory).generate(
            asset_ids=asset_ids
        )
        return {
            "candidates": len(result.candidates),
            "created": result.created_count,
            "reused": result.reused_count,
        }

    def _aggregate_events(self, asset_ids: set[UUID]) -> dict[str, object]:
        result = IntelligenceEventAggregator.from_production(self._session_factory).aggregate(
            asset_ids=asset_ids
        )
        return {
            "candidates": len(result.candidates),
            "created": result.created_event_count,
            "reused": result.reused_event_count,
            "evidence_created": result.created_evidence_count,
            "evidence_reused": result.reused_evidence_count,
            "event_ids": [str(event.id) for event in result.events],
        }

    def _materialize_priorities(self, event_ids: Sequence[UUID]) -> dict[str, object]:
        result = IntelligencePriorityService.from_production(self._session_factory).materialize(
            event_ids=event_ids
        )
        return {
            "candidates": len(result.candidates),
            "created": result.created_count,
            "reused": result.reused_count,
            "priority_ids": [str(priority.id) for priority in result.priorities],
        }

    def _materialize_feed(self, priority_ids: Sequence[UUID]) -> dict[str, int]:
        result = IntelligenceFeedService.from_production(self._session_factory).materialize(
            priority_ids=priority_ids
        )
        return {
            "candidates": len(result.candidates),
            "created": result.created_count,
            "reused": result.reused_count,
        }

    def _apply_feed_lifecycle(self) -> dict[str, object]:
        result = FeedLifecycleService.from_production(self._session_factory).apply()
        return {
            "updated": result.updated_count,
            "reused": result.reused_count,
            "transitions": len(result.plan.transitions),
            "evaluated_at": result.plan.evaluated_at.isoformat(),
        }

    def _verify_product(
        self,
        asset_ids: set[UUID],
        investor_ids: set[UUID],
    ) -> dict[str, object]:
        assets = set(asset_ids)
        investors = set(investor_ids)
        if not assets:
            existing = self._first_id(Asset)
            if existing is not None:
                assets.add(existing)
        if not investors:
            existing = self._first_id(Investor)
            if existing is not None:
                investors.add(existing)

        asset_service = AssetIntelligenceProductService.from_production(self._session_factory)
        investor_service = InvestorIntelligenceProductService.from_production(self._session_factory)
        verified_assets: list[str] = []
        verified_investors: list[str] = []
        failures: list[str] = []
        for asset_id in sorted(assets, key=lambda value: value.int):
            try:
                asset_service.get_asset_view(asset_id)
            except Exception as exc:
                failures.append(f"asset:{asset_id}:{type(exc).__name__}")
            else:
                verified_assets.append(str(asset_id))
        for investor_id in sorted(investors, key=lambda value: value.int):
            try:
                investor_service.get_investor_view(investor_id)
            except Exception as exc:
                failures.append(f"investor:{investor_id}:{type(exc).__name__}")
            else:
                verified_investors.append(str(investor_id))
        return {
            "partial": bool(failures),
            "verified_assets": verified_assets,
            "verified_investors": verified_investors,
            "affected_assets": len(asset_ids),
            "affected_investors": len(investor_ids),
            "failed": len(failures),
            "failure_items": failures,
        }

    def _first_id(self, model: Any) -> UUID | None:
        with self._session_factory() as session:
            return session.scalar(select(model.id).order_by(model.id).limit(1))


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise argparse.ArgumentTypeError("time values must include a UTC offset")
    return parsed


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the canonical incremental Xueqiu-to-Product refresh"
    )
    parser.add_argument("--max-batches", type=_positive_int, default=1)
    parser.add_argument("--since", type=_parse_datetime)
    parser.add_argument("--until", type=_parse_datetime)
    parser.add_argument("--only-investor-ids", nargs="+", default=())
    parser.add_argument("--headless", action="store_true")
    parser.add_argument("--cdp-endpoint")
    parser.add_argument(
        "--skip-collection",
        action="store_true",
        help="debug downstream stages for explicit --raw-event-id values",
    )
    parser.add_argument("--raw-event-id", action="append", type=UUID, default=[])
    parser.add_argument("--batch-size", type=_positive_int, default=10)
    parser.add_argument("--analysis-concurrency", type=_positive_int, default=4)
    parser.add_argument("--attention-concurrency", type=_positive_int, default=4)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.skip_collection and not args.raw_event_id:
        raise SystemExit("--skip-collection requires at least one --raw-event-id")
    print("Refresh started")
    summary = asyncio.run(
        OperationalRefreshService().run(
            max_batches=args.max_batches,
            since=args.since,
            until=args.until,
            only_author_ids=tuple(args.only_investor_ids),
            headless=args.headless,
            cdp_endpoint=args.cdp_endpoint,
            skip_collection=args.skip_collection,
            raw_event_ids=tuple(args.raw_event_id),
            batch_size=args.batch_size,
            analysis_concurrency=args.analysis_concurrency,
            attention_concurrency=args.attention_concurrency,
        )
    )
    print("REFRESH_RESULT=" + json.dumps(summary.as_dict(), ensure_ascii=False, indent=2))
    return 0 if summary.result == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
