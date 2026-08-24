from enum import StrEnum


class EventType(StrEnum):
    POST = "POST"
    ARTICLE = "ARTICLE"
    PORTFOLIO_SNAPSHOT = "PORTFOLIO_SNAPSHOT"
