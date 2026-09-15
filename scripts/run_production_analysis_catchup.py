"""Run the remaining missing production analyses without downstream recovery."""

from __future__ import annotations

import asyncio
import json
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from pathlib import Path
from uuid import UUID

from sqlalchemy import select

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import func  # noqa: E402

from ai import OpenAIOpinionExtractor, OpinionProcessingService  # noqa: E402
from backend.app.api.dependencies import _read_only_session  # noqa: E402
from config import get_production_analysis_policy, get_settings  # noqa: E402
from contracts import AnalysisSpec, RawEventView, current_author_analysis_view  # noqa: E402
from database.models import (  # noqa: E402
    CollectionObservation,
    CollectionRun,
    EventAnalysis,
    Investor,
    Opinion,
    RawEvent,
)
from database.session import SessionFactory  # noqa: E402
from database.unit_of_work import SqlAlchemyOpinionUnitOfWork  # noqa: E402
from pipeline import (  # noqa: E402
    AnalysisBackfillRunner,
    AnalysisRecoveryCandidate,
    AnalysisRecoveryProgress,
)

EXPECTED_IDENTITY = {
    "analysis_version": (
        "opinion-analysis-v3:794dc66ba5096337c3e2c0f85554887352f476e5f52ad55363b6b9420d5502a9"
    ),
    "provider_id": "deepseek",
    "model_version": "deepseek-v4-flash",
    "analysis_policy_version": "opinion-analysis-v3",
    "prompt_version": "opinion-extraction-v5",
    "schema_version": "opinion-extraction-result-v2",
}

VALIDATION_EVENT_IDS = {
    UUID(value)
    for value in (
        "020fa5fd-af80-429a-a0d6-8d2802b84535",
        "0c73324e-23b6-4fc9-b956-bd4da1dd941e",
        "1b5b9620-bf5d-4364-8e3a-4aa18b8b74b8",
        "011cf12a-109f-405e-8f99-3ca29ae1b6c2",
        "00b31349-e4cc-4e53-9180-2d9171df6f4e",
        "1f4225cb-d97d-4a96-9ad6-8d7af4b7bd10",
        "41f90976-a478-431c-8fa1-1c308bb90109",
        "86bb5b8b-4cf2-498f-9ecb-90f055109c0d",
    )
}

KNOWN_FAILED_EVENT_ID = UUID("ae13276c-69ac-46eb-8672-2b3b3a854f9b")


def _value(value: object) -> object:
    return getattr(value, "value", value)


def _identity(policy: object) -> dict[str, str]:
    spec: AnalysisSpec = policy.active_spec
    return {
        "analysis_version": policy.active_analysis_version,
        "provider_id": spec.provider_id,
        "model_version": spec.model_version,
        "analysis_policy_version": spec.analysis_policy_version,
        "prompt_version": spec.prompt_version,
        "schema_version": spec.schema_version,
    }


def _event_view(event: RawEvent) -> RawEventView:
    return RawEventView(
        id=event.id,
        investor_id=event.investor_id,
        event_type=event.event_type,
        source=event.source,
        url=event.url,
        published_time=event.published_time,
        content=event.content,
        raw_data=event.raw_data,
        hash=event.hash,
        collected_time=event.collected_time,
    )


def missing_event_ids(
    raw_event_ids: Iterable[UUID],
    current_analysis_event_ids: Iterable[UUID],
) -> tuple[UUID, ...]:
    """Return missing event identities without join multiplicity."""

    current_ids = set(current_analysis_event_ids)
    return tuple(event_id for event_id in raw_event_ids if event_id not in current_ids)


