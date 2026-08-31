from collections.abc import Callable, Mapping, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    ASSET_RECOVERY_POLICY_VERSION,
    AssetRecoveryResult,
    AssetRecoveryStatus,
    AssetResolutionStatus,
    EventAnalysisStatus,
    EventAnalysisView,
    OpinionCreate,
    OpinionWriteResult,
    RawEventView,
    UnresolvedAsset,
)
from resolution.asset_resolver import AssetResolver


class RecoveryAnalysisReader(Protocol):
    def get(self, analysis_id: UUID) -> EventAnalysisView | None: ...

    def get_by_identity(
        self, event_id: UUID, analysis_version: str
    ) -> EventAnalysisView | None: ...


class RecoveryAnalysisWriter(RecoveryAnalysisReader, Protocol):
    def update_recovery(
        self,
        analysis_id: UUID,
        *,
        status: EventAnalysisStatus,
        calculated_at: datetime,
        original_unresolved_assets: Sequence[UnresolvedAsset],
        remaining_unresolved_assets: Sequence[UnresolvedAsset],
        resolved_asset_ids: Sequence[UUID],
        policy_version: str,
    ) -> EventAnalysisView: ...


class RecoveryRawEventReader(Protocol):
    def get_view(self, event_id: UUID) -> RawEventView | None: ...


class RecoveryOpinionWriter(Protocol):
    def add_many(self, commands: Sequence[OpinionCreate]) -> OpinionWriteResult: ...


class RecoveryUnitOfWork(Protocol):
    raw_events: RecoveryRawEventReader
    analyses: RecoveryAnalysisWriter
    asset_resolver: AssetResolver
    opinions: RecoveryOpinionWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


RecoveryUnitOfWorkFactory = Callable[[], RecoveryUnitOfWork]


class AssetRecoveryNotFoundError(LookupError):
    """Raised when the requested EventAnalysis or RawEvent does not exist."""


