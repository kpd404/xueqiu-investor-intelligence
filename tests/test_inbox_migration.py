from types import SimpleNamespace
from unittest.mock import patch

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text

from database.base import Base


def test_sqlite_actual_0025_to_0026_incremental_and_repeat(tmp_path):
    url = "sqlite+pysqlite:///" + str(tmp_path / "inbox.db")
    engine = create_engine(url)
    Base.metadata.create_all(
        engine, tables=[t for t in Base.metadata.sorted_tables if t.name != "inbox_user_states"]
    )
    assert "inbox_user_states" not in inspect(engine).get_table_names()
    cfg = Config("alembic.ini")
    with patch("config.get_settings", return_value=SimpleNamespace(database_url=url)):
        command.stamp(cfg, "20261010_0025")
        command.upgrade(cfg, "20261010_0026")
        command.upgrade(cfg, "20261010_0026")
    assert inspect(engine).get_pk_constraint("inbox_user_states")["constrained_columns"] == [
        "feed_id"
    ]
    assert (
        inspect(engine).get_foreign_keys("inbox_user_states")[0]["referred_table"]
        == "intelligence_feed_items"
    )
    with engine.connect() as c:
        assert c.scalar(text("select version_num from alembic_version")) == "20261010_0026"
