"""Read-only selection report for the next Xueqiu history backfill targets.

The output is an evidence-based collection-priority report.  It is not a
persisted score, ranking, or Intelligence policy.  Matching is deliberately
limited to exact canonical names, registered aliases, and exact
``symbol + market`` identity evidence.
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path
from uuid import UUID

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from config import get_production_analysis_policy, get_production_attention_policy_version
from scripts.audit_intelligence_data import _fetchall


def _norm(value: object) -> str:
    return unicodedata.normalize("NFKC", str(value or "")).strip().casefold()


def _uuid(value: object) -> str:
    return str(value)


def _load_investors() -> dict[str, dict[str, object]]:
    rows = _fetchall(
        """
        SELECT i.id, i.name, i.platform, i.platform_user_id,
               count(r.id), min(r.published_time), max(r.published_time),
               count(DISTINCT date(r.published_time AT TIME ZONE 'Asia/Hong_Kong'))
        FROM investors i
        LEFT JOIN raw_events r ON r.investor_id = i.id
        GROUP BY i.id, i.name, i.platform, i.platform_user_id
        ORDER BY count(r.id) DESC, i.name, i.id
        """
    )
    return {
        _uuid(row[0]): {
            "investor_id": _uuid(row[0]),
            "name": row[1],
            "platform": row[2],
            "platform_user_id": row[3],
            "raw_events": int(row[4]),
            "history_first": row[5],
            "history_last": row[6],
            "active_days": int(row[7]),
        }
        for row in rows
    }


def _load_assets() -> tuple[dict[str, dict[str, object]], dict[str, set[str]]]:
    assets: dict[str, dict[str, object]] = {}
    names_to_assets: dict[str, set[str]] = defaultdict(set)
    for asset_id, name, symbol, market in _fetchall("SELECT id, name, symbol, market FROM assets"):
        key = _uuid(asset_id)
        assets[key] = {
            "asset_id": key,
            "name": name,
            "symbol": symbol,
            "market": market,
        }
        names_to_assets[_norm(name)].add(key)
    for asset_id, _alias, normalized_alias, _alias_type, _market in _fetchall(
        "SELECT asset_id, alias, normalized_alias, alias_type, market FROM asset_aliases"
    ):
        names_to_assets[_norm(normalized_alias)].add(_uuid(asset_id))
    return assets, names_to_assets


def _load_attention(
    analysis_version: str,
    attention_policy_version: str,
) -> tuple[dict[str, list[dict[str, object]]], dict[str, set[str]]]:
    by_investor: dict[str, list[dict[str, object]]] = defaultdict(list)
    by_asset: dict[str, set[str]] = defaultdict(set)
    rows = _fetchall(
        """
        SELECT ao.investor_id, ao.asset_id, count(*),
               count(DISTINCT date(ao.published_time AT TIME ZONE 'Asia/Hong_Kong')),
               min(ao.published_time), max(ao.published_time)
        FROM attention_occurrences ao
        LEFT JOIN event_analyses ea ON ea.id = ao.analysis_id
        WHERE ao.attention_policy_version = %s
          AND (
              ao.analysis_id IS NULL
              OR (
                  ea.analysis_version = %s
                  AND ea.status IN ('SUCCESS', 'PARTIALLY_RESOLVED')
              )
          )
        GROUP BY ao.investor_id, ao.asset_id
        """,
        (attention_policy_version, analysis_version),
    )
    for investor_id, asset_id, count, days, first, latest in rows:
        investor_key = _uuid(investor_id)
        asset_key = _uuid(asset_id)
        by_investor[investor_key].append(
            {
                "asset_id": asset_key,
                "occurrences": int(count),
                "active_days": int(days),
                "first": first,
                "latest": latest,
            }
        )
        by_asset[asset_key].add(investor_key)
    return by_investor, by_asset


def _load_opinions(
    analysis_version: str,
) -> dict[str, list[dict[str, object]]]:
    by_investor: dict[str, list[dict[str, object]]] = defaultdict(list)
    rows = _fetchall(
        """
        SELECT o.investor_id, o.asset_id, count(*),
               count(DISTINCT date(r.published_time AT TIME ZONE 'Asia/Hong_Kong')),
               min(r.published_time), max(r.published_time),
               string_agg(DISTINCT o.direction::text, ',')
        FROM opinions o
        JOIN raw_events r ON r.id = o.event_id
        JOIN event_analyses ea ON ea.id = o.analysis_id
        WHERE ea.analysis_version = %s
          AND ea.status IN ('SUCCESS', 'PARTIALLY_RESOLVED')
        GROUP BY o.investor_id, o.asset_id
        """,
        (analysis_version,),
    )
    for investor_id, asset_id, count, days, first, latest, directions in rows:
        by_investor[_uuid(investor_id)].append(
            {
                "asset_id": _uuid(asset_id),
                "opinions": int(count),
                "active_days": int(days),
                "first": first,
                "latest": latest,
                "directions": directions,
            }
        )
    return by_investor


def _load_unresolved(analysis_version: str) -> list[dict[str, object]]:
    unresolved: list[dict[str, object]] = []
    rows = _fetchall(
        """
        SELECT ea.event_id, re.investor_id, re.published_time, ea.structured_output
        FROM event_analyses ea
        JOIN raw_events re ON re.id = ea.event_id
        WHERE ea.analysis_version = %s
        """,
        (analysis_version,),
    )
    for event_id, investor_id, published_time, structured_output in rows:
        payload = structured_output if isinstance(structured_output, dict) else {}
        values = payload.get("unresolved_assets", [])
        if not isinstance(values, list):
            continue
        for value in values:
            if not isinstance(value, dict):
                continue
            unresolved.append(
                {
                    "event_id": _uuid(event_id),
                    "investor_id": _uuid(investor_id),
                    "published_time": published_time,
                    "name": str(value.get("asset_name") or "").strip(),
                    "symbol": str(value.get("symbol") or "").strip() or None,
                    "market": str(value.get("market") or "").strip() or None,
                    "reason": str(value.get("reason") or "").strip(),
                }
            )
    return unresolved


def _catalog_matches(
    value: dict[str, object],
    assets: dict[str, dict[str, object]],
    names_to_assets: dict[str, set[str]],
) -> set[str]:
    symbol = _norm(value.get("symbol"))
    market = _norm(value.get("market"))
    if symbol and market:
        return {
            asset_id
            for asset_id, asset in assets.items()
            if _norm(asset["symbol"]) == symbol and _norm(asset["market"]) == market
        }
    return set(names_to_assets.get(_norm(value.get("name")), set()))


def _asset_label(asset_id: str, assets: dict[str, dict[str, object]]) -> str:
    asset = assets[asset_id]
    return f"{asset['name']}[{asset['market']}:{asset['symbol']}]"


def _build_report(
    *,
    completed_ids: set[str],
    limit: int,
    analysis_version: str,
    attention_policy_version: str,
) -> dict[str, object]:
    investors = _load_investors()
    missing_completed = completed_ids - set(investors)
    if missing_completed:
        raise ValueError(
            "completed Investor IDs do not exist: " + ", ".join(sorted(missing_completed))
        )
    assets, names_to_assets = _load_assets()
    attention, asset_investors = _load_attention(
        analysis_version,
        attention_policy_version,
    )
    opinions = _load_opinions(analysis_version)
    unresolved = _load_unresolved(analysis_version)
    unresolved_by_investor: dict[str, list[dict[str, object]]] = defaultdict(list)
    unresolved_by_name: dict[str, list[dict[str, object]]] = defaultdict(list)
    for value in unresolved:
        unresolved_by_investor[str(value["investor_id"])].append(value)
        unresolved_by_name[_norm(value["name"])].append(value)

    shared_assets = {
        asset_id for asset_id, investor_ids in asset_investors.items() if len(investor_ids) >= 2
    }
    three_plus_assets = {
        asset_id for asset_id, investor_ids in asset_investors.items() if len(investor_ids) >= 3
    }
    shared_names = {
        name: values
        for name, values in unresolved_by_name.items()
        if len({str(value["investor_id"]) for value in values}) >= 2
    }

    records: list[tuple[tuple[object, ...], dict[str, object]]] = []
    for investor_id, investor in investors.items():
        if investor_id in completed_ids:
            continue
        attention_rows = attention.get(investor_id, [])
        opinion_rows = opinions.get(investor_id, [])
        attention_assets = {str(row["asset_id"]) for row in attention_rows}
        opinion_assets = {str(row["asset_id"]) for row in opinion_rows}

        potential_third: dict[str, list[dict[str, object]]] = defaultdict(list)
        unresolved_shared: dict[str, list[dict[str, object]]] = defaultdict(list)
        for value in unresolved_by_investor.get(investor_id, []):
            for asset_id in _catalog_matches(value, assets, names_to_assets):
                if asset_id not in shared_assets:
                    continue
                unresolved_shared[asset_id].append(value)
                if asset_id not in attention_assets and len(asset_investors[asset_id]) == 2:
                    potential_third[asset_id].append(value)

        multi_investor_names = []
        for name, values in shared_names.items():
            candidate_values = [
                value for value in values if str(value["investor_id"]) == investor_id
            ]
            if not candidate_values:
                continue
            multi_investor_names.append(
                {
                    "reference_name": next(
                        (str(value["name"]) for value in values if value["name"]),
                        name,
                    ),
                    "occurrences_all_investors": len(values),
                    "distinct_investors": len({str(value["investor_id"]) for value in values}),
                    "candidate_occurrences": len(candidate_values),
                    "candidate_raw_events": len(
                        {str(value["event_id"]) for value in candidate_values}
                    ),
                    "first": min(value["published_time"] for value in values),
                    "latest": max(value["published_time"] for value in values),
                }
            )
        multi_investor_names.sort(
            key=lambda value: (
                -int(value["occurrences_all_investors"]),
                -int(value["distinct_investors"]),
                str(value["reference_name"]),
            )
        )

        if three_plus_assets & attention_assets:
            evidence_band = "DIRECT_3_PLUS_ATTENTION"
        elif attention_assets & shared_assets or opinion_assets & shared_assets:
            evidence_band = "DIRECT_SHARED_ASSET"
        elif potential_third:
            evidence_band = "UNIQUE_SHARED_UNRESOLVED"
        elif multi_investor_names:
            evidence_band = "MULTI_INVESTOR_UNRESOLVED"
        else:
            evidence_band = "LOW_BASELINE"

        shared_attention = sorted(
            (
                {
                    "asset": _asset_label(asset_id, assets),
                    "current_attention_investors": sorted(
                        investors[other_id]["name"] for other_id in asset_investors[asset_id]
                    ),
                    "occurrences": int(
                        next(
                            row["occurrences"]
                            for row in attention_rows
                            if row["asset_id"] == asset_id
                        )
                    ),
                }
                for asset_id in attention_assets & shared_assets
            ),
            key=lambda value: value["asset"],
        )
        shared_opinion = sorted(
            (
                {
                    "asset": _asset_label(asset_id, assets),
                    "opinions": int(
                        next(row["opinions"] for row in opinion_rows if row["asset_id"] == asset_id)
                    ),
                    "directions": next(
                        row["directions"] for row in opinion_rows if row["asset_id"] == asset_id
                    ),
                }
                for asset_id in opinion_assets & shared_assets
            ),
            key=lambda value: value["asset"],
        )
        potential_third_values = sorted(
            (
                {
                    "asset": _asset_label(asset_id, assets),
                    "current_attention_investors": sorted(
                        investors[other_id]["name"] for other_id in asset_investors[asset_id]
                    ),
                    "candidate_unresolved_occurrences": len(values),
                    "candidate_unresolved_events": len(
                        {str(value["event_id"]) for value in values}
                    ),
                    "evidence": [
                        {
                            "reference_name": value["name"],
                            "symbol": value["symbol"],
                            "market": value["market"],
                            "event_id": value["event_id"],
                            "published_time": value["published_time"],
                        }
                        for value in values[:10]
                    ],
                }
                for asset_id, values in potential_third.items()
            ),
            key=lambda value: value["asset"],
        )
        unresolved_shared_values = sorted(
            (
                {
                    "asset": _asset_label(asset_id, assets),
                    "occurrences": len(values),
                    "events": len({str(value["event_id"]) for value in values}),
                    "distinct_days": len({value["published_time"].date() for value in values}),
                }
                for asset_id, values in unresolved_shared.items()
            ),
            key=lambda value: (-value["occurrences"], value["asset"]),
        )
        record = {
            "investor_id": investor_id,
            "name": investor["name"],
            "platform_user_id": investor["platform_user_id"],
            "evidence_band": evidence_band,
            "raw_events": investor["raw_events"],
            "observed_first": investor["history_first"],
            "observed_latest": investor["history_last"],
            "observed_active_days": investor["active_days"],
            "attention_occurrences": sum(int(row["occurrences"]) for row in attention_rows),
            "attention_asset_count": len(attention_assets),
            "effective_opinions": sum(int(row["opinions"]) for row in opinion_rows),
            "opinion_asset_count": len(opinion_assets),
            "unresolved_entries": len(unresolved_by_investor.get(investor_id, [])),
            "unresolved_name_count": len(
                {_norm(value["name"]) for value in unresolved_by_investor.get(investor_id, [])}
            ),
            "current_shared_attention_assets": shared_attention,
            "current_shared_opinion_assets": shared_opinion,
            "existing_3_plus_attention_assets": [
                _asset_label(asset_id, assets)
                for asset_id in sorted(three_plus_assets & attention_assets)
            ],
            "possible_third_investor_assets": potential_third_values,
            "unresolved_references_matching_shared_assets": unresolved_shared_values,
            "multi_investor_unresolved_references": multi_investor_names[:12],
        }
        ordering = (
            -len(three_plus_assets & attention_assets),
            -len(attention_assets & shared_assets),
            -len(opinion_assets & shared_assets),
            -len(potential_third),
            -len(unresolved_shared),
            -len(multi_investor_names),
            -int(investor["raw_events"]),
            str(investor["name"]),
            investor_id,
        )
        records.append((ordering, record))

    records.sort(key=lambda value: value[0])
    return {
        "analysis_version": analysis_version,
        "attention_policy_version": attention_policy_version,
        "completed_investor_ids": sorted(completed_ids),
        "candidate_count": len(records),
        "shared_asset_count": len(shared_assets),
        "three_plus_attention_asset_count": len(three_plus_assets),
        "multi_investor_unresolved_name_count": len(shared_names),
        "selection_note": (
            "Deterministic evidence ordering for collection priority only; "
            "no score/ranking business model is persisted or applied."
        ),
        "candidates": [
            {"candidate_order": index, **record}
            for index, (_ordering, record) in enumerate(records[:limit], start=1)
        ],
    }


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--completed-investor-id",
        action="append",
        required=True,
        type=UUID,
        help="Investor already covered by the completed history set; repeat five times.",
    )
    parser.add_argument("--limit", type=int, default=10)
    args = parser.parse_args()
    if not 5 <= args.limit <= 10:
        parser.error("--limit must be between 5 and 10")
    policy = get_production_analysis_policy()
    report = _build_report(
        completed_ids={str(value) for value in args.completed_investor_id},
        limit=args.limit,
        analysis_version=policy.active_analysis_version,
        attention_policy_version=get_production_attention_policy_version(),
    )
    print("# Consensus calibration Investor candidate evidence")
    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
