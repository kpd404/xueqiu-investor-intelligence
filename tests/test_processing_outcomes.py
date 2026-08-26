import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from contracts import (
    AnalysisProcessingError,
    AnalysisSpec,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    ProcessingOutcome,
    ProcessRawEventCommand,
    UnresolvedAsset,
)
from pipeline import IntelligencePipeline

SPEC = AnalysisSpec(
    analysis_version="outcome-v1",
    model_version="mock-v1",
    prompt_version="mock-prompt-v1",
    schema_version="opinion-schema-v1",
)


class PartialProcessor:
    async def process(self, event_id: object, model_version: str) -> OpinionProcessingResult:
        return OpinionProcessingResult(
            event_id=event_id,
            opinion_ids=(),
            unresolved_assets=(
                UnresolvedAsset(asset_name="Unknown", symbol="UNKNOWN", market="HK"),
            ),
            model_version=model_version,
            status=OpinionProcessingStatus.PARTIALLY_RESOLVED,
        )


class FailingProcessor:
    async def process(self, event_id: object, model_version: str) -> OpinionProcessingResult:
        raise AnalysisProcessingError("temporary extractor failure", retryable=True)


def command() -> ProcessRawEventCommand:
    return ProcessRawEventCommand(
        event_id=uuid4(),
        analysis_spec=SPEC,
        as_of=datetime(2026, 8, 25, tzinfo=UTC),
    )


def test_partial_resolution_is_a_successful_partial_outcome() -> None:
    pipeline = IntelligencePipeline(PartialProcessor(), object(), object())  # type: ignore[arg-type]

    result = asyncio.run(pipeline.process(command()))

    assert result.outcome == ProcessingOutcome.PARTIALLY_SUCCEEDED
    assert result.warnings == ()


def test_retryable_analysis_failure_has_stable_warning_fields() -> None:
    pipeline = IntelligencePipeline(FailingProcessor(), object(), object())  # type: ignore[arg-type]

    result = asyncio.run(pipeline.process(command()))

    assert result.outcome == ProcessingOutcome.RETRYABLE_FAILED
    assert result.warnings[0].retryable is True
    assert result.warnings[0].stage.value == "ANALYSIS"
