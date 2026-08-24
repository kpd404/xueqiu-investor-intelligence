from enum import StrEnum

from contracts.enums import EventType, OpinionDirection


class StringEnum(StrEnum):
    """Enum whose persisted value is the declared string value."""


class AttentionLevel(StringEnum):
    UNKNOWN = "UNKNOWN"
    DISCOVERED = "DISCOVERED"
    TRACKING = "TRACKING"
    FOCUS = "FOCUS"
    CORE_FOCUS = "CORE_FOCUS"
    ABANDONED = "ABANDONED"


class PositionStatus(StringEnum):
    NO_POSITION = "NO_POSITION"
    WATCHING = "WATCHING"
    SMALL_POSITION = "SMALL_POSITION"
    CORE_POSITION = "CORE_POSITION"
    REDUCING = "REDUCING"
    EXITED = "EXITED"


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
