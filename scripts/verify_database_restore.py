# ruff: noqa: E501
from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID

import psycopg
from sqlalchemy.engine import make_url

from backend.app.api.dependencies import (
    get_asset_intelligence_product_service,
    get_intelligence_feed_query_service,
    get_investor_intelligence_product_service,
)
from config import get_settings
from operations.status import OperationalStatusService

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
INTEGRITY_QUERIES = {
    "raw_event_investor": "SELECT count(*) FROM raw_events r LEFT JOIN investors i ON i.id=r.investor_id WHERE i.id IS NULL",
    "analysis_raw_event": "SELECT count(*) FROM event_analyses a LEFT JOIN raw_events r ON r.id=a.event_id WHERE r.id IS NULL",
    "opinion_raw_event": "SELECT count(*) FROM opinions o LEFT JOIN raw_events r ON r.id=o.event_id WHERE r.id IS NULL",
    "opinion_analysis": "SELECT count(*) FROM opinions o LEFT JOIN event_analyses a ON a.id=o.analysis_id WHERE o.analysis_id IS NOT NULL AND a.id IS NULL",
    "opinion_asset": "SELECT count(*) FROM opinions o LEFT JOIN assets a ON a.id=o.asset_id WHERE a.id IS NULL",
    "thesis_current_opinion": "SELECT count(*) FROM thesis_changes t LEFT JOIN opinions o ON o.id=t.current_opinion_id WHERE o.id IS NULL",
    "thesis_current_event": "SELECT count(*) FROM thesis_changes t LEFT JOIN raw_events r ON r.id=t.current_event_id WHERE r.id IS NULL",
    "event_evidence_event": "SELECT count(*) FROM intelligence_event_evidence e LEFT JOIN intelligence_events i ON i.id=e.event_id WHERE i.id IS NULL",
    "event_evidence_signal": "SELECT count(*) FROM intelligence_event_evidence e LEFT JOIN signals s ON s.id=e.signal_id WHERE s.id IS NULL",
    "priority_event": "SELECT count(*) FROM intelligence_event_priorities p LEFT JOIN intelligence_events e ON e.id=p.event_id WHERE e.id IS NULL",
    "feed_priority": "SELECT count(*) FROM intelligence_feed_items f LEFT JOIN intelligence_event_priorities p ON p.id=f.priority_id WHERE p.id IS NULL",
    "feed_asset": "SELECT count(*) FROM intelligence_feed_items f LEFT JOIN assets a ON a.id=f.asset_id WHERE a.id IS NULL",
    "collection_observation_run": "SELECT count(*) FROM collection_observations o LEFT JOIN collection_runs r ON r.id=o.collection_run_id WHERE r.id IS NULL",
    "collection_observation_event": "SELECT count(*) FROM collection_observations o LEFT JOIN raw_events r ON r.id=o.raw_event_id WHERE r.id IS NULL",
}
IDENTITY_QUERIES = {
    "raw_event_hash": "SELECT count(*) FROM (SELECT hash FROM raw_events GROUP BY hash HAVING count(*)>1)x",
    "asset_market_symbol": "SELECT count(*) FROM (SELECT market,symbol FROM assets GROUP BY market,symbol HAVING count(*)>1)x",
    "analysis_identity": "SELECT count(*) FROM (SELECT event_id,analysis_version FROM event_analyses GROUP BY event_id,analysis_version HAVING count(*)>1)x",
    "opinion_identity": "SELECT count(*) FROM (SELECT event_id,asset_id,analysis_id FROM opinions GROUP BY event_id,asset_id,analysis_id HAVING count(*)>1)x",
    "signal_identity": "SELECT count(*) FROM (SELECT signal_type,source_id FROM signals GROUP BY signal_type,source_id HAVING count(*)>1)x",
    "intelligence_event_identity": "SELECT count(*) FROM (SELECT event_type,asset_id FROM intelligence_events GROUP BY event_type,asset_id HAVING count(*)>1)x",
    "priority_identity": "SELECT count(*) FROM (SELECT event_id FROM intelligence_event_priorities GROUP BY event_id HAVING count(*)>1)x",
    "feed_identity": "SELECT count(*) FROM (SELECT priority_id FROM intelligence_feed_items GROUP BY priority_id HAVING count(*)>1)x",
}