def preflight() -> tuple[
    object,
    dict[str, str],
    tuple[UUID, ...],
    dict[UUID, int],
    int,
]:
    policy = get_production_analysis_policy()
    identity = _identity(policy)
    if identity != EXPECTED_IDENTITY:
        raise RuntimeError(f"PRODUCTION_IDENTITY_MISMATCH:{identity}")

    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_api_key.strip():
        raise RuntimeError("LLM_CREDENTIAL_MISSING")

    with _read_only_session() as session:
        events = {event.id: event for event in session.scalars(select(RawEvent))}
        current_rows = list(
            session.scalars(
                select(EventAnalysis).where(
                    EventAnalysis.analysis_version == policy.active_analysis_version
                )
            )
        )
        current_analysis: dict[UUID, EventAnalysis] = {}
        duplicate_event_ids: set[UUID] = set()
        for analysis in current_rows:
            if analysis.event_id in current_analysis:
                duplicate_event_ids.add(analysis.event_id)
            current_analysis[analysis.event_id] = analysis
        orphan_analysis = sum(analysis.event_id not in events for analysis in current_rows)
        missing_ids = missing_event_ids(events, current_analysis)
        if (
            len(events) != 1593
            or len(current_analysis) != 1490
            or len(missing_ids) != 103
            or duplicate_event_ids
            or orphan_analysis
        ):
            raise RuntimeError(
                "COHORT_DRIFT:"
                f"raw={len(events)}:"
                f"current={len(current_analysis)}:"
                f"missing={len(missing_ids)}:"
                f"duplicates={len(duplicate_event_ids)}:"
                f"orphans={orphan_analysis}"
            )
        if VALIDATION_EVENT_IDS & set(missing_ids):
            raise RuntimeError("VALIDATION_BATCH_STILL_MISSING")
        if KNOWN_FAILED_EVENT_ID in set(missing_ids):
            raise RuntimeError("KNOWN_FAILED_ANALYSIS_ENTERED_MISSING_COHORT")

        observed_ids = set(
            session.scalars(
                select(CollectionObservation.raw_event_id).where(
                    CollectionObservation.raw_event_id.in_(missing_ids)
                )
            )
        )
        if observed_ids != set(missing_ids):
            raise RuntimeError("MISSING_COHORT_PROVENANCE_INCOMPLETE")

        content_lengths: dict[UUID, int] = {}
        for event_id in missing_ids:
            content_view = current_author_analysis_view(_event_view(events[event_id]))
            content_lengths[event_id] = len(content_view.content)
        before_target_opinion_count = int(
            session.scalar(
                select(func.count()).select_from(Opinion).where(Opinion.event_id.in_(missing_ids))
            )
            or 0
        )

    return policy, identity, missing_ids, content_lengths, before_target_opinion_count


