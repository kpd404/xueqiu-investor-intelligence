import asyncio
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from collectors import ManualImportAdapter, SourceAdapter
from contracts import CollectionRequest, EventType
from database.models import Investor, RawEvent
from database.repositories import RawEventRepository
from pipeline import DataPipeline


def test_manual_import_pipeline_is_idempotent(db_session: Session) -> None:
    investor = Investor(
        name="Manual Investor",
        platform="manual",
        platform_user_id="manual-investor-1",
    )
    db_session.add(investor)
    db_session.commit()

    request = CollectionRequest(
        investor_id=investor.id,
        platform_user_id=investor.platform_user_id,
        homepage_url="https://example.test/investors/1",
    )
    adapter = ManualImportAdapter(
        content="A manually imported investment observation.",
        published_time=datetime(2026, 8, 24, 10, 0, tzinfo=UTC),
        url="https://example.test/manual/events/1",
        event_type=EventType.ARTICLE,
        raw_data={"source_event_id": "manual-event-1"},
    )
    repository = RawEventRepository(db_session)
    pipeline = DataPipeline(repository, db_session)

    assert isinstance(adapter, SourceAdapter)

    first = asyncio.run(pipeline.run(adapter, request))
    second = asyncio.run(pipeline.run(adapter, request))

    assert first.total == 1
    assert first.inserted == 1
    assert first.duplicates == 0
    assert second.total == 1
    assert second.inserted == 0
    assert second.duplicates == 1
    assert second.events[0].event_id == first.events[0].event_id

    event_count = db_session.scalar(select(func.count()).select_from(RawEvent))
    assert event_count == 1

    stored_by_hash = repository.get_by_hash(first.events[0].hash)
    stored_by_id = repository.get(first.events[0].event_id)
    assert stored_by_hash is not None
    assert stored_by_id is stored_by_hash
    assert stored_by_hash.investor_id == investor.id
    assert stored_by_hash.source == "manual"
    assert stored_by_hash.event_type == EventType.ARTICLE
    assert stored_by_hash.raw_data["source_event_id"] == "manual-event-1"
