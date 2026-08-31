from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from ai.extractors.base import OpinionExtractor
from contracts import (
    AnalysisProcessingError,
    AnalysisSpec,
    AssetReference,
    AssetResolutionResult,
    AssetResolutionStatus,
    EventAnalysisCreate,
    EventAnalysisStatus,
    EventAnalysisView,
    OpinionCreate,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    OpinionWriteResult,
    RawEventNotFoundError,
    RawEventView,
    UnresolvedAsset,
)


class ExtractorModelVersionMismatchError(ValueError):
    pass


class RawEventReader(Protocol):
    def get_view(self, event_id: UUID) -> RawEventView | None: ...


class AssetView(Protocol):
    id: UUID


class AssetReader(Protocol):
    def get_by_market_symbol(self, market: str, symbol: str) -> AssetView | None: ...


class AssetResolverPort(Protocol):
    def resolve(self, reference: AssetReference) -> AssetResolutionResult: ...


class EventAnalysisReader(Protocol):
    def get_by_identity(
        self, event_id: UUID, analysis_version: str
    ) -> EventAnalysisView | None: ...


class EventAnalysisWriter(EventAnalysisReader, Protocol):
    def save(self, command: EventAnalysisCreate) -> EventAnalysisView: ...


class OpinionWriter(Protocol):
    def add_many(self, commands: Sequence[OpinionCreate]) -> OpinionWriteResult: ...

    def list_by_event(self, event_id: UUID) -> list[object]: ...


class OpinionUnitOfWork(Protocol):
    raw_events: RawEventReader
    assets: AssetReader
    asset_resolver: AssetResolverPort
    analyses: EventAnalysisWriter
    opinions: OpinionWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


OpinionUnitOfWorkFactory = Callable[[], OpinionUnitOfWork]


def utc_now() -> datetime:
    return datetime.now(UTC)


