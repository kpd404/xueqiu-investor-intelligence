from typing import Protocol
from uuid import UUID

from ai.services.opinion_processing import RawEventNotFoundError
from contracts import (
    AssetIntelligenceSnapshot,
    CoreProcessingFailureCode,
    CoreProcessingResult,
    CoreProcessingWarning,
    OpinionProcessingResult,
    ProcessRawEventCommand,
    StateUpdateResult,
)


class OpinionProcessor(Protocol):
    async def process(self, event_id: UUID, model_version: str) -> OpinionProcessingResult: ...


class StateUpdater(Protocol):
    def update(self, opinion_id: UUID) -> StateUpdateResult: ...


class AssetIntelligenceCalculator(Protocol):
    def build(self, asset_id: UUID, as_of: object) -> AssetIntelligenceSnapshot: ...


class CoreProcessingError(RuntimeError):
    def __init__(
        self,
        code: CoreProcessingFailureCode,
        event_id: UUID,
        message: str,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.event_id = event_id


class IntelligencePipeline:
    """Application-level coordinator with no domain or persistence logic."""

    def __init__(
        self,
        opinion_processor: OpinionProcessor,
        state_updater: StateUpdater,
        intelligence_calculator: AssetIntelligenceCalculator,
    ) -> None:
        self._opinion_processor = opinion_processor
        self._state_updater = state_updater
        self._intelligence_calculator = intelligence_calculator

    async def process(self, command: ProcessRawEventCommand) -> CoreProcessingResult:
        try:
            opinion_result = await self._opinion_processor.process(
                command.event_id,
                command.model_version,
            )
        except RawEventNotFoundError as exc:
            raise CoreProcessingError(
                CoreProcessingFailureCode.RAW_EVENT_NOT_FOUND,
                command.event_id,
                str(exc),
            ) from exc

        warnings: list[CoreProcessingWarning] = []
        state_updates: list[StateUpdateResult] = []
        for opinion_id in sorted(opinion_result.opinion_ids, key=lambda value: value.int):
            try:
                state_updates.append(self._state_updater.update(opinion_id))
            except Exception as exc:
                warnings.append(
                    CoreProcessingWarning(
                        code=CoreProcessingFailureCode.STATE_UPDATE_FAILED,
                        opinion_id=opinion_id,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )

        affected_asset_ids = tuple(
            sorted({update.after.asset_id for update in state_updates}, key=lambda value: value.int)
        )
        snapshots: list[AssetIntelligenceSnapshot] = []
        for asset_id in affected_asset_ids:
            try:
                snapshots.append(self._intelligence_calculator.build(asset_id, command.as_of))
            except Exception as exc:
                warnings.append(
                    CoreProcessingWarning(
                        code=CoreProcessingFailureCode.INTELLIGENCE_CALCULATION_FAILED,
                        asset_id=asset_id,
                        message=f"{type(exc).__name__}: {exc}",
                    )
                )

        return CoreProcessingResult(
            event_id=command.event_id,
            model_version=command.model_version,
            as_of=command.as_of,
            opinion_processing_status=opinion_result.status,
            opinion_ids=opinion_result.opinion_ids,
            state_updates=tuple(state_updates),
            affected_asset_ids=affected_asset_ids,
            asset_intelligence_snapshots=tuple(snapshots),
            unresolved_assets=opinion_result.unresolved_assets,
            warnings=tuple(warnings),
        )
