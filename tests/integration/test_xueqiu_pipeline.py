import asyncio
import json
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from collectors.base import SourceAdapter
from collectors.xueqiu import XueqiuAdapter
from contracts import CollectionRequest
from database.models import Investor, RawEvent
from database.repositories import RawEventRepository
from pipeline import DataPipeline

FIXTURE_PATH = Path(__file__).parents[1] / "fixtures" / "xueqiu" / "status_response.json"


class FixtureXueqiuBrowser:
    async def fetch_status_payloads(self, request: CollectionRequest) -> list[dict[str, object]]:
        return [json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))]


def test_xueqiu_adapter_pipeline_is_idempotent(db_session: Session) -> None:
    investor = Investor(
        name="Fixture Xueqiu Investor",
        platform="xueqiu",
        platform_user_id="700001",
        homepage_url="https://xueqiu.com/u/700001",
    )
    db_session.add(investor)
    db_session.commit()

    request = CollectionRequest(
        investor_id=investor.id,
        platform_user_id=investor.platform_user_id,
        homepage_url=investor.homepage_url,
        limit=5,
    )
    adapter = XueqiuAdapter(FixtureXueqiuBrowser())
    pipeline = DataPipeline(RawEventRepository(db_session), db_session)

    assert isinstance(adapter, SourceAdapter)
    first = asyncio.run(pipeline.run(adapter, request))
    second = asyncio.run(pipeline.run(adapter, request))

    assert first.inserted == 1
    assert first.duplicates == 0
    assert second.inserted == 0
    assert second.duplicates == 1
    assert first.events[0].event_id == second.events[0].event_id
    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 1

    stored = db_session.get(RawEvent, first.events[0].event_id)
    assert stored is not None
    assert stored.source == "xueqiu"
    assert stored.raw_data["source_event_id"] == "880000000001"
