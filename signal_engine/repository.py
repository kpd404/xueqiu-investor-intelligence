"""Persistence adapter for deterministic Signal evidence."""

from collections.abc import Callable
from types import TracebackType
from typing import Self
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from contracts import EffectiveAnalysisPolicy, SignalCreate, SignalState, SignalType, SignalView
from contracts.thesis_change import ThesisChangeType
from database.models.signal import Signal
from database.models.thesis_change import ThesisChange
from database.repositories.thesis_changes import ThesisChangeRepository


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

    def list_by_asset(self, asset_id: UUID) -> tuple[SignalView, ...]:
        statement = (
            select(Signal)
            .where(Signal.asset_id == asset_id)
            .order_by(
                Signal.observed_at,
                Signal.signal_type,
                Signal.source_id,
                Signal.id,
            )
        )
        return tuple(self._to_view(entity) for entity in self._session.scalars(statement))

    def list_effective_thesis_changes(
        self,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str,
    ) -> tuple[SignalView, ...]:
        """Read current material Thesis Signals without changing their history.

        Validity comes from source records, not Signal metadata. The existing
        effective selector evaluates the complete current predecessor timeline;
        no local event scope or cached source validity is used here.
        """

        material_types = {
            ThesisChangeType.THESIS_REINFORCED,
            ThesisChangeType.THESIS_EXTENDED,
            ThesisChangeType.THESIS_CHANGED,
        }
        sources = {
            change.id: change
            for change in ThesisChangeRepository(self._session).list_effective(
                policy, comparison_version
            )
            if change.change_type in material_types
        }
        statement = (
            select(Signal)
            .where(
                Signal.signal_type == SignalType.THESIS_CHANGE.value,
                Signal.state == SignalState.ACTIVE.value,
                Signal.source_type == "ThesisChange",
            )
            .order_by(Signal.observed_at, Signal.signal_type, Signal.source_id, Signal.id)
        )
        return tuple(
            self._to_view(entity)
            for entity in self._session.scalars(statement)
            if (source := sources.get(entity.source_id)) is not None
            and entity.asset_id == source.asset_id
            and entity.investor_id == source.investor_id
        )

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


class EventAggregationSignalReader:
    """Event-only read adapter; ordinary Signal repository reads stay historical."""

    def __init__(self, repository: SignalRepository) -> None:
        self._repository = repository

    def list(self) -> tuple[SignalView, ...]:
        signals = self._repository.list()
        if not any(
            signal.signal_type is SignalType.THESIS_CHANGE and signal.state is SignalState.ACTIVE
            for signal in signals
        ):
            return tuple(
                signal for signal in signals if signal.signal_type is not SignalType.THESIS_CHANGE
            )

        from config import get_production_analysis_policy, get_production_thesis_comparison_policy

        effective_ids = {
            signal.id
            for signal in self._repository.list_effective_thesis_changes(
                get_production_analysis_policy().as_effective_policy(),
                get_production_thesis_comparison_policy().active_analysis_version,
            )
        }
        return tuple(
            signal
            for signal in signals
            if signal.signal_type is not SignalType.THESIS_CHANGE or signal.id in effective_ids
        )


class FeedThesisSignalReader:
    """Feed-only effective evidence with authoritative source fact times."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list(self) -> tuple[SignalView, ...]:
        from config import get_production_analysis_policy, get_production_thesis_comparison_policy

        signals = SignalRepository(self._session).list_effective_thesis_changes(
            get_production_analysis_policy().as_effective_policy(),
            get_production_thesis_comparison_policy().active_analysis_version,
        )
        if not signals:
            return ()
        source_times = dict(
            self._session.execute(
                select(ThesisChange.id, ThesisChange.effective_time).where(
                    ThesisChange.id.in_({signal.source_id for signal in signals})
                )
            ).all()
        )
        # A historical Signal may carry an incorrect observed_at. Correct only
        # this read view; never rewrite it or use calculation time as freshness.
        return tuple(
            signal.model_copy(
                update={"observed_at": SignalRepository._as_utc(source_times[signal.source_id])}
            )
            for signal in signals
            if signal.source_id in source_times
        )


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


__all__ = [
    "EventAggregationSignalReader",
    "FeedThesisSignalReader",
    "SignalRepository",
    "SqlAlchemySignalUnitOfWork",
]
