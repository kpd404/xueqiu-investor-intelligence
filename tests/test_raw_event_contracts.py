import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import CollectionRequest, EventType, RawEventDTO


def build_dto(*, collected_time: datetime | None = None) -> RawEventDTO:
    return RawEventDTO.build(
        investor_id=uuid4(),
        event_type=EventType.POST,
        source="manual",
        url="https://example.test/posts/1",
        published_time=datetime(2026, 8, 24, 9, 30, tzinfo=UTC),
        content="Example raw event",
        raw_data={"source_event_id": "1", "metrics": {"likes": 2}},
        collected_time=collected_time,
    )


def test_contracts_are_frozen_and_json_serializable() -> None:
    request = CollectionRequest(
        investor_id=uuid4(),
        platform_user_id="investor-1",
        homepage_url="https://example.test/investors/1",
        since=datetime(2026, 8, 23, tzinfo=UTC),
    )
    dto = build_dto()

    assert json.loads(request.model_dump_json())["platform_user_id"] == "investor-1"
    assert json.loads(dto.model_dump_json())["event_type"] == "POST"

    with pytest.raises(ValidationError):
        request.limit = 5  # type: ignore[misc]
    with pytest.raises(ValidationError):
        dto.content = "changed"  # type: ignore[misc]


def test_contracts_reject_naive_datetimes() -> None:
    with pytest.raises(ValidationError):
        CollectionRequest(
            investor_id=uuid4(),
            platform_user_id="investor-1",
            requested_at=datetime(2026, 8, 24, 9, 30),
        )

    with pytest.raises(ValueError, match="timezone-aware"):
        RawEventDTO.build(
            investor_id=uuid4(),
            event_type=EventType.POST,
            source="manual",
            url="https://example.test/posts/1",
            published_time=datetime(2026, 8, 24, 9, 30),
            content="Example raw event",
        )


def test_raw_event_hash_is_independent_of_collection_time() -> None:
    investor_id = uuid4()
    published_time = datetime(2026, 8, 24, 9, 30, tzinfo=UTC)
    common = {
        "investor_id": investor_id,
        "event_type": EventType.POST,
        "source": "manual",
        "url": "https://example.test/posts/1",
        "published_time": published_time,
        "content": "Example raw event",
    }

    first = RawEventDTO.build(
        **common,
        collected_time=published_time,
    )
    second = RawEventDTO.build(
        **common,
        collected_time=published_time + timedelta(hours=1),
    )

    assert first.hash == second.hash
