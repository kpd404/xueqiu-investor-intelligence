from typing import Protocol

from pydantic import BaseModel, ConfigDict

from collectors.base import SourceAdapter
from contracts import CollectionRequest, RawEventDTO, RawEventWriteResult


class RawEventWriter(Protocol):
    def add_if_absent(self, dto: RawEventDTO) -> RawEventWriteResult: ...


class TransactionManager(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    events: tuple[RawEventWriteResult, ...]

    @property
    def total(self) -> int:
        return len(self.events)

    @property
    def inserted(self) -> int:
        return sum(event.created for event in self.events)

    @property
    def duplicates(self) -> int:
        return self.total - self.inserted


class DataPipeline:
    """Store normalized adapter output with one short transaction per event."""

    def __init__(self, repository: RawEventWriter, transaction: TransactionManager) -> None:
        self._repository = repository
        self._transaction = transaction

    async def run(self, adapter: SourceAdapter, request: CollectionRequest) -> PipelineResult:
        results: list[RawEventWriteResult] = []
        async for dto in adapter.collect(request):
            try:
                results.append(self._repository.add_if_absent(dto))
                # Do not keep a transaction open while waiting for the next browser/network DTO.
                self._transaction.commit()
            except Exception:
                self._transaction.rollback()
                raise

        return PipelineResult(events=tuple(results))
