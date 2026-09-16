"""Persistence adapter for deterministic Signal evidence."""

from collections.abc import Callable
from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import SignalCreate, SignalView
from database.models.signal import Signal


class SignalRepository:
    """Idempotent repository for the Signal-derived layer."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, signal_id: UUID) -> SignalView | None:
        entity = self._session.get(Signal, signal_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_identity(self, signal_type: str, source_id: UUID) -> SignalView | None:
        entity = self._session.scalar(
            select(Signal).where(
                Signal.signal_type == signal_type,
                Signal.source_id == source_id,
            )
        )
        return self._to_view(entity) if entity is not None else None

    def add_if_absent(self, command: SignalCreate) -> tuple[SignalView, bool]:
        existing = self.get_by_identity(command.signal_type.value, command.source_id)
        if existing is not None:
            return existing, False

        entity = Signal(
            asset_id=command.asset_id,
            investor_id=command.investor_id,
            signal_type=command.signal_type.value,
            state=command.state.value,
            severity=command.severity.value,
            source_type=command.source_type,
            source_id=command.source_id,
            created_at=command.created_at,
            observed_at=command.observed_at,
            metadata_json=command.metadata,
        )
        try:
            with self._session.begin_nested():
                self._session.add(entity)
                self._session.flush()
        except IntegrityError:
            existing = self.get_by_identity(command.signal_type.value, command.source_id)
            if existing is None:
                raise
            return existing, False
        return self._to_view(entity), True

    def list(self) -> tuple[SignalView, ...]:
        statement = select(Signal).order_by(
            Signal.observed_at,
            Signal.signal_type,
            Signal.source_id,
            Signal.id,
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    @classmethod
    def _to_view(cls, entity: Signal | None) -> SignalView | None:
        if entity is None:
            return None
        return SignalView(
            id=entity.id,
            asset_id=entity.asset_id,
            investor_id=entity.investor_id,
            signal_type=entity.signal_type,
            state=entity.state,
            severity=entity.severity,
            source_type=entity.source_type,
            source_id=entity.source_id,
            created_at=cls._as_utc(entity.created_at),
            observed_at=cls._as_utc(entity.observed_at),
            metadata=entity.metadata_json or {},
        )

    @staticmethod
    def _as_utc(value):
        from datetime import UTC

        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


class SqlAlchemySignalUnitOfWork:
    """Transactional source-read plus Signal-write scope."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> Self:
        from signal_engine.generator import SqlAlchemySignalSourceReader

        self._session = self._session_factory()
        self._committed = False
        self.signals = SignalRepository(self._session)
        self.source_reader = SqlAlchemySignalSourceReader(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


__all__ = ["SignalRepository", "SqlAlchemySignalUnitOfWork"]
