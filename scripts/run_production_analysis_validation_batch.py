"""Run the explicitly approved eight-event production-analysis validation batch.

This is orchestration only: analysis semantics remain in the existing
AnalysisBackfillRunner and OpinionProcessingService. No downstream recovery
is part of this command.
"""

from __future__ import annotations

import asyncio
import json
import sys
from collections import defaultdict
from pathlib import Path
from uuid import UUID

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from sqlalchemy import select  # noqa: E402

from ai import OpenAIOpinionExtractor, OpinionProcessingService  # noqa: E402
from backend.app.api.dependencies import _read_only_session  # noqa: E402
from config import get_production_analysis_policy, get_settings  # noqa: E402
from contracts import (  # noqa: E402
    AnalysisSpec,
    RawEventView,
    current_author_analysis_view,
)
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

TARGET_EVENT_IDS = (
    UUID("020fa5fd-af80-429a-a0d6-8d2802b84535"),
    UUID("0c73324e-23b6-4fc9-b956-bd4da1dd941e"),
    UUID("1b5b9620-bf5d-4364-8e3a-4aa18b8b74b8"),
    UUID("011cf12a-109f-405e-8f99-3ca29ae1b6c2"),
    UUID("00b31349-e4cc-4e53-9180-2d9171df6f4e"),
    UUID("1f4225cb-d97d-4a96-9ad6-8d7af4b7bd10"),
    UUID("41f90976-a478-431c-8fa1-1c308bb90109"),
    UUID("86bb5b8b-4cf2-498f-9ecb-90f055109c0d"),
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


def _value(value: object) -> object:
    return getattr(value, "value", value)


def _raw_event_view(event: RawEvent) -> RawEventView:
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


def preflight() -> tuple[object, dict[str, object], dict[UUID, object]]:
    policy = get_production_analysis_policy()
    spec: AnalysisSpec = policy.active_spec
    identity = {
        "analysis_version": policy.active_analysis_version,
        "provider_id": spec.provider_id,
        "model_version": spec.model_version,
        "analysis_policy_version": spec.analysis_policy_version,
        "prompt_version": spec.prompt_version,
        "schema_version": spec.schema_version,
    }
    if identity != EXPECTED_IDENTITY:
        raise RuntimeError(f"PRODUCTION_IDENTITY_MISMATCH:{identity}")

    settings = get_settings()
    if not settings.llm_api_key or not settings.llm_api_key.strip():
        raise RuntimeError("LLM_CREDENTIAL_MISSING")

    with _read_only_session() as session:
        events = {event.id: event for event in session.scalars(select(RawEvent))}
        current: dict[UUID, list[EventAnalysis]] = defaultdict(list)
        for analysis in session.scalars(
            select(EventAnalysis).where(EventAnalysis.analysis_version == spec.analysis_version)
        ):
            current[analysis.event_id].append(analysis)
        missing = [event_id for event_id in TARGET_EVENT_IDS if not current.get(event_id)]
        missing_count = len(events) - len(current)
        duplicate_events = sum(len(rows) > 1 for rows in current.values())
        orphan_analysis = sum(
            analysis.event_id not in events
            for analysis in session.scalars(
                select(EventAnalysis).where(EventAnalysis.analysis_version == spec.analysis_version)
            )
        )
        if len(events) != 1593 or len(current) != 1482 or missing_count != 111:
            raise RuntimeError(
                f"COHORT_DRIFT:raw={len(events)}:current={len(current)}:missing={missing_count}"
            )
        if len(missing) != len(TARGET_EVENT_IDS):
            raise RuntimeError("TARGET_ALREADY_HAS_CURRENT_ANALYSIS")
        if duplicate_events or orphan_analysis:
            raise RuntimeError(
                f"ANALYSIS_ANOMALY:duplicates={duplicate_events}:orphans={orphan_analysis}"
            )

        target_events = {event_id: events[event_id] for event_id in TARGET_EVENT_IDS}
        observations = list(
            session.scalars(
                select(CollectionObservation).where(
                    CollectionObservation.raw_event_id.in_(TARGET_EVENT_IDS)
                )
            )
        )
        observed_ids = {observation.raw_event_id for observation in observations}
        if observed_ids != set(TARGET_EVENT_IDS):
            raise RuntimeError("TARGET_PROVENANCE_MISSING")

        ready: dict[UUID, object] = {}
        for event_id, event in target_events.items():
            ready[event_id] = current_author_analysis_view(_raw_event_view(event))

    return policy, identity, ready


async def run_batch() -> dict[str, object]:
    policy, identity, ready = preflight()
    extractor = OpenAIOpinionExtractor.from_settings()
    if extractor.analysis_spec != policy.active_spec:
        raise RuntimeError("EXTRACTOR_SPEC_MISMATCH")

    processor = OpinionProcessingService(
        extractor,
        lambda: SqlAlchemyOpinionUnitOfWork(SessionFactory),
        production_policy=policy,
    )
    outcomes: dict[UUID, object] = {}
    errors: dict[UUID, Exception] = {}

    async def process_missing(event_id: UUID) -> object:
        try:
            result = await processor.process(event_id, analysis_spec=policy.active_spec)
        except Exception as exc:
            errors[event_id] = exc
            raise
        outcomes[event_id] = result
        return result

    def progress(progress: AnalysisRecoveryProgress) -> None:
        print(
            json.dumps(
                {
                    "phase": "validation_batch",
                    "attempted": progress.processed,
                    "completed": progress.success,
                    "remaining": progress.remaining,
                    "success": progress.success,
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
        batch_size=8,
        max_concurrency=6,
    ).run(
        tuple(
            AnalysisRecoveryCandidate(event_id=event_id, status=None)
            for event_id in TARGET_EVENT_IDS
        ),
        progress_callback=progress,
    )

    with _read_only_session() as session:
        event_rows = {
            event.id: event
            for event in session.scalars(select(RawEvent).where(RawEvent.id.in_(TARGET_EVENT_IDS)))
        }
        investor_rows = {investor.id: investor for investor in session.scalars(select(Investor))}
        analysis_rows = {
            analysis.event_id: analysis
            for analysis in session.scalars(
                select(EventAnalysis).where(
                    EventAnalysis.event_id.in_(TARGET_EVENT_IDS),
                    EventAnalysis.analysis_version == policy.active_analysis_version,
                )
            )
        }
        opinion_rows = list(
            session.scalars(select(Opinion).where(Opinion.event_id.in_(TARGET_EVENT_IDS)))
        )
        observation_rows = list(
            session.scalars(
                select(CollectionObservation).where(
                    CollectionObservation.raw_event_id.in_(TARGET_EVENT_IDS)
                )
            )
        )
        run_rows = {
            run.id: run
            for run in session.scalars(
                select(CollectionRun).where(
                    CollectionRun.id.in_(
                        {observation.collection_run_id for observation in observation_rows}
                    )
                )
            )
        }

    observations_by_event: dict[UUID, list[dict[str, object]]] = defaultdict(list)
    for observation in observation_rows:
        run = run_rows[observation.collection_run_id]
        observations_by_event[observation.raw_event_id].append(
            {
                "collection_mode": str(_value(run.collection_mode)),
                "collection_run_id": str(run.id),
                "ingest_disposition": observation.ingest_disposition,
            }
        )
    opinions_by_event: dict[UUID, list[Opinion]] = defaultdict(list)
    for opinion in opinion_rows:
        opinions_by_event[opinion.event_id].append(opinion)

    per_event = []
    for event_id in TARGET_EVENT_IDS:
        event = event_rows[event_id]
        analysis = analysis_rows.get(event_id)
        structured = analysis.structured_output if analysis is not None else {}
        extracted = (
            len(structured.get("opinions", ())) + len(structured.get("unresolved_assets", ()))
            if isinstance(structured, dict)
            else 0
        )
        per_event.append(
            {
                "raw_event_id": str(event_id),
                "investor": investor_rows[event.investor_id].name,
                "content_length": len(ready[event_id].content),
                "provenance": observations_by_event[event_id],
                "provider_attempts": 1 if extractor.retry_count == 0 else None,
                "analysis_status": (str(_value(analysis.status)) if analysis is not None else None),
                "event_analysis_id": str(analysis.id) if analysis is not None else None,
                "investment_related": (
                    analysis.investment_related if analysis is not None else None
                ),
                "extracted_asset_mention_count": extracted,
                "unresolved_asset_count": (
                    len(structured.get("unresolved_assets", ()))
                    if isinstance(structured, dict)
                    else 0
                ),
                "opinion_count": len(opinions_by_event[event_id]),
                "error_code": analysis.error_code
                if analysis is not None
                else (
                    str(_value(getattr(errors.get(event_id), "code", None)))
                    if event_id in errors
                    else None
                ),
            }
        )

    return {
        "identity": identity,
        "target_event_count": len(TARGET_EVENT_IDS),
        "summary": {
            "attempted": summary.attempted,
            "success": summary.success,
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
        "per_event": per_event,
    }


def main() -> int:
    try:
        result = asyncio.run(run_batch())
    except Exception as exc:
        print(
            json.dumps(
                {
                    "phase": "VALIDATION_BATCH_ABORTED",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1
    print("VALIDATION_RESULT=" + json.dumps(result, ensure_ascii=False))
    return 1 if result["summary"]["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
