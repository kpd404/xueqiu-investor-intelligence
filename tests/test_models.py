from datetime import UTC, datetime

import pytest
from sqlalchemy import inspect
from sqlalchemy.orm import Session

from database.base import Base
from database.models import Asset, Investor, Opinion, RawEvent, RawEventImmutableError
from database.models.enums import EventType, OpinionDirection


def test_metadata_contains_exactly_the_six_core_tables() -> None:
    assert set(Base.metadata.tables) == {
        "assets",
        "investors",
        "investor_asset_states",
        "opinions",
        "raw_events",
        "signals",
    }


def test_core_fact_and_interpretation_records_are_traceable(db_session: Session) -> None:
    investor = Investor(name="Example Investor", platform="xueqiu", platform_user_id="42")
    asset = Asset(name="Tencent Holdings", symbol="00700", market="HK")
    db_session.add_all([investor, asset])
    db_session.flush()

    raw_event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.POST,
        source="xueqiu",
        url="https://example.test/posts/1",
        published_time=datetime.now(UTC),
        content="Example raw fact",
        raw_data={"source_id": "1"},
        hash="a" * 64,
    )
    db_session.add(raw_event)
    db_session.flush()

    opinion = Opinion(
        event_id=raw_event.id,
        investor_id=investor.id,
        asset_id=asset.id,
        direction=OpinionDirection.BULLISH,
        strength=85.0,
        confidence=0.91,
        thesis=["AI commercialization"],
        catalysts=["Advertising recovery"],
        risks=["Regulation"],
        time_horizon="LONG_TERM",
        model_version="bootstrap-test-model",
    )
    db_session.add(opinion)
    db_session.commit()

    assert opinion.event_id == raw_event.id
    assert opinion.investor_id == investor.id
    assert opinion.asset_id == asset.id
    assert opinion.generated_time is not None


def test_raw_event_is_immutable_after_persistence(db_session: Session) -> None:
    investor = Investor(name="Example Investor", platform="manual", platform_user_id="1")
    db_session.add(investor)
    db_session.flush()
    raw_event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.ARTICLE,
        source="manual",
        url="https://example.test/articles/1",
        published_time=datetime.now(UTC),
        content="Original content",
        raw_data={},
        hash="b" * 64,
    )
    db_session.add(raw_event)
    db_session.commit()

    raw_event.content = "Mutated content"
    with pytest.raises(RawEventImmutableError):
        db_session.commit()
    db_session.rollback()


def test_opinion_schema_has_ai_provenance_fields() -> None:
    columns = {column.name for column in inspect(Opinion).columns}
    assert {"event_id", "confidence", "generated_time", "model_version"} <= columns
