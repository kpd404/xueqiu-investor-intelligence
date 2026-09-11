"""Collect selected Investor history and run the existing production pipeline.

The collection phase delegates all browser behavior to the verified
``InvestorHistoryCollectionRequest`` / ``run_history_probe`` path.  The
processing phase is intentionally scoped to RawEvents inserted by this run;
cross-investor artifacts are then recalculated from the complete effective
dataset using their existing versioned services.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import and_, func, select

from ai import OpenAICompatibleThesisComparator, OpenAIOpinionExtractor, OpinionProcessingService
from collectors.xueqiu.investor_history import (
    InvestorHistoryCollectionRequest,
    InvestorHistoryProbeResult,
    browser_config,
    run_history_probe,
)
from config import get_production_analysis_policy, get_production_attention_policy_version
from contracts import CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2, EventAnalysisStatus
from database.models import EventAnalysis, Investor, Opinion, RawEvent
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
from intelligence import (
    AttentionOccurrenceService,
    CrossInvestorAssetAlignmentService,
    CrossInvestorAssetSnapshotService,
    CrossInvestorConsensusEvidenceService,
    StateUpdateService,
    ThesisChangeService,
)
from pipeline import AnalysisBackfillRunner, AnalysisRecoveryCandidate, AnalysisRecoveryProgress
from resolution import AssetRecoveryService


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _load_target_investors(investor_ids: tuple[UUID, ...]) -> dict[UUID, Investor]:
    with SessionFactory() as session:
        investors = {
            investor.id: investor
            for investor in session.scalars(
                select(Investor).where(Investor.id.in_(investor_ids))
            ).all()
        }
    missing = [str(investor_id) for investor_id in investor_ids if investor_id not in investors]
    if missing:
        raise ValueError("Investor IDs do not exist: " + ", ".join(missing))
    invalid_platform = [
        str(investor_id)
        for investor_id in investor_ids
        if investors[investor_id].platform != "xueqiu"
    ]
    if invalid_platform:
        raise ValueError(
            "target Investors must use the xueqiu platform: " + ", ".join(invalid_platform)
        )
    return investors


def _load_event_ids_by_investor(investor_ids: Iterable[UUID]) -> dict[UUID, set[UUID]]:
    ids = tuple(investor_ids)
    if not ids:
        return {}
    with SessionFactory() as session:
        rows = session.execute(
            select(RawEvent.investor_id, RawEvent.id).where(RawEvent.investor_id.in_(ids))
        )
    result: dict[UUID, set[UUID]] = {investor_id: set() for investor_id in ids}
    for investor_id, event_id in rows:
        result.setdefault(investor_id, set()).add(event_id)
    return result


def _load_new_event_ids(
    investor_ids: tuple[UUID, ...],
    baseline: dict[UUID, set[UUID]],
) -> tuple[UUID, ...]:
    current = _load_event_ids_by_investor(investor_ids)
    new_ids = {
        event_id
        for investor_id in investor_ids
        for event_id in current.get(investor_id, set()) - baseline.get(investor_id, set())
    }
    if not new_ids:
        return ()
    with SessionFactory() as session:
        return tuple(
            session.scalars(
                select(RawEvent.id)
                .where(RawEvent.id.in_(new_ids))
                .order_by(RawEvent.published_time, RawEvent.id)
            ).all()
        )


def _load_analysis_candidates(
    event_ids: tuple[UUID, ...],
    analysis_version: str,
) -> tuple[AnalysisRecoveryCandidate, ...]:
    if not event_ids:
        return ()
    with SessionFactory() as session:
        rows = session.execute(
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
        AnalysisRecoveryCandidate(event_id=event_id, status=status) for event_id, status in rows
    )


def _load_active_analysis_ids(
    event_ids: tuple[UUID, ...],
    analysis_version: str,
) -> tuple[UUID, ...]:
    if not event_ids:
        return ()
    with SessionFactory() as session:
        return tuple(
            session.scalars(
                select(EventAnalysis.id)
                .where(
                    EventAnalysis.event_id.in_(event_ids),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status.in_(
                        [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                    ),
                )
                .order_by(EventAnalysis.id)
            ).all()
        )


def _load_statuses(analysis_version: str) -> Counter[str]:
    with SessionFactory() as session:
        rows = session.execute(
            select(EventAnalysis.status).where(EventAnalysis.analysis_version == analysis_version)
        )
    return Counter(str(getattr(status, "value", status)) for (status,) in rows)


def _load_effective_opinion_ids_for_events(
    event_ids: tuple[UUID, ...],
    analysis_version: str,
) -> tuple[UUID, ...]:
    if not event_ids:
        return ()
    with SessionFactory() as session:
        return tuple(
            session.scalars(
                select(Opinion.id)
                .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                .join(RawEvent, Opinion.event_id == RawEvent.id)
                .where(
                    Opinion.event_id.in_(event_ids),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status.in_(
                        [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                    ),
                )
                .order_by(RawEvent.published_time, RawEvent.id, Opinion.id)
            ).all()
        )


def _load_affected_pairs(opinion_ids: tuple[UUID, ...]) -> tuple[tuple[UUID, UUID], ...]:
    if not opinion_ids:
        return ()
    with SessionFactory() as session:
        rows = session.execute(
            select(Opinion.investor_id, Opinion.asset_id)
            .where(Opinion.id.in_(opinion_ids))
            .distinct()
        )
    return tuple(sorted(set(rows), key=lambda value: (value[0].int, value[1].int)))


def _load_effective_opinions_for_pairs(
    pairs: tuple[tuple[UUID, UUID], ...],
    analysis_version: str,
) -> tuple[UUID, ...]:
    if not pairs:
        return ()
    pair_predicate = tuple(
        (Opinion.investor_id == investor_id) & (Opinion.asset_id == asset_id)
        for investor_id, asset_id in pairs
    )
    from sqlalchemy import or_

    with SessionFactory() as session:
        return tuple(
            session.scalars(
                select(Opinion.id)
                .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                .join(RawEvent, Opinion.event_id == RawEvent.id)
                .where(
                    or_(*pair_predicate),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status.in_(
                        [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                    ),
                )
                .order_by(RawEvent.published_time, RawEvent.id, Opinion.id)
            ).all()
        )


def _load_observed_range() -> tuple[datetime, datetime]:
    with SessionFactory() as session:
        earliest, latest = session.execute(
            select(func.min(RawEvent.published_time), func.max(RawEvent.published_time))
        ).one()
    if earliest is None or latest is None:
        raise RuntimeError("no RawEvents are available")
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
    snapshot_rebuilder = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(SessionFactory)
    )
    alignment_rebuilder = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(SessionFactory)
    )
    consensus_rebuilder = CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(SessionFactory),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
    )
    return (
        production_policy,
        effective_policy,
        opinion_extractor,
        thesis_comparator,
        opinion_processor,
        state_updater,
        AssetRecoveryService(opinion_uow),
        attention_rebuilder,
        thesis_rebuilder,
        snapshot_rebuilder,
        alignment_rebuilder,
        consensus_rebuilder,
    )


async def _run_analysis(
    candidates: tuple[AnalysisRecoveryCandidate, ...],
    processor: OpinionProcessingService,
    production_policy,
    extractor: OpenAIOpinionExtractor,
    *,
    batch_size: int,
    concurrency: int,
) -> dict[str, object]:
    async def process_one(event_id: UUID) -> object:
        return await processor.process(event_id, analysis_spec=production_policy.active_spec)

    def report_progress(progress: AnalysisRecoveryProgress) -> None:
        print(
            json.dumps(
                {
                    "phase": "analysis",
                    **progress.as_dict(),
                    "retry_count": extractor.retry_count,
                    "llm_calls": extractor.request_count,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    result = await AnalysisBackfillRunner(
        process_one,
        batch_size=batch_size,
        max_concurrency=concurrency,
    ).run(candidates, progress_callback=report_progress)
    return {
        **result.as_dict(),
        "llm_calls": extractor.request_count,
        "retry_count": extractor.retry_count,
    }


async def _recover_assets(
    analysis_ids: tuple[UUID, ...],
    recovery: AssetRecoveryService,
    *,
    batch_size: int,
    concurrency: int,
) -> dict[str, object]:
    statuses: Counter[str] = Counter()
    failures: list[str] = []
    created = reused = resolved = 0
    for start in range(0, len(analysis_ids), batch_size):
        batch = analysis_ids[start : start + batch_size]
        semaphore = asyncio.Semaphore(concurrency)

        async def recover_one(analysis_id: UUID, *, limiter: asyncio.Semaphore = semaphore):
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
            statuses[result.status.value] += 1
            created += result.created_count
            reused += result.reused_count
            resolved += len(result.resolved_asset_ids)
    return {
        "analyses": len(analysis_ids),
        "status": dict(statuses),
        "opinion_created": created,
        "opinion_reused": reused,
        "resolved_asset_references": resolved,
        "failed": failures,
    }


async def _rebuild_attention(
    event_ids: tuple[UUID, ...],
    rebuilder: AttentionOccurrenceService,
    *,
    batch_size: int,
    concurrency: int,
) -> dict[str, object]:
    created = updated = deleted = 0
    failures: list[str] = []
    for start in range(0, len(event_ids), batch_size):
        batch = event_ids[start : start + batch_size]
        semaphore = asyncio.Semaphore(concurrency)

        async def rebuild_one(event_id: UUID, *, limiter: asyncio.Semaphore = semaphore):
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
    return {
        "events": len(event_ids),
        "created": created,
        "updated": updated,
        "deleted": deleted,
        "failed": failures,
    }


async def _rebuild_thesis(
    opinion_ids: tuple[UUID, ...],
    rebuilder: ThesisChangeService,
) -> dict[str, object]:
    created = reused = 0
    failures: list[str] = []
    for opinion_id in opinion_ids:
        try:
            result = await rebuilder.process(opinion_id)
        except Exception as exc:
            failures.append(f"{opinion_id}:{type(exc).__name__}")
            continue
        if result.created:
            created += 1
        else:
            reused += 1
    return {"opinions": len(opinion_ids), "created": created, "reused": reused, "failed": failures}


def _rebuild_cross_investor(
    production_policy,
    effective_policy,
    snapshot_rebuilder: CrossInvestorAssetSnapshotService,
    alignment_rebuilder: CrossInvestorAssetAlignmentService,
    consensus_rebuilder: CrossInvestorConsensusEvidenceService,
) -> dict[str, object]:
    window_start, window_end = _load_observed_range()
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
    consensus_states: Counter[str] = Counter()
    consensus_coverage: Counter[str] = Counter()
    alignment_failures: list[str] = []
    consensus_failures: list[str] = []
    for snapshot in snapshots:
        if snapshot.attention_investor_count < 2:
            continue
        try:
            alignment = alignment_rebuilder.calculate(snapshot.id)
            alignments += 1
        except Exception as exc:
            alignment_failures.append(f"{snapshot.id}:{type(exc).__name__}")
            continue
        try:
            evidence = consensus_rebuilder.calculate(snapshot.id, alignment.id)
            consensus_states[evidence.consensus_state.value] += 1
            consensus_coverage[evidence.opinion_coverage_state.value] += 1
        except Exception as exc:
            consensus_failures.append(f"{snapshot.id}:{type(exc).__name__}")
    return {
        "window_start": window_start.isoformat(),
        "window_end": window_end.isoformat(),
        "assets": len(asset_ids),
        "snapshots": len(snapshots),
        "snapshot_failed": snapshot_failures,
        "alignments": alignments,
        "alignment_failed": alignment_failures,
        "consensus": {
            "processed_overlap_snapshots": sum(consensus_states.values()),
            "states": dict(consensus_states),
            "coverage": dict(consensus_coverage),
            "failed": consensus_failures,
        },
    }


async def run(
    investor_ids: tuple[UUID, ...],
    *,
    attach_cdp_endpoint: str,
    lookback_days: int = 30,
    max_pages: int = 10,
    max_idle_cycles: int = 3,
    max_duration: int = 300,
    response_wait_ms: int = 1500,
    batch_size: int = 10,
    analysis_concurrency: int = 4,
    attention_concurrency: int = 4,
) -> dict[str, object]:
    investors = _load_target_investors(investor_ids)
    baseline = _load_event_ids_by_investor(investor_ids)
    production_policy = get_production_analysis_policy()
    print(
        json.dumps(
            {
                "phase": "preflight",
                "analysis_version": production_policy.active_analysis_version,
                "target_investors": [
                    {
                        "investor_id": str(investor_id),
                        "name": investors[investor_id].name,
                        "platform_user_id": investors[investor_id].platform_user_id,
                        "baseline_raw_events": len(baseline.get(investor_id, set())),
                    }
                    for investor_id in investor_ids
                ],
                "baseline_raw_events": sum(len(values) for values in baseline.values()),
                "active_analysis_before": dict(
                    _load_statuses(production_policy.active_analysis_version)
                ),
            },
            ensure_ascii=False,
        ),
        flush=True,
    )

    collection_results: list[InvestorHistoryProbeResult] = []
    for index, investor_id in enumerate(investor_ids, start=1):
        investor = investors[investor_id]
        print(
            json.dumps(
                {
                    "phase": "collection_start",
                    "index": index,
                    "total": len(investor_ids),
                    "investor_id": str(investor_id),
                    "name": investor.name,
                    "platform_user_id": investor.platform_user_id,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )
        request = InvestorHistoryCollectionRequest.for_lookback(
            investor_id=investor_id,
            platform_user_id=investor.platform_user_id,
            lookback_days=lookback_days,
            max_pages=max_pages,
            max_idle_cycles=max_idle_cycles,
            max_duration_seconds=max_duration,
            human_assisted=True,
            attach_cdp_endpoint=attach_cdp_endpoint,
        )
        result = await run_history_probe(
            request,
            browser_config(headless=False, response_wait_ms=max(response_wait_ms, 0)),
        )
        collection_results.append(result)
        print(
            json.dumps(
                {"phase": "collection_result", **result.model_dump(mode="json")},
                ensure_ascii=False,
            ),
            flush=True,
        )

    new_event_ids = _load_new_event_ids(investor_ids, baseline)
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
        consensus_rebuilder,
    ) = _build_services()
    candidates = _load_analysis_candidates(new_event_ids, production_policy.active_analysis_version)
    analysis_result = await _run_analysis(
        candidates,
        opinion_processor,
        production_policy,
        opinion_extractor,
        batch_size=batch_size,
        concurrency=analysis_concurrency,
    )
    active_analysis_ids = _load_active_analysis_ids(
        new_event_ids,
        production_policy.active_analysis_version,
    )
    asset_result = await _recover_assets(
        active_analysis_ids,
        asset_recovery,
        batch_size=batch_size,
        concurrency=analysis_concurrency,
    )
    new_opinion_ids = _load_effective_opinion_ids_for_events(
        new_event_ids,
        production_policy.active_analysis_version,
    )
    state_failures: list[str] = []
    for opinion_id in new_opinion_ids:
        try:
            state_updater.update(opinion_id)
        except Exception as exc:
            state_failures.append(f"{opinion_id}:{type(exc).__name__}")
    attention_result = await _rebuild_attention(
        new_event_ids,
        attention_rebuilder,
        batch_size=batch_size,
        concurrency=attention_concurrency,
    )
    affected_pairs = _load_affected_pairs(new_opinion_ids)
    thesis_opinion_ids = _load_effective_opinions_for_pairs(
        affected_pairs,
        production_policy.active_analysis_version,
    )
    thesis_result = await _rebuild_thesis(thesis_opinion_ids, thesis_rebuilder)
    cross_investor_result = _rebuild_cross_investor(
        production_policy,
        effective_policy,
        snapshot_rebuilder,
        alignment_rebuilder,
        consensus_rebuilder,
    )
    active_statuses_after = _load_statuses(production_policy.active_analysis_version)
    collection_stopped = [
        {
            "investor_id": str(result.investor_id),
            "stop_reason": result.stop_reason.value,
            "error": result.error,
        }
        for result in collection_results
        if result.status.value != "COMPLETED"
    ]
    failures = {
        "collection": len(collection_stopped),
        "analysis": int(analysis_result["failed"]),
        "asset_recovery": len(asset_result["failed"]),
        "state": len(state_failures),
        "attention": len(attention_result["failed"]),
        "thesis": len(thesis_result["failed"]),
        "snapshot": len(cross_investor_result["snapshot_failed"]),
        "alignment": len(cross_investor_result["alignment_failed"]),
        "consensus": len(cross_investor_result["consensus"]["failed"]),
    }
    result = {
        "analysis_version": production_policy.active_analysis_version,
        "target_investors": [str(investor_id) for investor_id in investor_ids],
        "collection": {
            "lookback_days": lookback_days,
            "results": [item.model_dump(mode="json") for item in collection_results],
            "stopped": collection_stopped,
        },
        "baseline_raw_events": sum(len(values) for values in baseline.values()),
        "new_raw_events": len(new_event_ids),
        "analysis": analysis_result,
        "active_analysis_ids_processed": len(active_analysis_ids),
        "asset_recovery": asset_result,
        "new_effective_opinions": len(new_opinion_ids),
        "state_update_failures": state_failures,
        "attention": attention_result,
        "affected_investor_asset_pairs": len(affected_pairs),
        "thesis": {
            **thesis_result,
            "llm_calls": thesis_comparator.request_count,
            "retry_count": getattr(thesis_comparator, "retry_count", 0),
        },
        "cross_investor": cross_investor_result,
        "active_analysis_after": dict(active_statuses_after),
        "total_llm_calls": opinion_extractor.request_count + thesis_comparator.request_count,
        "total_retry_count": opinion_extractor.retry_count
        + getattr(thesis_comparator, "retry_count", 0),
        "failures": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return result


def _positive_int(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be at least 1")
    return parsed


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--investor-id", action="append", required=True, type=UUID)
    parser.add_argument("--attach-cdp", required=True)
    parser.add_argument("--lookback-days", type=int, choices=(30,), default=30)
    parser.add_argument("--max-pages", type=_positive_int, default=10)
    parser.add_argument("--max-idle-cycles", type=_positive_int, default=3)
    parser.add_argument("--max-duration", type=_positive_int, default=300)
    parser.add_argument("--response-wait-ms", type=int, default=1500)
    parser.add_argument("--batch-size", type=_positive_int, default=10)
    parser.add_argument("--analysis-concurrency", type=_positive_int, default=4)
    parser.add_argument("--attention-concurrency", type=_positive_int, default=4)
    args = parser.parse_args()
    if not 5 <= len(args.investor_id) <= 10:
        parser.error("repeat --investor-id between 5 and 10 times")
    if args.analysis_concurrency > 16 or args.attention_concurrency > 16:
        parser.error("concurrency must be <= 16")
    result = asyncio.run(
        run(
            tuple(args.investor_id),
            attach_cdp_endpoint=args.attach_cdp,
            lookback_days=args.lookback_days,
            max_pages=args.max_pages,
            max_idle_cycles=args.max_idle_cycles,
            max_duration=args.max_duration,
            response_wait_ms=args.response_wait_ms,
            batch_size=args.batch_size,
            analysis_concurrency=args.analysis_concurrency,
            attention_concurrency=args.attention_concurrency,
        )
    )
    return 1 if any(result["failures"].values()) else 0


if __name__ == "__main__":
    raise SystemExit(main())