def _connect():
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("restore verification requires PostgreSQL")
    return psycopg.connect(
        host=url.host, port=url.port, dbname=url.database, user=url.username, password=url.password
    )


def _verify_product_views():
    asset_service = get_asset_intelligence_product_service()
    investor_service = get_investor_intelligence_product_service()
    feed_service = get_intelligence_feed_query_service()
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id FROM assets ORDER BY market,symbol,id LIMIT 1")
            asset_id = cursor.fetchone()[0]
            cursor.execute("SELECT id FROM investors ORDER BY name,id LIMIT 1")
            investor_id = cursor.fetchone()[0]
    asset_view = asset_service.get_asset_view(UUID(str(asset_id)))
    investor_view = investor_service.get_investor_view(UUID(str(investor_id)))
    feed = feed_service.list_feed(limit=20)
    operational = OperationalStatusService().get_status()
    return {
        "asset_view": {
            "asset_id": str(asset_view.asset.asset_id),
            "source_ref_count": asset_view.traceability_summary.source_ref_count,
        },
        "investor_view": {
            "investor_id": str(investor_view.investor.investor_id),
            "observed_asset_count": investor_view.summary.observed_asset_count,
            "opinion_count": investor_view.summary.opinion_count,
        },
        "inbox_total": feed.total,
        "operational_status": operational.status.value,
        "operational_freshness": operational.freshness.value,
        "latest_refresh_status": operational.latest_status.value
        if operational.latest_status
        else None,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--expected-database", required=True)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    failures = []
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT current_database(),version()")
            database_name, postgres_version = cursor.fetchone()
            cursor.execute("SELECT version_num FROM alembic_version")
            migration_head = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
            )
            table_count = cursor.fetchone()[0]
            cursor.execute("SELECT count(*) FROM pg_indexes WHERE schemaname='public'")
            index_count = cursor.fetchone()[0]
            cursor.execute(
                "SELECT count(*) FROM information_schema.table_constraints WHERE table_schema='public'"
            )
            constraint_count = cursor.fetchone()[0]
            counts = {}
            for table in CRITICAL_TABLES:
                cursor.execute(f'SELECT count(*) FROM "{table}"')
                counts[table] = cursor.fetchone()[0]
            integrity = {name: int(cursor.execute(sql) or 0) for name, sql in []}
            integrity = {}
            for name, sql in INTEGRITY_QUERIES.items():
                cursor.execute(sql)
                integrity[name] = int(cursor.fetchone()[0])
            identity = {}
            for name, sql in IDENTITY_QUERIES.items():
                cursor.execute(sql)
                identity[name] = int(cursor.fetchone()[0])
    expected_counts = manifest["critical_row_counts"]
    count_match = counts == expected_counts
    schema_match = (
        database_name == args.expected_database
        and migration_head == manifest["migration_head"]
        and table_count == manifest["public_table_count"]
        and index_count == manifest["public_index_count"]
        and constraint_count == manifest["public_constraint_count"]
    )
    if not count_match:
        failures.append("critical row counts differ from backup manifest")
    if not schema_match:
        failures.append("database or schema metadata differs from backup manifest")
    failures.extend(f"{name}={value}" for name, value in integrity.items() if value)
    failures.extend(f"identity:{name}={value}" for name, value in identity.items() if value)
    try:
        product = _verify_product_views()
    except Exception as exc:
        product = {"error_type": type(exc).__name__}
        failures.append("Product/API read verification failed")
    result = {
        "ok": not failures,
        "failures": failures,
        "database": {
            "database": database_name,
            "postgres_version": postgres_version,
            "migration_head": migration_head,
            "schema_match": schema_match,
            "counts_match": count_match,
            "critical_row_counts": counts,
        },
        "integrity": integrity,
        "identity": identity,
        "product": product,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
