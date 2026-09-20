"""Backfill missing production analyses and rebuild existing artifacts.

Only RawEvents without the active production EventAnalysis identity are sent
to the provider. Existing effective analyses are reused, active FAILED rows
are preserved as failures, and rerunning the command resumes from the
remaining missing set.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, func, select

from ai import (
    OpenAICompatibleThesisComparator,
    OpenAIOpinionExtractor,
    OpinionProcessingService,
)
from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
)
from contracts import EventAnalysisStatus
from database.models import EventAnalysis, Opinion, RawEvent
from database.session import SessionFactory
from database.unit_of_work import (
    SqlAlchemyAttentionUnitOfWork,
    SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork,
    SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
    SqlAlchemyThesisChangeUnitOfWork,
)
from intelligence import (
    AttentionOccurrenceService,
    CrossInvestorAssetAlignmentService,
    CrossInvestorAssetSnapshotService,
    StateUpdateService,
    ThesisChangeService,
)
from pipeline import (
    AnalysisBackfillRunner,
    AnalysisRecoveryCandidate,
    AnalysisRecoveryProgress,
)
from resolution import AssetRecoveryService
from resolution.materialization import RecoveryUnitOfWorkFactory

ListingIdentity = tuple[str, str]


def _load_candidates(
    analysis_version: str,
    investor_ids: tuple[UUID, ...] = (),
) -> tuple[AnalysisRecoveryCandidate, ...]:
    with SessionFactory() as session:
        statement = (
            select(RawEvent.id, EventAnalysis.status)
            .outerjoin(
                EventAnalysis,
                and_(
                    EventAnalysis.event_id == RawEvent.id,
                    EventAnalysis.analysis_version == analysis_version,
                ),
            )
            .order_by(RawEvent.published_time, RawEvent.id)
        )
        if investor_ids:
            statement = statement.where(RawEvent.investor_id.in_(investor_ids))
        return tuple(
            AnalysisRecoveryCandidate(event_id=event_id, status=status)
            for event_id, status in session.execute(statement)
        )


def _load_event_ids(investor_ids: tuple[UUID, ...] = ()) -> tuple[UUID, ...]:
    with SessionFactory() as session:
        statement = select(RawEvent.id).order_by(RawEvent.published_time, RawEvent.id)
        if investor_ids:
            statement = statement.where(RawEvent.investor_id.in_(investor_ids))
        return tuple(session.scalars(statement).all())


def _load_active_statuses(analysis_version: str) -> Counter[str]:
    with SessionFactory() as session:
        rows = session.execute(
            select(EventAnalysis.status).where(EventAnalysis.analysis_version == analysis_version)
        )
        return Counter(str(getattr(status, "value", status)) for (status,) in rows)


def _load_active_analysis_ids(analysis_version: str) -> tuple[UUID, ...]:
    with SessionFactory() as session:
        statement = (
            select(EventAnalysis.id)
            .where(
                EventAnalysis.analysis_version == analysis_version,
                EventAnalysis.status.in_(
                    [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                ),
            )
            .order_by(EventAnalysis.id)
        )
        return tuple(session.scalars(statement).all())


def _load_effective_opinion_ids(analysis_version: str) -> tuple[UUID, ...]:
    with SessionFactory() as session:
        statement = (
            select(Opinion.id)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .where(
                EventAnalysis.analysis_version == analysis_version,
                EventAnalysis.status.in_(
                    [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                ),
            )
            .order_by(RawEvent.published_time, RawEvent.id, Opinion.id)
        )
        return tuple(session.scalars(statement).all())


def _load_observed_range(investor_ids: tuple[UUID, ...] = ()) -> tuple[datetime, datetime]:
    with SessionFactory() as session:
        statement = select(func.min(RawEvent.published_time), func.max(RawEvent.published_time))
        if investor_ids:
            statement = statement.where(RawEvent.investor_id.in_(investor_ids))
        earliest, latest = session.execute(statement).one()
    if earliest is None or latest is None:
        raise RuntimeError("no RawEvents are available for the requested scope")
    return _utc(earliest), _utc(latest)


def _load_attention_asset_ids(
    analysis_policy,
    attention_policy_version: str,
    as_of: datetime,
) -> tuple[UUID, ...]:
    with SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(SessionFactory) as unit_of_work:
        rows = unit_of_work.attention_occurrences.list_effective(
            analysis_policy,
            attention_policy_version,
            as_of=as_of,
        )
    return tuple(sorted({row.asset_id for row in rows}, key=lambda value: value.int))


def _build_services():
    production_policy = get_production_analysis_policy()
    effective_policy = production_policy.as_effective_policy()

    def opinion_uow():
        return SqlAlchemyOpinionUnitOfWork(SessionFactory)

    def state_uow():
        return SqlAlchemyStateUnitOfWork(SessionFactory)

    def attention_uow():
        return SqlAlchemyAttentionUnitOfWork(SessionFactory)

    def thesis_uow():
        return SqlAlchemyThesisChangeUnitOfWork(SessionFactory)

    opinion_extractor = OpenAIOpinionExtractor.from_settings()
    opinion_processor = OpinionProcessingService(
        opinion_extractor,
        opinion_uow,
        production_policy=production_policy,
    )
    state_updater = StateUpdateService(state_uow, effective_policy)
    attention_rebuilder = AttentionOccurrenceService(
        attention_uow,
        effective_policy,
        attention_policy_version=get_production_attention_policy_version(),
    )
    thesis_comparator = OpenAICompatibleThesisComparator.from_settings()
    thesis_rebuilder = ThesisChangeService(
        thesis_uow,
        effective_policy,
        thesis_comparator,
    )
    asset_recovery = AssetRecoveryService(opinion_uow)
    snapshot_rebuilder = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(SessionFactory)
    )
    alignment_rebuilder = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(SessionFactory)
    )
    return (
        production_policy,
        effective_policy,
        opinion_extractor,
        thesis_comparator,
        opinion_processor,
        state_updater,
        asset_recovery,
        attention_rebuilder,
        thesis_rebuilder,
        snapshot_rebuilder,
        alignment_rebuilder,
    )


def run_resolution_materialization(
    *,
    analysis_ids: tuple[UUID, ...] = (),
    event_ids: tuple[UUID, ...] = (),
    analysis_version: str | None = None,
    allowed_market_symbols: tuple[ListingIdentity, ...] = (),
    dry_run: bool = False,
    unit_of_work_factory: RecoveryUnitOfWorkFactory | None = None,
) -> dict[str, object]:
    """Re-resolve and materialize Opinions without entering any LLM or downstream stage."""

    if not analysis_ids and not event_ids:
        raise ValueError("analysis_ids or event_ids is required")
    selected_analysis_version = analysis_version
    if event_ids and selected_analysis_version is None:
        selected_analysis_version = get_production_analysis_policy().active_analysis_version

    factory = unit_of_work_factory or (lambda: SqlAlchemyOpinionUnitOfWork(SessionFactory))
    results = AssetRecoveryService(factory).materialize_many(
        analysis_ids=analysis_ids,
        event_ids=event_ids,
        analysis_version=selected_analysis_version,
        allowed_market_symbols=allowed_market_symbols or None,
        dry_run=dry_run,
    )
    statuses = Counter(result.status.value for result in results)
    unresolved_reasons: Counter[str] = Counter()
    for result in results:
        unresolved_reasons.update(item.reason for item in result.unresolved_assets)
    return {
        "mode": "RESOLUTION_MATERIALIZATION_ONLY",
        "analysis_version": selected_analysis_version,
        "analyses": len(results),
        "created": sum(result.created_count for result in results),
        "reused": sum(result.reused_count for result in results),
        "resolved_asset_references": sum(len(result.resolved_asset_ids) for result in results),
        "unresolved_entries": sum(len(result.unresolved_assets) for result in results),
        "unresolved_reasons": dict(unresolved_reasons),
        "status": dict(statuses),
        "dry_run": dry_run,
        "llm_calls": {"analysis": 0, "thesis": 0, "other": 0},
        "downstream_stages_run": [],
    }


def _listing_identity(value: str) -> ListingIdentity:
    market, separator, symbol = value.partition(":")
    market = market.strip().upper()
    symbol = symbol.strip().upper()
    if not separator or market not in {"HK", "SH", "SZ"} or not symbol:
        raise argparse.ArgumentTypeError("listing identity must be HK|SH|SZ:SYMBOL")
    return market, symbol


async def _rebuild_attention(
    event_ids: tuple[UUID, ...],
    rebuilder: AttentionOccurrenceService,
    *,
    batch_size: int,
    max_concurrency: int,
) -> tuple[int, int, int, tuple[str, ...]]:
    created = updated = deleted = 0
    failures: list[str] = []
    for start in range(0, len(event_ids), batch_size):
        batch = event_ids[start : start + batch_size]
        semaphore = asyncio.Semaphore(max_concurrency)

        async def rebuild_one(
            event_id: UUID,
            *,
            limiter: asyncio.Semaphore = semaphore,
        ):
            async with limiter:
                return await asyncio.to_thread(rebuilder.rebuild_event, event_id)

        results = await asyncio.gather(
            *(rebuild_one(event_id) for event_id in batch),
            return_exceptions=True,
        )
        for event_id, result in zip(batch, results, strict=True):
            if isinstance(result, Exception):
                failures.append(f"{event_id}:{type(result).__name__}")
                continue
            created += result.created_count
            updated += result.updated_count
            deleted += result.deleted_count
    return created, updated, deleted, tuple(failures)


async def _recover_assets(
    analysis_ids: tuple[UUID, ...],
    recovery: AssetRecoveryService,
    *,
    batch_size: int,
    max_concurrency: int,
) -> dict[str, object]:
    status_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    created = reused = resolved = 0
    failures: list[str] = []
    for start in range(0, len(analysis_ids), batch_size):
        batch = analysis_ids[start : start + batch_size]
        semaphore = asyncio.Semaphore(max_concurrency)

        async def recover_one(
            analysis_id: UUID,
            *,
            limiter: asyncio.Semaphore = semaphore,
        ):
            async with limiter:
                return await asyncio.to_thread(recovery.recover, analysis_id=analysis_id)

        results = await asyncio.gather(
            *(recover_one(analysis_id) for analysis_id in batch),
            return_exceptions=True,
        )
        for analysis_id, result in zip(batch, results, strict=True):
            if isinstance(result, Exception):
                failures.append(f"{analysis_id}:{type(result).__name__}")
                continue
            status_counts[result.status.value] += 1
            created += result.created_count
            reused += result.reused_count
            resolved += len(result.resolved_asset_ids)
            reason_counts.update(item.reason for item in result.unresolved_assets)
    return {
        "analyses": len(analysis_ids),
        "status": dict(status_counts),
        "opinion_created": created,
        "opinion_reused": reused,
        "resolved_asset_references": resolved,
        "unresolved_entries": sum(reason_counts.values()),
        "unresolved_reasons": dict(reason_counts),
        "failed": failures,
    }


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


async def run(
    investor_ids: tuple[UUID, ...] = (),
    *,
    batch_size: int = 10,
    analysis_concurrency: int = 6,
    attention_concurrency: int = 6,
) -> dict[str, object]:
    if batch_size < 1:
        raise ValueError("batch_size must be at least 1")
    if analysis_concurrency < 1 or attention_concurrency < 1:
        raise ValueError("concurrency must be at least 1")

    (
        production_policy,
        effective_policy,
        opinion_extractor,
        thesis_comparator,
        opinion_processor,
        state_updater,
        asset_recovery,
        attention_rebuilder,
        thesis_rebuilder,
        snapshot_rebuilder,
        alignment_rebuilder,
    ) = _build_services()
    analysis_version = production_policy.active_analysis_version
    candidates = _load_candidates(analysis_version, investor_ids)
    before_statuses = _load_active_statuses(analysis_version)
    print(
        json.dumps(
            {
                "phase": "preflight",
                "analysis_version": analysis_version,
                "raw_events": len(candidates),
                "active_analysis": sum(item.status is not None for item in candidates),
                "missing_active_analysis": sum(item.status is None for item in candidates),
                "active_failed": sum(
                    item.status is EventAnalysisStatus.FAILED for item in candidates
                ),
                "statuses": dict(before_statuses),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    async def process_missing(event_id: UUID) -> object:
        return await opinion_processor.process(
            event_id,
            analysis_spec=production_policy.active_spec,
        )

    def report_progress(progress: AnalysisRecoveryProgress) -> None:
        payload = {
            "phase": "analysis_backfill",
            **progress.as_dict(),
            "retry_count": opinion_extractor.retry_count,
            "llm_calls": opinion_extractor.request_count,
        }
        print(json.dumps(payload, ensure_ascii=False), flush=True)

    recovery = await AnalysisBackfillRunner(
        process_missing,
        batch_size=batch_size,
        max_concurrency=analysis_concurrency,
    ).run(candidates, progress_callback=report_progress)
    after_backfill_statuses = _load_active_statuses(analysis_version)

    active_analysis_ids = _load_active_analysis_ids(analysis_version)
    asset_recovery_result = await _recover_assets(
        active_analysis_ids,
        asset_recovery,
        batch_size=batch_size,
        max_concurrency=analysis_concurrency,
    )
    after_asset_recovery_statuses = _load_active_statuses(analysis_version)
    opinion_ids = _load_effective_opinion_ids(analysis_version)
    state_update_failures: list[str] = []
    for opinion_id in opinion_ids:
        try:
            state_updater.update(opinion_id)
        except Exception as exc:
            state_update_failures.append(f"{opinion_id}:{type(exc).__name__}")

    event_ids = _load_event_ids(investor_ids)
    (
        attention_created,
        attention_updated,
        attention_deleted,
        attention_failures,
    ) = await _rebuild_attention(
        event_ids,
        attention_rebuilder,
        batch_size=batch_size,
        max_concurrency=attention_concurrency,
    )

    thesis_created = thesis_reused = 0
    thesis_failures: list[str] = []
    for opinion_id in opinion_ids:
        try:
            result = await thesis_rebuilder.process(opinion_id)
            if result.created:
                thesis_created += 1
            else:
                thesis_reused += 1
        except Exception as exc:
            thesis_failures.append(f"{opinion_id}:{type(exc).__name__}")

    window_start, window_end = _load_observed_range(investor_ids)
    asset_ids = _load_attention_asset_ids(
        effective_policy,
        get_production_attention_policy_version(),
        window_end,
    )
    snapshots = []
    snapshot_failures: list[str] = []
    for asset_id in asset_ids:
        try:
            snapshots.append(
                snapshot_rebuilder.calculate(
                    asset_id,
                    window_start,
                    window_end,
                    as_of=window_end,
                )
            )
        except Exception as exc:
            snapshot_failures.append(f"{asset_id}:{type(exc).__name__}")

    alignments = 0
    alignment_skipped = 0
    alignment_failures: list[str] = []
    for snapshot in snapshots:
        if snapshot.attention_investor_count < 2:
            alignment_skipped += 1
            continue
        try:
            alignment_rebuilder.calculate(snapshot.id)
            alignments += 1
        except Exception as exc:
            alignment_failures.append(f"{snapshot.id}:{type(exc).__name__}")

    return {
        "analysis_version": analysis_version,
        "target_investors": [str(value) for value in investor_ids],
        "target_raw_events": len(event_ids),
        "analysis_before": dict(before_statuses),
        "analysis_after_backfill": dict(after_backfill_statuses),
        "analysis_after_asset_recovery": dict(after_asset_recovery_statuses),
        "analysis_backfill": {
            **recovery.as_dict(),
            "llm_calls": opinion_extractor.request_count,
            "retry_count": opinion_extractor.retry_count,
        },
        "total_llm_calls": opinion_extractor.request_count
        + getattr(thesis_comparator, "request_count", 0),
        "total_retry_count": opinion_extractor.retry_count
        + getattr(thesis_comparator, "retry_count", 0),
        "asset_recovery": asset_recovery_result,
        "effective_opinions": len(opinion_ids),
        "state_update_failures": state_update_failures,
        "attention_rebuild": {
            "events": len(event_ids),
            "created": attention_created,
            "updated": attention_updated,
            "deleted": attention_deleted,
            "failed": list(attention_failures),
        },
        "thesis_rebuild": {
            "created": thesis_created,
            "reused": thesis_reused,
            "llm_calls": getattr(thesis_comparator, "request_count", 0),
            "retry_count": getattr(thesis_comparator, "retry_count", 0),
            "failed": thesis_failures,
        },
        "cross_investor_snapshot_rebuild": {
            "assets": len(asset_ids),
            "snapshots": len(snapshots),
            "failed": snapshot_failures,
            "window_start": window_start.isoformat(),
            "window_end": window_end.isoformat(),
        },
        "cross_investor_alignment_rebuild": {
            "created_or_reused": alignments,
            "skipped_single_investor": alignment_skipped,
            "failed": alignment_failures,
        },
        "failures": {
            "analysis": recovery.failed,
            "state": len(state_update_failures),
            "attention": len(attention_failures),
            "thesis": len(thesis_failures),
            "snapshot": len(snapshot_failures),
            "alignment": len(alignment_failures),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--investor-id", action="append", type=UUID, default=[])
    parser.add_argument("--batch-size", type=int, default=10)
    parser.add_argument("--resolution-only", action="store_true")
    parser.add_argument("--analysis-id", action="append", type=UUID, default=[])
    parser.add_argument("--event-id", action="append", type=UUID, default=[])
    parser.add_argument(
        "--allowed-market-symbol",
        action="append",
        type=_listing_identity,
        default=[],
        metavar="MARKET:SYMBOL",
    )
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--analysis-concurrency", type=int, default=6)
    parser.add_argument("--attention-concurrency", type=int, default=6)
    args = parser.parse_args()
    if args.resolution_only:
        if not args.analysis_id and not args.event_id:
            parser.error("--resolution-only requires --analysis-id or --event-id")
        if args.investor_id:
            parser.error("--investor-id cannot be combined with --resolution-only")
        result = run_resolution_materialization(
            analysis_ids=tuple(args.analysis_id),
            event_ids=tuple(args.event_id),
            allowed_market_symbols=tuple(args.allowed_market_symbol),
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return
    if args.analysis_id or args.event_id or args.allowed_market_symbol or args.dry_run:
        parser.error(
            "--analysis-id, --event-id, --allowed-market-symbol, and --dry-run "
            "require --resolution-only"
        )
    result = asyncio.run(
        run(
            tuple(args.investor_id),
            batch_size=args.batch_size,
            analysis_concurrency=args.analysis_concurrency,
            attention_concurrency=args.attention_concurrency,
        )
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    failures = result["failures"]
    raise SystemExit(1 if any(failures.values()) else 0)


if __name__ == "__main__":
    main()
