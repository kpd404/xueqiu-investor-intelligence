"""Execute the new Alembic upgrade over a predecessor schema, never create the new table."""

from types import SimpleNamespace
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from contracts import FeedState
from database.base import Base
from database.models import ResearchCandidate  # noqa: F401
from intelligence.product.research import AddResearch, EditResearch, ResearchService
from tests.integration.test_effective_asset_context import _ready
from tests.integration.test_research_candidates import body_for
from tests.integration.test_thesis_change_signals import production_policies as production_policies
from tests.integration.test_thesis_materialization_consistency import _history


def test_actual_sqlite_incremental_upgrade_and_repeat(tmp_path, production_policies):
    url = "sqlite+pysqlite:///" + str(tmp_path / "research.db")
    engine = create_engine(url)
    # Existing-schema fixture only. Research table must be created by Alembic.
    Base.metadata.create_all(
        engine,
        tables=[
            t
            for t in Base.metadata.sorted_tables
            if t.name not in {"research_candidates", "inbox_user_states"}
        ],
    )
    assert "research_candidates" not in inspect(engine).get_table_names()
    cfg = Config("alembic.ini")
    with patch("config.get_settings", return_value=SimpleNamespace(database_url=url)):
        command.stamp(cfg, "20260920_0024")
        command.upgrade(cfg, "20261010_0025")
        command.upgrade(cfg, "20261010_0025")
    assert "research_candidates" in inspect(engine).get_table_names()
    with engine.connect() as c:
        assert c.scalar(text("select version_num from alembic_version")) == "20261010_0025"
    assert inspect(engine).get_indexes("research_candidates")[0]["unique"] == 1
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    source, feed = _history(factory, production_policies, state=FeedState.NEW)
    _ready(factory)
    service = ResearchService(factory)
    row = service.add(AddResearch(**body_for(factory, source, feed)))
    service.edit(
        __import__("uuid").UUID(row["id"]),
        EditResearch(status="RESEARCHING", questions="持久化问题"),
    )
    engine.dispose()
    restarted = create_engine(url)
    saved = ResearchService(sessionmaker(bind=restarted, expire_on_commit=False)).read(
        __import__("uuid").UUID(row["id"])
    )
    assert saved["status"] == "RESEARCHING" and saved["questions"] == "持久化问题"
    assert saved["id"] == row["id"] and saved["created_at"] == row["created_at"]
    restarted.dispose()
