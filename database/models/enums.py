from enum import StrEnum

from contracts.enums import (
    AttentionLevel,
    EventType,
    OpinionDirection,
    PositionStatus,
)


class StringEnum(StrEnum):
    """Enum whose persisted value is the declared string value."""


class SignalLevel(StringEnum):
    STRONG_SIGNAL = "STRONG_SIGNAL"
    HIGH_PRIORITY_RESEARCH = "HIGH_PRIORITY_RESEARCH"
    WATCH = "WATCH"
    LOW_PRIORITY = "LOW_PRIORITY"


__all__ = [
    "AttentionLevel",
    "EventType",
    "OpinionDirection",
    "PositionStatus",
    "SignalLevel",
]
