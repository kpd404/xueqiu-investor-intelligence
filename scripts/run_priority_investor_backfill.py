"""Run the bounded failed-analysis recovery workflow for selected Investors.

This is an operational composition of existing production services. It does
not define a new policy, model, table, or intelligence rule.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections import Counter
from uuid import UUID

from sqlalchemy import select

from ai import OpenAICompatibleThesisComparator, OpenAIOpinionExtractor, OpinionProcessingService
from config import get_production_analysis_policy
from database.models import EventAnalysis, Opinion, RawEvent
from database.session import SessionFactory
from database.unit_of_work import (
    SqlAlchemyAttentionUnitOfWork,
    SqlAlchemyOpinionUnitOfWork,
    SqlAlchemyStateUnitOfWork,
    SqlAlchemyThesisChangeUnitOfWork,
)
from intelligence import StateUpdateService
from intelligence.services.attention_occurrence import AttentionOccurrenceService
from intelligence.services.thesis_change import ThesisChangeService
from pipeline import RecoveryReconciliationService
from resolution import AssetRecoveryService


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

    opinion_processor = OpinionProcessingService(
        OpenAIOpinionExtractor.from_settings(),
        opinion_uow,
        production_policy=production_policy,
    )
    state_updater = StateUpdateService(state_uow, effective_policy)
    reconciliation = RecoveryReconciliationService(
        AssetRecoveryService(opinion_uow),
        state_updater,
        AttentionOccurrenceService(attention_uow, effective_policy),
    )
    thesis_changes = ThesisChangeService(
        thesis_uow,
        effective_policy,
        OpenAICompatibleThesisComparator.from_settings(),
    )
    return production_policy, opinion_processor, state_updater, reconciliation, thesis_changes


def _load_target_events(investor_ids: tuple[UUID, ...]) -> tuple[RawEvent, ...]:
    with SessionFactory() as session:
        return tuple(
            session.scalars(
                select(RawEvent)
                .where(RawEvent.investor_id.in_(investor_ids))
                .order_by(RawEvent.published_time, RawEvent.id)
            ).all()
        )


def _load_analysis_candidates(
    events: tuple[RawEvent, ...],
    analysis_version: str,
) -> tuple[RawEvent, ...]:
    event_ids = tuple(event.id for event in events)
    if not event_ids:
        return ()
    with SessionFactory() as session:
        existing = {
            analysis.event_id: analysis
            for analysis in session.scalars(
                select(EventAnalysis).where(
                    EventAnalysis.event_id.in_(event_ids),
                    EventAnalysis.analysis_version == analysis_version,
                )
            ).all()
        }
    return tuple(
        event
        for event in events
        if (analysis := existing.get(event.id)) is not None and analysis.status.value == "FAILED"
    )


def _load_effective_opinion_ids(
    investor_ids: tuple[UUID, ...],
    analysis_version: str,
) -> tuple[UUID, ...]:
    with SessionFactory() as session:
        return tuple(
            session.scalars(
                select(Opinion.id)
                .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
                .where(
                    Opinion.investor_id.in_(investor_ids),
                    EventAnalysis.analysis_version == analysis_version,
                    EventAnalysis.status.in_(["SUCCESS", "PARTIALLY_RESOLVED"]),
                )
                .order_by(Opinion.generated_time, Opinion.id)
            ).all()
        )


async def run(investor_ids: tuple[UUID, ...], *, analysis_concurrency: int = 6) -> int:
    production_policy, opinion_processor, state_updater, reconciliation, thesis_changes = (
        _build_services()
    )
    events = _load_target_events(investor_ids)
    candidates = _load_analysis_candidates(events, production_policy.active_analysis_version)
    print(
        json.dumps(
            {
                "analysis_version": production_policy.active_analysis_version,
                "target_investors": [str(value) for value in investor_ids],
                "target_raw_events": len(events),
                "analysis_candidates": len(candidates),
            },
            ensure_ascii=False,
        )
    )

    analysis_statuses: Counter[str] = Counter()
    analysis_failures: list[str] = []
    semaphore = asyncio.Semaphore(analysis_concurrency)

    async def process_analysis(index: int, event: RawEvent):
        async with semaphore:
            try:
                result = await opinion_processor.process(
                    event.id,
                    analysis_spec=production_policy.active_spec,
                )
                return index, event, result, None
            except Exception as exc:  # keep the bounded batch progressing
                return index, event, None, f"{event.id}: {type(exc).__name__}: {exc}"

    analysis_results = await asyncio.gather(
        *(process_analysis(index, event) for index, event in enumerate(candidates, start=1))
    )
    for index, event, result, failure in sorted(analysis_results, key=lambda value: value[0]):
        if failure is not None:
            analysis_failures.append(failure)
            print(f"analysis_error event={event.id} detail={failure}")
            continue
        status = result.status.value
        analysis_statuses[status] += 1
        for opinion_id in result.opinion_ids:
            try:
                state_updater.update(opinion_id)
            except Exception as exc:  # keep the bounded batch progressing
                analysis_failures.append(f"{event.id}: state update {type(exc).__name__}: {exc}")
        print(f"analysis {index}/{len(candidates)} event={event.id} status={status}")

    recovery_statuses: Counter[str] = Counter()
    recovery_failures: list[str] = []
    for index, event in enumerate(candidates, start=1):
        try:
            result = reconciliation.reconcile(
                event_id=event.id,
                analysis_version=production_policy.active_analysis_version,
            )
            recovery_statuses[result.recovery.status.value] += 1
            print(
                f"reconcile {index}/{len(events)} event={event.id} "
                f"recovery={result.recovery.status.value} "
                f"attention_created={result.attention.created_count} "
                f"attention_updated={result.attention.updated_count}"
            )
        except Exception as exc:  # keep the bounded batch progressing
            recovery_failures.append(f"{event.id}: {type(exc).__name__}: {exc}")
            print(f"reconcile_error event={event.id} error={type(exc).__name__}: {exc}")

    opinion_ids = _load_effective_opinion_ids(
        investor_ids,
        production_policy.active_analysis_version,
    )
    thesis_statuses: Counter[str] = Counter()
    thesis_failures: list[str] = []
    for index, opinion_id in enumerate(opinion_ids, start=1):
        try:
            result = await thesis_changes.process(opinion_id)
            thesis_statuses["created" if result.created else "reused"] += 1
            print(
                f"thesis {index}/{len(opinion_ids)} opinion={opinion_id} "
                f"change_type={result.change_type.value} "
                f"created={result.created}"
            )
        except Exception as exc:  # keep the bounded batch progressing
            thesis_failures.append(f"{opinion_id}: {type(exc).__name__}: {exc}")
            print(f"thesis_error opinion={opinion_id} error={type(exc).__name__}: {exc}")

    summary = {
        "analysis_statuses": dict(analysis_statuses),
        "analysis_failures": analysis_failures,
        "recovery_statuses": dict(recovery_statuses),
        "recovery_failures": recovery_failures,
        "effective_opinions_seen": len(opinion_ids),
        "thesis_statuses": dict(thesis_statuses),
        "thesis_failures": thesis_failures,
    }
    print(json.dumps(summary, ensure_ascii=False))
    return 1 if analysis_failures or recovery_failures or thesis_failures else 0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--investor-id", action="append", required=True, type=UUID)
    parser.add_argument("--analysis-concurrency", type=int, default=6)
    args = parser.parse_args()
    if args.analysis_concurrency < 1 or args.analysis_concurrency > 16:
        parser.error("--analysis-concurrency must be between 1 and 16")
    raise SystemExit(
        asyncio.run(
            run(
                tuple(args.investor_id),
                analysis_concurrency=args.analysis_concurrency,
            )
        )
    )


if __name__ == "__main__":
    main()