class AssetRecoveryService:
    """Re-resolve persisted asset hints without invoking an extractor."""

    def __init__(
        self,
        unit_of_work_factory: RecoveryUnitOfWorkFactory,
        *,
        policy_version: str = ASSET_RECOVERY_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._policy_version = policy_version

    def recover(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
    ) -> AssetRecoveryResult:
        if analysis_id is None and (event_id is None or not analysis_version):
            raise ValueError("analysis_id or event_id plus analysis_version is required")

        calculated_at = datetime.now(UTC)
        with self._unit_of_work_factory() as unit_of_work:
            analysis = self._find_analysis(
                unit_of_work,
                analysis_id=analysis_id,
                event_id=event_id,
                analysis_version=analysis_version,
            )
            if analysis is None:
                raise AssetRecoveryNotFoundError("event analysis not found")

            event = unit_of_work.raw_events.get_view(analysis.event_id)
            if event is None:
                raise AssetRecoveryNotFoundError(f"raw event not found: {analysis.event_id}")

            unresolved_assets = self._source_unresolved_assets(analysis.structured_output)
            if not unresolved_assets:
                unit_of_work.commit()
                return AssetRecoveryResult(
                    analysis_id=analysis.id,
                    event_id=analysis.event_id,
                    status=AssetRecoveryStatus.NO_UNRESOLVED,
                    calculated_at=calculated_at,
                    analysis_status_before=analysis.status,
                    analysis_status_after=analysis.status,
                )

            commands: list[OpinionCreate] = []
            remaining: list[UnresolvedAsset] = []
            resolved_asset_ids: list[UUID] = []
            for unresolved in unresolved_assets:
                resolution = unit_of_work.asset_resolver.resolve(unresolved.to_asset_reference())
                if resolution.status is AssetResolutionStatus.RESOLVED:
                    if not self._has_complete_semantics(unresolved):
                        remaining.append(
                            unresolved.model_copy(
                                update={
                                    "reason": "MISSING_OPINION_SEMANTICS",
                                    "candidate_asset_ids": (),
                                }
                            )
                        )
                        continue
                    if resolution.asset_id is None:
                        raise RuntimeError("resolved Asset result did not include asset_id")
                    resolved_asset_ids.append(resolution.asset_id)
                    commands.append(
                        OpinionCreate(
                            event_id=event.id,
                            analysis_id=analysis.id,
                            investor_id=event.investor_id,
                            asset_id=resolution.asset_id,
                            direction=unresolved.direction,
                            strength=unresolved.strength,
                            confidence=unresolved.confidence,
                            thesis=unresolved.thesis,
                            catalysts=unresolved.catalysts,
                            risks=unresolved.risks,
                            time_horizon=unresolved.time_horizon,
                            generated_time=analysis.generated_time,
                            model_version=analysis.spec.model_version,
                        )
                    )
                    continue

                remaining.append(
                    unresolved.model_copy(
                        update={
                            "reason": resolution.reason or resolution.status.value,
                            "candidate_asset_ids": resolution.candidate_asset_ids,
                        }
                    )
                )

            write_result = unit_of_work.opinions.add_many(commands)
            after_status = (
                EventAnalysisStatus.SUCCESS
                if not remaining and analysis.investment_related
                else EventAnalysisStatus.PARTIALLY_RESOLVED
            )
            unit_of_work.analyses.update_recovery(
                analysis.id,
                status=after_status,
                calculated_at=calculated_at,
                original_unresolved_assets=unresolved_assets,
                remaining_unresolved_assets=remaining,
                resolved_asset_ids=resolved_asset_ids,
                policy_version=self._policy_version,
            )
            unit_of_work.commit()

        status = self._result_status(
            resolved_count=len(resolved_asset_ids),
            remaining_count=len(remaining),
            created_count=write_result.created_count,
        )
        return AssetRecoveryResult(
            analysis_id=analysis.id,
            event_id=analysis.event_id,
            status=status,
            opinion_ids=write_result.opinion_ids,
            created_count=write_result.created_count,
            reused_count=len(write_result.opinion_ids) - write_result.created_count,
            resolved_asset_ids=tuple(dict.fromkeys(resolved_asset_ids)),
            unresolved_assets=tuple(remaining),
            calculated_at=calculated_at,
            analysis_status_before=analysis.status,
            analysis_status_after=after_status,
        )

    @staticmethod
    def _find_analysis(
        unit_of_work: RecoveryUnitOfWork,
        *,
        analysis_id: UUID | None,
        event_id: UUID | None,
        analysis_version: str | None,
    ) -> EventAnalysisView | None:
        if analysis_id is not None:
            return unit_of_work.analyses.get(analysis_id)
        if event_id is None or not analysis_version:
            return None
        return unit_of_work.analyses.get_by_identity(event_id, analysis_version)

    @staticmethod
    def _source_unresolved_assets(output: Mapping[str, object]) -> tuple[UnresolvedAsset, ...]:
        recovery = output.get("resolution_recovery")
        values: object = output.get("unresolved_assets", [])
        if isinstance(recovery, Mapping):
            original = recovery.get("original_unresolved_assets")
            if isinstance(original, list):
                values = original
        if not isinstance(values, list):
            return ()
        return tuple(UnresolvedAsset.model_validate(value) for value in values)

    @staticmethod
    def _has_complete_semantics(unresolved: UnresolvedAsset) -> bool:
        return (
            unresolved.direction is not None
            and unresolved.strength is not None
            and unresolved.confidence is not None
        )

    @staticmethod
    def _result_status(
        *,
        resolved_count: int,
        remaining_count: int,
        created_count: int,
    ) -> AssetRecoveryStatus:
        if remaining_count:
            return (
                AssetRecoveryStatus.PARTIALLY_RESOLVED
                if resolved_count
                else AssetRecoveryStatus.UNRESOLVED
            )
        return (
            AssetRecoveryStatus.RECOVERED
            if created_count
            else AssetRecoveryStatus.ALREADY_RECOVERED
        )