async def run_catchup() -> dict[str, object]:
    policy, identity, missing_ids, content_lengths, before_target_opinion_count = preflight()
    extractor = OpenAIOpinionExtractor.from_settings()
    if extractor.analysis_spec != policy.active_spec:
        raise RuntimeError("EXTRACTOR_SPEC_MISMATCH")

    processor = OpinionProcessingService(
        extractor,
        lambda: SqlAlchemyOpinionUnitOfWork(SessionFactory),
        production_policy=policy,
    )
    errors: dict[UUID, Exception] = {}
    results: dict[UUID, object] = {}
    catastrophic_stop = asyncio.Event()

    async def process_missing(event_id: UUID) -> object:
        if catastrophic_stop.is_set():
            raise RuntimeError("CATCHUP_ABORTED_AFTER_CATASTROPHIC_FAILURE")
        try:
            result = await processor.process(event_id, analysis_spec=policy.active_spec)
        except Exception as exc:
            errors[event_id] = exc
            code = str(_value(getattr(exc, "code", "")))
            if code in {
                "AUTHENTICATION_ERROR",
                "CONFIGURATION_ERROR",
                "UNSUPPORTED_CAPABILITY",
            }:
                catastrophic_stop.set()
            raise
        results[event_id] = result
        return result

    def progress(progress: AnalysisRecoveryProgress) -> None:
        print(
            json.dumps(
                {
                    "phase": "production_analysis_catchup",
                    "attempted": progress.processed,
                    "completed": progress.success,
                    "remaining": progress.remaining,
                    "failed": progress.failed,
                    "provider_calls": extractor.request_count,
                    "retry_calls": extractor.retry_count,
                },
                ensure_ascii=False,
            ),
            flush=True,
        )

    summary = await AnalysisBackfillRunner(
        process_missing,
        batch_size=10,
        max_concurrency=6,
    ).run(
        tuple(
            AnalysisRecoveryCandidate(event_id=event_id, status=None) for event_id in missing_ids
        ),
        progress_callback=progress,
    )

    with _read_only_session() as session:
        current = list(
            session.scalars(
                select(EventAnalysis).where(
                    EventAnalysis.analysis_version == policy.active_analysis_version
                )
            )
        )
        target_analysis = {
            analysis.event_id: analysis
            for analysis in session.scalars(
                select(EventAnalysis).where(
                    EventAnalysis.event_id.in_(missing_ids),
                    EventAnalysis.analysis_version == policy.active_analysis_version,
                )
            )
        }
        target_opinions = list(
            session.scalars(select(Opinion).where(Opinion.event_id.in_(missing_ids)))
        )
        investors = {investor.id: investor for investor in session.scalars(select(Investor))}
        observations = list(
            session.scalars(
                select(CollectionObservation).where(
                    CollectionObservation.raw_event_id.in_(missing_ids)
                )
            )
        )
        runs = {
            run.id: run
            for run in session.scalars(
                select(CollectionRun).where(
                    CollectionRun.id.in_(
                        {observation.collection_run_id for observation in observations}
                    )
                )
            )
        }
        raw_events = {
            event.id: event
            for event in session.scalars(select(RawEvent).where(RawEvent.id.in_(missing_ids)))
        }

    status_distribution = Counter(
        str(_value(analysis.status)) for analysis in target_analysis.values()
    )
    all_status_distribution = Counter(str(_value(analysis.status)) for analysis in current)
    opinions_by_event: dict[UUID, list[Opinion]] = defaultdict(list)
    for opinion in target_opinions:
        opinions_by_event[opinion.event_id].append(opinion)

    investor_distribution: dict[str, Counter[str]] = defaultdict(Counter)
    extracted_mentions = 0
    resolved_mentions = len(target_opinions)
    unresolved_mentions = 0
    unresolved_names: Counter[str] = Counter()
    per_event = []
    for event_id in sorted(missing_ids, key=lambda value: value.int):
        event = raw_events[event_id]
        analysis = target_analysis.get(event_id)
        structured = analysis.structured_output if analysis is not None else {}
        extracted = (
            len(structured.get("opinions", ())) + len(structured.get("unresolved_assets", ()))
            if isinstance(structured, dict)
            else 0
        )
        unresolved = structured.get("unresolved_assets", ()) if isinstance(structured, dict) else ()
        extracted_mentions += extracted
        unresolved_mentions += len(unresolved)
        for item in unresolved:
            if isinstance(item, dict) and item.get("asset_name"):
                unresolved_names[str(item["asset_name"])] += 1
        status = str(_value(analysis.status)) if analysis is not None else "MISSING"
        investor_name = investors[event.investor_id].name
        investor_distribution[investor_name][status] += 1
        per_event.append(
            {
                "raw_event_id": str(event_id),
                "investor": investor_name,
                "content_length": content_lengths[event_id],
                "provider_attempts": 1 if extractor.retry_count == 0 else None,
                "analysis_status": status,
                "event_analysis_id": str(analysis.id) if analysis is not None else None,
                "investment_related": (
                    analysis.investment_related if analysis is not None else None
                ),
                "extracted_asset_mention_count": extracted,
                "resolved_opinion_count": len(opinions_by_event[event_id]),
                "unresolved_asset_count": len(unresolved),
                "error_code": analysis.error_code if analysis is not None else None,
            }
        )

    return {
        "identity": identity,
        "target_missing_events": len(missing_ids),
        "summary": {
            "attempted": summary.attempted,
            "completed": summary.success,
            "failed": summary.failed,
            "remaining": 0,
            "failure_codes": dict(summary.failure_codes),
        },
        "provider": {
            "primary_calls": extractor.request_count - extractor.retry_count,
            "retry_calls": extractor.retry_count,
            "total_attempts": extractor.request_count,
            "max_attempts_per_event": 1 if extractor.retry_count == 0 else None,
            "configured_max_attempts_per_event": 3,
        },
        "target_status_distribution": dict(status_distribution),
        "all_current_status_distribution": dict(all_status_distribution),
        "investor_distribution": {
            name: dict(counter) for name, counter in sorted(investor_distribution.items())
        },
        "post_analysis_asset_audit": {
            "investment_related_events": sum(
                item["investment_related"] is True for item in per_event
            ),
            "extracted_asset_mentions": extracted_mentions,
            "resolved_mentions": resolved_mentions,
            "unresolved_mentions": unresolved_mentions,
            "new_unresolved_asset_strings": dict(unresolved_names),
        },
        "provenance_mode_counts": {
            mode: len(
                {
                    observation.raw_event_id
                    for observation in observations
                    if str(_value(runs[observation.collection_run_id].collection_mode)) == mode
                }
            )
            for mode in sorted({str(_value(run.collection_mode)) for run in runs.values()})
        },
        "before_target_opinion_count": before_target_opinion_count,
        "new_target_opinion_count": max(
            0,
            len(target_opinions) - before_target_opinion_count,
        ),
        "per_event": per_event,
        "errors": {
            str(event_id): {
                "type": type(error).__name__,
                "code": str(_value(getattr(error, "code", ""))) or None,
                "retryable": bool(getattr(error, "retryable", False)),
            }
            for event_id, error in errors.items()
        },
    }


def main() -> int:
    try:
        result = asyncio.run(run_catchup())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "phase": "CATCHUP_ABORTED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print("CATCHUP_RESULT=" + json.dumps(result, ensure_ascii=False))
    return 1 if result["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
