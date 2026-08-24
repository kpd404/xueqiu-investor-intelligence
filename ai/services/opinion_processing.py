from collections.abc import Callable, Sequence
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from ai.extractors.base import OpinionExtractor
from contracts import (
    OpinionCreate,
    OpinionProcessingResult,
    OpinionProcessingStatus,
    OpinionWriteResult,
    RawEventView,
    UnresolvedAsset,
)


class RawEventNotFoundError(LookupError):
    pass


class ExtractorModelVersionMismatchError(ValueError):
    pass


class RawEventReader(Protocol):
    def get_view(self, event_id: UUID) -> RawEventView | None: ...


class AssetView(Protocol):
    id: UUID


class AssetReader(Protocol):
    def get_by_market_symbol(self, market: str, symbol: str) -> AssetView | None: ...


class OpinionWriter(Protocol):
    def add_many(self, commands: Sequence[OpinionCreate]) -> OpinionWriteResult: ...


class OpinionUnitOfWork(Protocol):
    raw_events: RawEventReader
    assets: AssetReader
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


class OpinionProcessingService:
    """Orchestrate extraction and persistence without crossing into state logic."""

    def __init__(
        self,
        extractor: OpinionExtractor,
        unit_of_work_factory: OpinionUnitOfWorkFactory,
    ) -> None:
        self._extractor = extractor
        self._unit_of_work_factory = unit_of_work_factory

    async def process(self, event_id: UUID, model_version: str) -> OpinionProcessingResult:
        normalized_version = model_version.strip()
        if not normalized_version:
            raise ValueError("model_version must not be blank")

        # The read unit of work is closed before awaiting a future network-backed extractor.
        with self._unit_of_work_factory() as read_unit_of_work:
            event = read_unit_of_work.raw_events.get_view(event_id)
        if event is None:
            raise RawEventNotFoundError(f"raw event not found: {event_id}")

        extraction = await self._extractor.extract(event)
        if extraction.model_version != normalized_version:
            raise ExtractorModelVersionMismatchError(
                "extractor model_version does not match the processing request"
            )

        if not extraction.investment_related:
            return OpinionProcessingResult(
                event_id=event.id,
                opinion_ids=(),
                unresolved_assets=(),
                model_version=normalized_version,
                status=OpinionProcessingStatus.NO_OPINION,
            )

        with self._unit_of_work_factory() as write_unit_of_work:
            persisted_event = write_unit_of_work.raw_events.get_view(event_id)
            if persisted_event is None:
                raise RawEventNotFoundError(f"raw event not found: {event_id}")

            commands: list[OpinionCreate] = []
            unresolved_assets: list[UnresolvedAsset] = []
            for extracted_opinion in extraction.opinions:
                asset = write_unit_of_work.assets.get_by_market_symbol(
                    extracted_opinion.market,
                    extracted_opinion.symbol,
                )
                if asset is None:
                    unresolved_assets.append(
                        UnresolvedAsset(
                            asset_name=extracted_opinion.asset_name,
                            symbol=extracted_opinion.symbol,
                            market=extracted_opinion.market,
                        )
                    )
                    continue

                commands.append(
                    OpinionCreate(
                        event_id=persisted_event.id,
                        investor_id=persisted_event.investor_id,
                        asset_id=asset.id,
                        direction=extracted_opinion.direction,
                        strength=extracted_opinion.strength,
                        confidence=extracted_opinion.confidence,
                        thesis=extracted_opinion.thesis,
                        catalysts=extracted_opinion.catalysts,
                        risks=extracted_opinion.risks,
                        time_horizon=extracted_opinion.time_horizon,
                        model_version=normalized_version,
                    )
                )

            write_result = write_unit_of_work.opinions.add_many(commands)
            write_unit_of_work.commit()

        status = self._status_for(write_result, unresolved_assets)
        return OpinionProcessingResult(
            event_id=event.id,
            opinion_ids=write_result.opinion_ids,
            unresolved_assets=tuple(unresolved_assets),
            model_version=normalized_version,
            status=status,
        )

    @staticmethod
    def _status_for(
        write_result: OpinionWriteResult,
        unresolved_assets: Sequence[UnresolvedAsset],
    ) -> OpinionProcessingStatus:
        if unresolved_assets:
            return OpinionProcessingStatus.PARTIALLY_RESOLVED
        if write_result.opinion_ids and write_result.created_count == 0:
            return OpinionProcessingStatus.ALREADY_PROCESSED
        return OpinionProcessingStatus.PROCESSED
