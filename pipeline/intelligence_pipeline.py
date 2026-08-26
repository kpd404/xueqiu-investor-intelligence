import inspect
from typing import Protocol
from uuid import UUID

from contracts import (
    AnalysisProcessingError,
    AnalysisSpec,
    AssetIntelligenceSnapshot,
    CoreProcessingFailureCode,
    CoreProcessingResult,
    CoreProcessingWarning,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    ProcessingOutcome,
    ProcessingStage,
    ProcessRawEventCommand,
    RawEventNotFoundError,
    StateUpdateResult,
)


class OpinionProcessor(Protocol):
    async def process(
        self,
        event_id: UUID,
        model_version: str,
        *,
        analysis_spec: AnalysisSpec | None = None,
    ) -> OpinionProcessingResult: ...


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
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.event_id = event_id
        self.retryable = retryable


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
        spec = command.resolved_analysis_spec
        try:
            opinion_result = await self._process_opinions(command.event_id, spec)
        except RawEventNotFoundError as exc:
            raise CoreProcessingError(
                CoreProcessingFailureCode.RAW_EVENT_NOT_FOUND,
                command.event_id,
                str(exc),
                retryable=False,
            ) from exc
        except AnalysisProcessingError as exc:
            warning = CoreProcessingWarning(
                code=CoreProcessingFailureCode.ANALYSIS_FAILED,
                stage=ProcessingStage.ANALYSIS,
                retryable=exc.retryable,
                message=str(exc),
            )
            return self._result(
                command,
                spec,
                opinion_processing_status=OpinionProcessingStatus.FAILED,
                opinion_ids=(),
                unresolved_assets=(),
                state_updates=(),
                affected_asset_ids=(),
                snapshots=(),
                warnings=(warning,),
            )

        warnings: list[CoreProcessingWarning] = []
        state_updates: list[StateUpdateResult] = []
        for opinion_id in sorted(opinion_result.opinion_ids, key=lambda value: value.int):
            try:
                state_updates.append(self._state_updater.update(opinion_id))
            except Exception as exc:
                self._append_stage_warning(
                    warnings,
                    exc,
                    code=CoreProcessingFailureCode.STATE_UPDATE_FAILED,
                    stage=ProcessingStage.STATE_UPDATE,
                    opinion_id=opinion_id,
                )

        affected_asset_ids = tuple(
            sorted({update.after.asset_id for update in state_updates}, key=lambda value: value.int)
        )
        snapshots: list[AssetIntelligenceSnapshot] = []
        for asset_id in affected_asset_ids:
            try:
                snapshots.append(self._intelligence_calculator.build(asset_id, command.as_of))
            except Exception as exc:
                self._append_stage_warning(
                    warnings,
                    exc,
                    code=CoreProcessingFailureCode.INTELLIGENCE_CALCULATION_FAILED,
                    stage=ProcessingStage.INTELLIGENCE,
                    asset_id=asset_id,
                )

        return self._result(
            command,
            spec,
            opinion_processing_status=opinion_result.status,
            opinion_ids=opinion_result.opinion_ids,
            unresolved_assets=opinion_result.unresolved_assets,
            state_updates=tuple(state_updates),
            affected_asset_ids=affected_asset_ids,
            snapshots=tuple(snapshots),
            warnings=tuple(warnings),
        )

    async def _process_opinions(
        self,
        event_id: UUID,
        spec: AnalysisSpec,
    ) -> OpinionProcessingResult:
        process = self._opinion_processor.process
        parameters = inspect.signature(process).parameters
        if "analysis_spec" in parameters:
            return await process(event_id, spec.model_version, analysis_spec=spec)
        # Compatibility for pre-1F test doubles and callers.
        return await process(event_id, spec.model_version)

    @staticmethod
    def _append_stage_warning(
        warnings: list[CoreProcessingWarning],
        error: Exception,
        *,
        code: CoreProcessingFailureCode,
        stage: ProcessingStage,
        opinion_id: UUID | None = None,
        asset_id: UUID | None = None,
    ) -> None:
        if not isinstance(error, (RuntimeError, LookupError, TimeoutError, ConnectionError)):
            raise error
        warnings.append(
            CoreProcessingWarning(
                code=code,
                stage=stage,
                retryable=not isinstance(error, LookupError),
                opinion_id=opinion_id,
                asset_id=asset_id,
                message=f"{type(error).__name__}: {error}",
            )
        )

    @classmethod
    def _result(
        cls,
        command: ProcessRawEventCommand,
        spec: AnalysisSpec,
        *,
        opinion_processing_status: OpinionProcessingStatus,
        opinion_ids: tuple[UUID, ...],
        unresolved_assets: tuple[object, ...],
        state_updates: tuple[StateUpdateResult, ...],
        affected_asset_ids: tuple[UUID, ...],
        snapshots: tuple[AssetIntelligenceSnapshot, ...],
        warnings: tuple[CoreProcessingWarning, ...],
    ) -> CoreProcessingResult:
        outcome = cls._outcome(
            opinion_processing_status,
            unresolved_assets,
            state_updates,
            snapshots,
            warnings,
        )
        return CoreProcessingResult(
            event_id=command.event_id,
            model_version=spec.model_version,
            analysis_spec=spec,
            as_of=command.as_of,
            opinion_processing_status=opinion_processing_status,
            opinion_ids=opinion_ids,
            state_updates=state_updates,
            affected_asset_ids=affected_asset_ids,
            asset_intelligence_snapshots=snapshots,
            unresolved_assets=unresolved_assets,
            warnings=warnings,
            outcome=outcome,
        )

    @staticmethod
    def _outcome(
        opinion_status: OpinionProcessingStatus,
        unresolved_assets: tuple[object, ...],
        state_updates: tuple[StateUpdateResult, ...],
        snapshots: tuple[AssetIntelligenceSnapshot, ...],
        warnings: tuple[CoreProcessingWarning, ...],
    ) -> ProcessingOutcome:
        if not warnings:
            if opinion_status == OpinionProcessingStatus.FAILED:
                return ProcessingOutcome.PERMANENTLY_FAILED
            if opinion_status == OpinionProcessingStatus.PARTIALLY_RESOLVED or unresolved_assets:
                return ProcessingOutcome.PARTIALLY_SUCCEEDED
            return ProcessingOutcome.SUCCEEDED
        if state_updates or snapshots:
            return ProcessingOutcome.PARTIALLY_SUCCEEDED
        if any(warning.retryable for warning in warnings):
            return ProcessingOutcome.RETRYABLE_FAILED
        return ProcessingOutcome.PERMANENTLY_FAILED
