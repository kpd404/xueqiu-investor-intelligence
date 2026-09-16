"""Research-signal contracts and deterministic engine components."""

from signal_engine.contracts import SignalEvidence, SignalEvidenceCollection
from signal_engine.generator import SignalSourceReader, SqlAlchemySignalSourceReader
from signal_engine.repository import SignalRepository, SqlAlchemySignalUnitOfWork
from signal_engine.service import (
    SignalEngineUnitOfWork,
    SignalEngineUnitOfWorkFactory,
    SignalGenerator,
    SignalWriter,
)

__all__ = [
    "SignalEvidence",
    "SignalEvidenceCollection",
    "SignalEngineUnitOfWork",
    "SignalEngineUnitOfWorkFactory",
    "SignalGenerator",
    "SignalRepository",
    "SignalSourceReader",
    "SignalWriter",
    "SqlAlchemySignalSourceReader",
    "SqlAlchemySignalUnitOfWork",
]
