from enum import StrEnum


class EventType(StrEnum):
    POST = "POST"
    ARTICLE = "ARTICLE"
    PORTFOLIO_SNAPSHOT = "PORTFOLIO_SNAPSHOT"


class OpinionDirection(StrEnum):
    STRONG_BEARISH = "STRONG_BEARISH"
    BEARISH = "BEARISH"
    NEUTRAL = "NEUTRAL"
    BULLISH = "BULLISH"
    STRONG_BULLISH = "STRONG_BULLISH"