class OpinionProcessingService:
    """Persist one complete, retry-aware analysis lifecycle without state logic."""

    def __init__(
        self,
        extractor: OpinionExtractor,
        unit_of_work_factory: OpinionUnitOfWorkFactory,
    ) -> None:
        self._extractor = extractor
        self._unit_of_work_factory = unit_of_work_factory

    async def process(
        self,
        event_id: UUID,
        model_version: str | None = None,
        *,
        analysis_spec: AnalysisSpec | None = None,
    ) -> OpinionProcessingResult:
        spec = analysis_spec or AnalysisSpec.from_model_version(model_version or "")
        if model_version is not None and model_version.strip() != spec.model_version:
            raise ValueError("model_version must match analysis_spec.model_version")

        with self._unit_of_work_factory() as read_unit_of_work:
            event = read_unit_of_work.raw_events.get_view(event_id)
            existing = read_unit_of_work.analyses.get_by_identity(event_id, spec.analysis_version)
            existing_opinion_ids = tuple(
                opinion.id for opinion in read_unit_of_work.opinions.list_by_event(event_id)
            )
        if event is None:
            raise RawEventNotFoundError(f"raw event not found: {event_id}")

        if existing is not None and existing.status != EventAnalysisStatus.FAILED:
            return self._result_from_existing(existing, event.id, existing_opinion_ids)

        try:
            extraction = await self._extractor.extract(event)
            self._validate_extraction(extraction_model_version=extraction.model_version, spec=spec)
            if extraction.analysis_spec is not None and extraction.analysis_spec != spec:
                raise ExtractorModelVersionMismatchError(
                    "extractor analysis_spec does not match the processing request"
                )
        except Exception as exc:
            self._persist_failure(event.id, spec, exc)
            retryable = getattr(
                exc,
                "retryable",
                not isinstance(exc, ExtractorModelVersionMismatchError),
            )
            error_code = getattr(exc, "code", type(exc).__name__)
            raise AnalysisProcessingError(
                f"analysis failed: {type(exc).__name__}: {exc}",
                retryable=retryable,
                error_code=str(error_code),
            ) from exc

        now = utc_now()
        unresolved_assets: list[UnresolvedAsset] = [
            UnresolvedAsset.from_hint(hint) for hint in getattr(extraction, "unresolved_assets", ())
        ]
        commands: list[OpinionCreate] = []
        with self._unit_of_work_factory() as write_unit_of_work:
            persisted_event = write_unit_of_work.raw_events.get_view(event_id)
            if persisted_event is None:
                raise RawEventNotFoundError(f"raw event not found: {event_id}")

            for extracted_opinion in extraction.opinions:
                resolution = write_unit_of_work.asset_resolver.resolve(
                    extracted_opinion.to_asset_reference()
                )
                if resolution.status is not AssetResolutionStatus.RESOLVED:
                    unresolved_assets.append(
                        UnresolvedAsset.from_extraction(
                            extracted_opinion,
                            reason=resolution.reason or resolution.status.value,
                            candidate_asset_ids=resolution.candidate_asset_ids,
                        )
                    )
                    continue

                asset_id = resolution.asset_id
                if asset_id is None:
                    raise RuntimeError("resolved Asset result did not include asset_id")

                commands.append(
                    OpinionCreate(
                        event_id=persisted_event.id,
                        analysis_id=None,
                        investor_id=persisted_event.investor_id,
                        asset_id=asset_id,
                        direction=extracted_opinion.direction,
                        strength=extracted_opinion.strength,
                        confidence=extracted_opinion.confidence,
                        thesis=extracted_opinion.thesis,
                        catalysts=extracted_opinion.catalysts,
                        risks=extracted_opinion.risks,
                        time_horizon=extracted_opinion.time_horizon,
                        generated_time=now,
                        model_version=spec.model_version,
                    )
                )

            status = self._analysis_status(extraction.investment_related, unresolved_assets)
            structured_output = extraction.model_dump(mode="json", exclude={"provider_metadata"})
            structured_output["analysis_spec"] = spec.model_dump(mode="json")
            structured_output["unresolved_assets"] = [
                item.model_dump(mode="json") for item in unresolved_assets
            ]
            analysis = write_unit_of_work.analyses.save(
                EventAnalysisCreate(
                    event_id=persisted_event.id,
                    spec=spec,
                    status=status,
                    investment_related=extraction.investment_related,
                    generated_time=now,
                    calculated_at=now,
                    confidence=self._analysis_confidence(extraction),
                    structured_output=structured_output,
                    provider_metadata=extraction.provider_metadata,
                )
            )
            commands = [
                command.model_copy(update={"analysis_id": analysis.id}) for command in commands
            ]
            write_result = write_unit_of_work.opinions.add_many(commands)
            write_unit_of_work.commit()

        opinion_status = self._opinion_status_for_new(write_result, unresolved_assets, status)
        return OpinionProcessingResult(
            event_id=event.id,
            opinion_ids=write_result.opinion_ids,
            unresolved_assets=tuple(unresolved_assets),
            model_version=spec.model_version,
            status=opinion_status,
            analysis_id=analysis.id,
            analysis_version=spec.analysis_version,
            analysis_status=status,
        )

    def _persist_failure(self, event_id: UUID, spec: AnalysisSpec, error: Exception) -> None:
        now = utc_now()
        with self._unit_of_work_factory() as unit_of_work:
            if unit_of_work.raw_events.get_view(event_id) is None:
                return
            unit_of_work.analyses.save(
                EventAnalysisCreate(
                    event_id=event_id,
                    spec=spec,
                    status=EventAnalysisStatus.FAILED,
                    investment_related=False,
                    generated_time=now,
                    calculated_at=now,
                    confidence=0.0,
                    structured_output={
                        "error_type": type(error).__name__,
                        "analysis_spec": spec.model_dump(mode="json"),
                        "error_code": str(getattr(error, "code", type(error).__name__)),
                        "error_message": str(error),
                        "retryable": bool(getattr(error, "retryable", False)),
                    },
                    error_code=str(getattr(error, "code", type(error).__name__)),
                )
            )
            unit_of_work.commit()

    @staticmethod
    def _validate_extraction(*, extraction_model_version: str, spec: AnalysisSpec) -> None:
        if extraction_model_version != spec.model_version:
            raise ExtractorModelVersionMismatchError(
                "extractor model_version does not match the processing request"
            )

    @staticmethod
    def _analysis_status(
        investment_related: bool,
        unresolved_assets: Sequence[UnresolvedAsset],
    ) -> EventAnalysisStatus:
        if not investment_related:
            return EventAnalysisStatus.NO_OPINION
        if unresolved_assets:
            return EventAnalysisStatus.PARTIALLY_RESOLVED
        return EventAnalysisStatus.SUCCESS

    @staticmethod
    def _analysis_confidence(extraction: object) -> float:
        opinions = getattr(extraction, "opinions", ())
        if not opinions:
            return 0.0
        return round(sum(item.confidence for item in opinions) / len(opinions), 6)

    @classmethod
    def _opinion_status_for_new(
        cls,
        write_result: OpinionWriteResult,
        unresolved_assets: Sequence[UnresolvedAsset],
        analysis_status: EventAnalysisStatus,
    ) -> OpinionProcessingStatus:
        if analysis_status == EventAnalysisStatus.NO_OPINION:
            return OpinionProcessingStatus.NO_OPINION
        if unresolved_assets:
            return OpinionProcessingStatus.PARTIALLY_RESOLVED
        if write_result.opinion_ids and write_result.created_count == 0:
            return OpinionProcessingStatus.ALREADY_PROCESSED
        return OpinionProcessingStatus.PROCESSED

    @classmethod
    def _result_from_existing(
        cls,
        analysis: EventAnalysisView,
        event_id: UUID,
        opinion_ids: Sequence[UUID],
    ) -> OpinionProcessingResult:
        unresolved_assets = cls._unresolved_from_output(analysis.structured_output)
        normalized_opinion_ids = tuple(opinion_ids)
        if analysis.status == EventAnalysisStatus.NO_OPINION:
            status = OpinionProcessingStatus.NO_OPINION
        elif analysis.status == EventAnalysisStatus.PARTIALLY_RESOLVED:
            status = OpinionProcessingStatus.PARTIALLY_RESOLVED
        else:
            status = OpinionProcessingStatus.ALREADY_PROCESSED
        return OpinionProcessingResult(
            event_id=event_id,
            opinion_ids=normalized_opinion_ids,
            unresolved_assets=unresolved_assets,
            model_version=analysis.spec.model_version,
            status=status,
            analysis_id=analysis.id,
            analysis_version=analysis.spec.analysis_version,
            analysis_status=analysis.status,
        )

    @staticmethod
    def _unresolved_from_output(output: dict[str, object]) -> tuple[UnresolvedAsset, ...]:
        values = output.get("unresolved_assets", [])
        if not isinstance(values, list):
            return ()
        return tuple(UnresolvedAsset.model_validate(value) for value in values)
