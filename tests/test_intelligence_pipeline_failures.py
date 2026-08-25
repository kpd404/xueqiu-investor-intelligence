import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from ai.services.opinion_processing import RawEventNotFoundError
from contracts import (
    AttentionLevel,
    CoreProcessingFailureCode,
    InvestorAssetStateSnapshot,
    OpinionDirection,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    PositionStatus,
    ProcessRawEventCommand,
    StateTransitionType,
    StateUpdateResult,
)
from pipeline import CoreProcessingError, IntelligencePipeline


class MissingRawEventProcessor:
    async def process(self, event_id: object, model_version: str) -> OpinionProcessingResult:
        raise RawEventNotFoundError(f"raw event not found: {event_id}")


class StaticOpinionProcessor:
    def __init__(self, opinion_id: object) -> None:
        self._opinion_id = opinion_id

    async def process(self, event_id: object, model_version: str) -> OpinionProcessingResult:
        return OpinionProcessingResult(
            event_id=event_id,
            opinion_ids=(self._opinion_id,),
            unresolved_assets=(),
            model_version=model_version,
            status=OpinionProcessingStatus.PROCESSED,
        )


class FailingStateUpdater:
    def update(self, opinion_id: object) -> StateUpdateResult:
        raise RuntimeError("state fixture failure")


class StaticStateUpdater:
    def __init__(self, asset_id: object) -> None:
        self._asset_id = asset_id

    def update(self, opinion_id: object) -> StateUpdateResult:
        now = datetime(2026, 8, 25, tzinfo=UTC)
        snapshot = InvestorAssetStateSnapshot(
            investor_id=uuid4(),
            asset_id=self._asset_id,
            attention_level=AttentionLevel.DISCOVERED,
            direction=OpinionDirection.BULLISH,
            conviction=72,
            mention_count=1,
            position_status=PositionStatus.NO_POSITION,
            last_opinion_time=now,
            last_change_time=now,
        )
        return StateUpdateResult(
            state_id=uuid4(),
            changed=True,
            before=None,
            after=snapshot,
            transition=StateTransitionType.NEW_ATTENTION,
            applied_opinion_ids=(opinion_id,),
            source_event_ids=(uuid4(),),
        )


class FailingIntelligenceCalculator:
    def build(self, asset_id: object, as_of: object) -> object:
        raise RuntimeError("intelligence fixture failure")


class UnexpectedCalculator:
    def build(self, asset_id: object, as_of: object) -> object:
        raise AssertionError("calculator should not be called")


def command() -> ProcessRawEventCommand:
    return ProcessRawEventCommand(
        event_id=uuid4(),
        model_version="fixture-v1",
        as_of=datetime(2026, 8, 25, tzinfo=UTC),
    )


def test_raw_event_not_found_uses_typed_pipeline_error() -> None:
    pipeline = IntelligencePipeline(
        MissingRawEventProcessor(),  # type: ignore[arg-type]
        FailingStateUpdater(),
        UnexpectedCalculator(),  # type: ignore[arg-type]
    )

    with pytest.raises(CoreProcessingError) as raised:
        asyncio.run(pipeline.process(command()))

    assert raised.value.code == CoreProcessingFailureCode.RAW_EVENT_NOT_FOUND


def test_state_failure_is_structured_warning_and_stops_that_asset_path() -> None:
    opinion_id = uuid4()
    pipeline = IntelligencePipeline(
        StaticOpinionProcessor(opinion_id),  # type: ignore[arg-type]
        FailingStateUpdater(),
        UnexpectedCalculator(),  # type: ignore[arg-type]
    )

    result = asyncio.run(pipeline.process(command()))

    assert result.state_updates == ()
    assert result.affected_asset_ids == ()
    assert result.asset_intelligence_snapshots == ()
    assert result.warnings[0].code == CoreProcessingFailureCode.STATE_UPDATE_FAILED
    assert result.warnings[0].opinion_id == opinion_id


def test_intelligence_failure_is_structured_warning() -> None:
    opinion_id = uuid4()
    asset_id = uuid4()
    pipeline = IntelligencePipeline(
        StaticOpinionProcessor(opinion_id),  # type: ignore[arg-type]
        StaticStateUpdater(asset_id),  # type: ignore[arg-type]
        FailingIntelligenceCalculator(),  # type: ignore[arg-type]
    )

    result = asyncio.run(pipeline.process(command()))

    assert len(result.state_updates) == 1
    assert result.affected_asset_ids == (asset_id,)
    assert result.asset_intelligence_snapshots == ()
    assert result.warnings[0].code == CoreProcessingFailureCode.INTELLIGENCE_CALCULATION_FAILED
    assert result.warnings[0].asset_id == asset_id
