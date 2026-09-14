from collections.abc import Callable
from datetime import datetime
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from collectors.base import SourceAdapter
from contracts import (
    CollectionIngestDisposition,
    CollectionObservationCreate,
    CollectionObservationView,
    CollectionRequest,
    RawEventDTO,
    RawEventWriteResult,
)
from contracts.collection_provenance import utc_now


class RawEventWriter(Protocol):
    def add_if_absent(self, dto: RawEventDTO) -> RawEventWriteResult: ...


class TransactionManager(Protocol):
    def commit(self) -> None: ...

    def rollback(self) -> None: ...


class CollectionObservationWriter(Protocol):
    """Persistence port for recording one run-to-RawEvent provenance edge."""

    def record_observation(
        self, command: CollectionObservationCreate
    ) -> tuple[CollectionObservationView, bool]: ...


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

    def __init__(
        self,
        repository: RawEventWriter,
        transaction: TransactionManager,
        *,
        collection_observation_repository: CollectionObservationWriter | None = None,
        collection_run_id: UUID | None = None,
        observed_at_factory: Callable[[], datetime] = utc_now,
        source_page: str | None = None,
        source_context_json: dict[str, object] | None = None,
    ) -> None:
        if (collection_observation_repository is None) != (collection_run_id is None):
            raise ValueError(
                "collection_observation_repository and collection_run_id must be provided together"
            )
        self._repository = repository
        self._transaction = transaction
        self._collection_observations = collection_observation_repository
        self._collection_run_id = collection_run_id
        self._observed_at_factory = observed_at_factory
        self._source_page = source_page
        self._source_context_json = source_context_json

    async def run(
        self,
        adapter: SourceAdapter,
        request: CollectionRequest,
        *,
        collection_run_id: UUID | None = None,
    ) -> PipelineResult:
        run_id = collection_run_id or self._collection_run_id
        observation_writer = self._collection_observations
        if (observation_writer is None) != (run_id is None):
            raise ValueError(
                "collection_observation_repository and collection_run_id must be provided together"
            )
        results: list[RawEventWriteResult] = []
        async for sequence, dto in _enumerate_async(adapter.collect(request)):
            try:
                begin_transaction_if_needed(self._transaction)
                result = self._repository.add_if_absent(dto)
                if observation_writer is not None and run_id is not None:
                    observation_writer.record_observation(
                        CollectionObservationCreate(
                            collection_run_id=run_id,
                            raw_event_id=result.event_id,
                            observed_at=self._observed_at_factory(),
                            ingest_disposition=(
                                CollectionIngestDisposition.INSERTED
                                if result.created
                                else CollectionIngestDisposition.REUSED_EXISTING
                            ),
                            observation_sequence=sequence,
                            source_page=self._source_page,
                            source_context_json=self._source_context_json,
                        )
                    )
                results.append(result)
                # Do not keep a transaction open while waiting for the next browser/network DTO.
                self._transaction.commit()
            except Exception:
                self._transaction.rollback()
                raise

        return PipelineResult(events=tuple(results))


def begin_transaction_if_needed(transaction: object) -> None:
    """Start a real DB transaction before a nested savepoint is used.

    SQLite's legacy transaction mode does not make a savepoint transactional
    unless an outer transaction has already begun.  Starting one when the
    adapter exposes SQLAlchemy's Session API keeps RawEvent and provenance
    writes atomic while preserving the lightweight fake transaction port used
    by unit tests.
    """

    begin = getattr(transaction, "begin", None)
    if not callable(begin):
        return
    active = getattr(transaction, "in_transaction", None)
    is_active = active() if callable(active) else bool(active)
    if not is_active:
        begin()
        return

    # Python's sqlite3 driver uses legacy transaction control by default:
    # SQLAlchemy can have a logical Session transaction after a SELECT while
    # the driver still has no real transaction.  A nested savepoint would
    # otherwise be released as an independently committed transaction.
    get_bind = getattr(transaction, "get_bind", None)
    connection_factory = getattr(transaction, "connection", None)
    if not callable(get_bind) or not callable(connection_factory):
        return
    try:
        if get_bind().dialect.name != "sqlite":
            return
        connection = connection_factory()
        connection_fairy = getattr(connection, "connection", None)
        driver_connection = getattr(connection_fairy, "driver_connection", None)
        if driver_connection is not None and not driver_connection.in_transaction:
            driver_connection.execute("BEGIN")
    except (AttributeError, RuntimeError):
        # Transaction ports other than SQLAlchemy Session do not expose the
        # driver state; their existing begin/commit/rollback contract remains
        # authoritative.
        return


async def _enumerate_async(source):
    sequence = 0
    async for item in source:
        yield sequence, item
        sequence += 1
