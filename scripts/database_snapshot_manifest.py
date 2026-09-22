# ruff: noqa: E501
from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import psycopg
from sqlalchemy.engine import make_url

from config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CRITICAL_TABLES = (
    "investors",
    "assets",
    "asset_aliases",
    "raw_events",
    "event_analyses",
    "opinions",
    "attention_occurrences",
    "thesis_changes",
    "signals",
    "intelligence_events",
    "intelligence_event_priorities",
    "intelligence_feed_items",
    "collection_runs",
    "collection_observations",
    "operational_refresh_runs",
)


def _connect():
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("database snapshot manifest requires PostgreSQL")
    return psycopg.connect(
        host=url.host, port=url.port, dbname=url.database, user=url.username, password=url.password
    )


def _git_head():
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=PROJECT_ROOT, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() or None


def main():
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT version(), current_database(), pg_size_pretty(pg_database_size(current_database()))"
            )
            postgres_version, database_name, database_size = cursor.fetchone()
            cursor.execute("SELECT version_num FROM alembic_version")
            migration_head = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
            )
            public_table_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
            public_index_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM information_schema.table_constraints WHERE table_schema='public'"
            )
            public_constraint_count = cursor.fetchone()[0]
            row_counts = {}
            for table in CRITICAL_TABLES:
                cursor.execute(f'SELECT count(*) FROM "{table}"')
                row_counts[table] = cursor.fetchone()[0]
    print(
        json.dumps(
            {
                "schema_version": "database-backup-manifest-v1",
                "captured_at_utc": datetime.now(UTC).isoformat(),
                "git_head": _git_head(),
                "database": database_name,
                "postgres_version": postgres_version,
                "database_size": database_size,
                "migration_head": migration_head,
                "public_table_count": public_table_count,
                "public_index_count": public_index_count,
                "public_constraint_count": public_constraint_count,
                "critical_row_counts": row_counts,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
