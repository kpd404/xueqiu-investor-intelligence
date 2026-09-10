"""Audit active unresolved Asset references without invoking an LLM."""

from __future__ import annotations

import sys
from collections import Counter
from typing import Any
from uuid import UUID

import psycopg
from sqlalchemy.engine import make_url

from config import get_production_analysis_policy, get_settings
from contracts import UnresolvedAsset
from resolution import (
    AssetCatalogIdentity,
    UnresolvedReference,
    build_unresolved_inventory,
)


def _connect() -> psycopg.Connection[Any]:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Asset resolution audit requires PostgreSQL; configured backend is "
            f"{url.get_backend_name()}"
        )
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
    )


def _load_references(analysis_version: str) -> list[UnresolvedReference]:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT r.id, r.investor_id, r.published_time, ea.structured_output
                FROM raw_events r
                JOIN event_analyses ea
                  ON ea.event_id = r.id
                 AND ea.analysis_version = %s
                ORDER BY r.published_time, r.id
                """,
                (analysis_version,),
            )
            references: list[UnresolvedReference] = []
            for event_id, investor_id, published_time, structured_output in cursor.fetchall():
                output = structured_output if isinstance(structured_output, dict) else {}
                for value in output.get("unresolved_assets", ()):
                    unresolved = UnresolvedAsset.model_validate(value)
                    references.append(
                        UnresolvedReference(
                            name=unresolved.asset_name,
                            symbol=unresolved.symbol,
                            market=unresolved.market,
                            investor_id=_uuid(investor_id),
                            event_id=_uuid(event_id),
                            published_time=published_time,
                            candidate_asset_ids=unresolved.candidate_asset_ids,
                        )
                    )
            return references


def _load_catalog() -> list[AssetCatalogIdentity]:
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT name, market, symbol FROM assets ORDER BY market, symbol")
            return [
                AssetCatalogIdentity(name=str(name), market=str(market), symbol=str(symbol))
                for name, market, symbol in cursor.fetchall()
            ]


def _uuid(value: object) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _print_summary(
    references: list[UnresolvedReference], catalog: list[AssetCatalogIdentity]
) -> None:
    aggregates = build_unresolved_inventory(references, catalog=catalog)
    category_occurrences = Counter(
        aggregate.category.value
        for aggregate in aggregates
        for _ in range(aggregate.occurrence_count)
    )
    category_names = Counter(aggregate.category.value for aggregate in aggregates)
    blocker_occurrences = Counter(
        aggregate.blocker.value
        for aggregate in aggregates
        for _ in range(aggregate.occurrence_count)
    )

    print("# Unresolved Asset Audit")
    print(f"Active unresolved entries: {len(references)}")
    print(f"Distinct unresolved references: {len(aggregates)}")
    print("Taxonomy by occurrence:")
    for category, count in category_occurrences.most_common():
        print(f"  {category}: occurrences={count}, references={category_names[category]}")
    print("Resolution blocker by occurrence:")
    for blocker, count in blocker_occurrences.most_common():
        print(f"  {blocker}: {count}")

    safe = [aggregate for aggregate in aggregates if aggregate.safe_to_seed]
    print(f"Safe Asset master candidates: {len(safe)}")
    print("Top unresolved candidates:")
    for aggregate in sorted(aggregates, key=lambda value: value.priority_key(), reverse=True)[:40]:
        print(
            "  "
            f"name={aggregate.name} symbol={aggregate.symbol or '-'} "
            f"market={aggregate.market or '-'} "
            f"category={aggregate.category.value} blocker={aggregate.blocker.value} "
            f"occurrences={aggregate.occurrence_count} "
            f"investors={aggregate.distinct_investor_count} "
            f"events={aggregate.distinct_event_count} active_days={aggregate.active_day_count} "
            f"repeated_cross_day={aggregate.repeated_cross_day} "
            f"first={aggregate.first_published_time.isoformat()} "
            f"latest={aggregate.latest_published_time.isoformat()}"
        )
    print("Safe candidates prioritized for explicit seeding:")
    for aggregate in sorted(safe, key=lambda value: value.priority_key(), reverse=True):
        print(
            "  "
            f"name={aggregate.name} symbol={aggregate.symbol or '-'} "
            f"market={aggregate.market or '-'} "
            f"occurrences={aggregate.occurrence_count} "
            f"investors={aggregate.distinct_investor_count} "
            f"events={aggregate.distinct_event_count} active_days={aggregate.active_day_count}"
        )


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    policy = get_production_analysis_policy()
    references = _load_references(policy.active_analysis_version)
    catalog = _load_catalog()
    _print_summary(references, catalog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
