"""Deterministic Signal generation service with dry-run and idempotency."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import SignalCreate, SignalGenerationResult, SignalType, SignalView
from signal_engine.generator import SignalSourceReader
from signal_engine.repository import SqlAlchemySignalUnitOfWork


class SignalWriter(Protocol):
    def get_by_identity(self, signal_type: str, source_id: UUID) -> SignalView | None: ...

    def add_if_absent(self, command: SignalCreate) -> tuple[SignalView, bool]: ...


class SignalEngineUnitOfWork(Protocol):
    signals: SignalWriter
    source_reader: SignalSourceReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


SignalEngineUnitOfWorkFactory = Callable[[], SignalEngineUnitOfWork]


class SignalGenerator:
    """Generate only facts-backed Signal rows; never modifies source artifacts."""

    def __init__(self, unit_of_work_factory: SignalEngineUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(cls, session_factory: Callable[[], object]) -> SignalGenerator:
        return cls(lambda: SqlAlchemySignalUnitOfWork(session_factory))

    def dry_run(
        self,
        *,
        asset_ids: Iterable[UUID] | None = None,
        event_ids: Iterable[UUID] | None = None,
        signal_types: Iterable[SignalType] | None = None,
    ) -> SignalGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work,
                asset_ids=asset_ids,
                event_ids=event_ids,
                signal_types=signal_types,
            )
            existing = tuple(
                signal
                for candidate in candidates
                for signal in (
                    unit_of_work.signals.get_by_identity(
                        candidate.signal_type.value,
                        candidate.source_id,
                    ),
                )
                if signal is not None
            )
        return SignalGenerationResult(
            candidates=candidates,
            signals=existing,
            created_count=len(candidates) - len(existing),
            reused_count=len(existing),
            duplicate_count=0,
            dry_run=True,
        )

    def generate(
        self,
        *,
        asset_ids: Iterable[UUID] | None = None,
        event_ids: Iterable[UUID] | None = None,
        signal_types: Iterable[SignalType] | None = None,
    ) -> SignalGenerationResult:
        with self._unit_of_work_factory() as unit_of_work:
            candidates = self._candidates(
                unit_of_work,
                asset_ids=asset_ids,
                event_ids=event_ids,
                signal_types=signal_types,
            )
            persisted: list[SignalView] = []
            created_count = 0
            reused_count = 0
            for candidate in candidates:
                signal, created = unit_of_work.signals.add_if_absent(candidate)
                persisted.append(signal)
                if created:
                    created_count += 1
                else:
                    reused_count += 1
            unit_of_work.commit()
        return SignalGenerationResult(
            candidates=candidates,
            signals=tuple(persisted),
            created_count=created_count,
            reused_count=reused_count,
            duplicate_count=0,
            dry_run=False,
        )

    def generate_many(
        self,
        *,
        asset_ids: Iterable[UUID] | None = None,
        event_ids: Iterable[UUID] | None = None,
        signal_types: Iterable[SignalType] | None = None,
    ) -> SignalGenerationResult:
        return self.generate(
            asset_ids=asset_ids,
            event_ids=event_ids,
            signal_types=signal_types,
        )

    @staticmethod
    def _candidates(
        unit_of_work: SignalEngineUnitOfWork,
        *,
        asset_ids: Iterable[UUID] | None,
        event_ids: Iterable[UUID] | None,
        signal_types: Iterable[SignalType] | None,
    ) -> tuple[SignalCreate, ...]:
        normalized_assets = frozenset(asset_ids) if asset_ids is not None else None
        normalized_events = frozenset(event_ids) if event_ids is not None else None
        normalized_types = frozenset(signal_types) if signal_types is not None else None
        return unit_of_work.source_reader.list_candidates(
            asset_ids=normalized_assets,
            event_ids=normalized_events,
            signal_types=normalized_types,
        )


__all__ = [
    "SignalEngineUnitOfWork",
    "SignalEngineUnitOfWorkFactory",
    "SignalGenerator",
    "SignalWriter",
]
