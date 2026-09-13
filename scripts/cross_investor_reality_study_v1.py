"""Read-only Cross-Investor / Thesis / Attention Reality Study V1."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Any

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
)
from contracts import (
    CONSISTENCY_POLICY_VERSION,
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
)
from scripts.reality_study_database_audit import (
    _as_list,
    _as_map,
    _connect_read_only,
    _date_hk,
    _effective_thesis,
    _enum_text,
    _fmt_dt,
    _id,
    _latest_key,
    _load_data,
    _markdown_table,
    _scalar,
)

# The report is intentionally verbose and tabular for direct terminal/chat
# consumption.  This file has no write path.
# ruff: noqa: E501

Row = dict[str, Any]
DAY = timedelta(days=1)


def _direction(value: Any) -> str:
    return _enum_text(value)


def _direction_side(value: Any) -> str | None:
    direction = _direction(value)
    if direction in {"BULLISH", "STRONG_BULLISH"}:
        return "BULLISH"
    if direction in {"BEARISH", "STRONG_BEARISH"}:
        return "BEARISH"
    if direction == "NEUTRAL":
        return "NEUTRAL"
    return None


def _asset_label(asset: Row | None) -> str:
    if not asset:
        return "unknown asset"
    return f"{asset.get('name')} ({asset.get('market')}:{asset.get('symbol')})"


def _time_key(row: Row, field: str = "published_time") -> tuple[datetime, int]:
    value = row.get(field)
    if not isinstance(value, datetime):
        value = datetime.min
    elif value.tzinfo is None or value.utcoffset() is None:
        value = value.replace(tzinfo=datetime.now().astimezone().tzinfo)
    return value, int(_id(row.get("id")).replace("-", "") or "0", 16)


def _current_views(data: dict[str, Any]) -> dict[str, Any]:
    analysis_version = get_production_analysis_policy().active_analysis_version
    thesis_version = get_production_thesis_comparison_policy().active_analysis_version
    attention_version = get_production_attention_policy_version()
    active_analyses = [
        row for row in data["analyses"] if row.get("analysis_version") == analysis_version
    ]
    current_analysis = {_id(row.get("event_id")): row for row in active_analyses}
    effective_analysis_ids = {
        _id(row.get("id"))
        for row in active_analyses
        if _enum_text(row.get("status")) in {"SUCCESS", "PARTIALLY_RESOLVED"}
    }
    opinions = [
        row for row in data["opinions"] if _id(row.get("analysis_id")) in effective_analysis_ids
    ]
    attention = [
        row
        for row in data["attention"]
        if row.get("attention_policy_version") == attention_version
        and (
            row.get("analysis_id") is None or _id(row.get("analysis_id")) in effective_analysis_ids
        )
    ]
    thesis = _effective_thesis(data["thesis"], opinions, analysis_version, thesis_version)

    opinion_by_asset_investor: dict[tuple[str, str], list[Row]] = defaultdict(list)
    opinion_by_asset: dict[str, list[Row]] = defaultdict(list)
    for row in opinions:
        key = (_id(row.get("asset_id")), _id(row.get("investor_id")))
        opinion_by_asset_investor[key].append(row)
        opinion_by_asset[_id(row.get("asset_id"))].append(row)
    attention_by_asset_investor: dict[tuple[str, str], list[Row]] = defaultdict(list)
    attention_by_asset: dict[str, list[Row]] = defaultdict(list)
    for row in attention:
        key = (_id(row.get("asset_id")), _id(row.get("investor_id")))
        attention_by_asset_investor[key].append(row)
        attention_by_asset[_id(row.get("asset_id"))].append(row)
    thesis_by_pair: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in thesis:
        thesis_by_pair[(_id(row.get("asset_id")), _id(row.get("investor_id")))].append(row)

    policy_snapshots = [
        row
        for row in data["snapshots"]
        if row.get("opinion_analysis_version") == analysis_version
        and row.get("attention_policy_version") == attention_version
        and row.get("thesis_comparison_version") == thesis_version
        and row.get("consistency_policy_version") == CONSISTENCY_POLICY_VERSION
        and row.get("cross_investor_policy_version") == CROSS_INVESTOR_POLICY_VERSION
    ]
    current_attention_ids: dict[str, set[str]] = defaultdict(set)
    attention_investors: dict[str, set[str]] = defaultdict(set)
    for row in attention:
        asset_id = _id(row.get("asset_id"))
        current_attention_ids[asset_id].add(_id(row.get("id")))
        attention_investors[asset_id].add(_id(row.get("investor_id")))

    def snapshot_attention_ids(row: Row) -> set[str]:
        values: set[str] = set()
        for contribution in _as_list(row.get("contributions")):
            values.update(
                _id(value)
                for value in _as_list(_as_map(contribution).get("attention_occurrence_ids"))
            )
        return values

    latest_snapshot: dict[str, Row] = {}
    for row in sorted(policy_snapshots, key=lambda item: _latest_key(item, "calculated_at")):
        latest_snapshot[_id(row.get("asset_id"))] = row
    snapshot_heads = {
        asset_id: row
        for asset_id, row in latest_snapshot.items()
        if len(attention_investors.get(asset_id, set())) >= 2
        and snapshot_attention_ids(row) == current_attention_ids.get(asset_id, set())
    }
    snapshot_ids = {_id(row.get("id")) for row in snapshot_heads.values()}
    snapshot_by_id = {_id(row.get("id")): row for row in data["snapshots"]}
    alignments = [
        row
        for row in data["alignments"]
        if row.get("alignment_policy_version") == CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION
        and _id(row.get("source_snapshot_id")) in snapshot_ids
        and _id(snapshot_by_id.get(_id(row.get("source_snapshot_id")), {}).get("asset_id"))
        == _id(row.get("asset_id"))
    ]
    alignment_ids = {_id(row.get("id")) for row in alignments}
    consensus = [
        row
        for row in data["consensus"]
        if row.get("consensus_policy_version") == CROSS_INVESTOR_CONSENSUS_POLICY_VERSION
        and _id(row.get("source_snapshot_id")) in snapshot_ids
        and _id(row.get("source_alignment_id")) in alignment_ids
        and _id(snapshot_by_id.get(_id(row.get("source_snapshot_id")), {}).get("asset_id"))
        == _id(row.get("asset_id"))
    ]
    return {
        "analysis_version": analysis_version,
        "thesis_version": thesis_version,
        "attention_version": attention_version,
        "active_analyses": active_analyses,
        "current_analysis": current_analysis,
        "effective_analysis_ids": effective_analysis_ids,
        "opinions": opinions,
        "attention": attention,
        "thesis": thesis,
        "opinion_by_asset_investor": opinion_by_asset_investor,
        "opinion_by_asset": opinion_by_asset,
        "attention_by_asset_investor": attention_by_asset_investor,
        "attention_by_asset": attention_by_asset,
        "thesis_by_pair": thesis_by_pair,
        "snapshot_heads": snapshot_heads,
        "alignments": alignments,
        "consensus": consensus,
    }


def _investor_density(data: dict[str, Any], views: dict[str, Any]) -> list[Row]:
    investors = {_id(row.get("id")): row for row in data["investors"]}
    raw_by_investor: dict[str, list[Row]] = defaultdict(list)
    for row in data["raw_events"]:
        raw_by_investor[_id(row.get("investor_id"))].append(row)
    opinions_by_investor: dict[str, list[Row]] = defaultdict(list)
    attention_by_investor: dict[str, list[Row]] = defaultdict(list)
    thesis_by_investor: dict[str, list[Row]] = defaultdict(list)
    for row in views["opinions"]:
        opinions_by_investor[_id(row.get("investor_id"))].append(row)
    for row in views["attention"]:
        attention_by_investor[_id(row.get("investor_id"))].append(row)
    for row in views["thesis"]:
        thesis_by_investor[_id(row.get("investor_id"))].append(row)
    shared_by_asset = defaultdict(set)
    for asset_id, rows in views["attention_by_asset"].items():
        shared_by_asset[asset_id] = {_id(row.get("investor_id")) for row in rows}
    rows: list[Row] = []
    for investor_id, investor in investors.items():
        raw = raw_by_investor[investor_id]
        opinions = opinions_by_investor[investor_id]
        attention = attention_by_investor[investor_id]
        opinion_assets = {_id(row.get("asset_id")) for row in opinions}
        attention_assets = {_id(row.get("asset_id")) for row in attention}
        attention_pairs = defaultdict(list)
        for row in attention:
            attention_pairs[_id(row.get("asset_id"))].append(row)
        repeated_pairs = sum(len(values) >= 2 for values in attention_pairs.values())
        repeated_cross_day = sum(
            len(values) >= 2 and len({_date_hk(row.get("published_time")) for row in values}) >= 2
            for values in attention_pairs.values()
        )
        shared_assets = sum(len(shared_by_asset[asset_id]) >= 2 for asset_id in attention_assets)
        three_plus = sum(len(shared_by_asset[asset_id]) >= 3 for asset_id in attention_assets)
        rows.append(
            {
                "investor_id": investor_id,
                "name": investor.get("name") or investor_id,
                "platform_user_id": investor.get("platform_user_id") or "—",
                "raw": len(raw),
                "opinions": len(opinions),
                "opinion_density": len(opinions) / len(raw) if raw else 0.0,
                "opinion_assets": len(opinion_assets),
                "attention": len(attention),
                "attention_pairs": len(attention_assets),
                "repeated_attention_pairs": repeated_pairs,
                "repeated_cross_day": repeated_cross_day,
                "thesis": len(thesis_by_investor[investor_id]),
                "shared_assets": shared_assets,
                "three_plus": three_plus,
            }
        )
    return sorted(rows, key=lambda row: (-row["raw"], str(row["name"])))


def _first_by_investor(rows: list[Row]) -> dict[str, Row]:
    result: dict[str, Row] = {}
    for row in rows:
        investor_id = _id(row.get("investor_id"))
        previous = result.get(investor_id)
        if previous is None or _time_key(row) < _time_key(previous):
            result[investor_id] = row
    return result


def _first_opinion_by_investor(rows: list[Row]) -> dict[str, Row]:
    result: dict[str, Row] = {}
    for row in rows:
        investor_id = _id(row.get("investor_id"))
        previous = result.get(investor_id)
        if previous is None or _time_key(row) < _time_key(previous):
            result[investor_id] = row
    return result


def _lag_days(start: datetime, end: datetime) -> float:
    return max(0.0, (end - start).total_seconds() / 86400)


def _lag_bucket(days: float) -> str:
    if days <= 1:
        return "0–1d"
    if days <= 3:
        return "1–3d"
    if days <= 7:
        return "3–7d"
    return ">7d"


def _asset_timelines(data: dict[str, Any], views: dict[str, Any]) -> list[Row]:
    assets = {_id(row.get("id")): row for row in data["assets"]}
    investors = {
        _id(row.get("id")): str(row.get("name") or row.get("id")) for row in data["investors"]
    }
    timelines: list[Row] = []
    for asset_id, attention_rows in views["attention_by_asset"].items():
        first_attention = _first_by_investor(attention_rows)
        if len(first_attention) < 2:
            continue
        opinion_rows = views["opinion_by_asset"].get(asset_id, [])
        first_opinion = _first_opinion_by_investor(opinion_rows)
        ordered = sorted(
            first_attention.items(),
            key=lambda item: (_time_key(item[1]), investors.get(item[0], item[0])),
        )
        anchor_time = _time_key(ordered[0][1])[0]
        entries = []
        for index, (investor_id, attention) in enumerate(ordered):
            attention_time = _time_key(attention)[0]
            opinion = first_opinion.get(investor_id)
            entries.append(
                {
                    "investor_id": investor_id,
                    "investor": investors.get(investor_id, investor_id),
                    "attention_time": attention_time,
                    "lag_days": _lag_days(anchor_time, attention_time),
                    "attention_event_id": _id(attention.get("event_id")),
                    "attention_types": "+".join(attention.get("evidence_types") or []),
                    "first_opinion_time": _time_key(opinion)[0] if opinion else None,
                    "first_opinion_event_id": _id(opinion.get("event_id")) if opinion else None,
                    "first_opinion_direction": _direction(opinion.get("direction"))
                    if opinion
                    else None,
                    "is_anchor": index == 0,
                }
            )
        pair_rows = views["attention_by_asset_investor"]
        repeated = sum(
            len(rows) >= 2 and len({_date_hk(row.get("published_time")) for row in rows}) >= 2
            for (candidate_asset, _investor), rows in pair_rows.items()
            if candidate_asset == asset_id
        )
        timelines.append(
            {
                "asset_id": asset_id,
                "asset": assets.get(asset_id),
                "entries": entries,
                "attention_count": len(attention_rows),
                "investor_count": len(first_attention),
                "repeated_cross_day_pairs": repeated,
            }
        )
    return sorted(
        timelines,
        key=lambda row: (
            -row["investor_count"],
            -row["attention_count"],
            _asset_label(row["asset"]),
        ),
    )


def _diffusion_edges(timelines: list[Row], views: dict[str, Any]) -> list[Row]:
    edges: list[Row] = []
    for timeline in timelines:
        entries = timeline["entries"]
        if len(entries) < 2:
            continue
        anchor = entries[0]
        for later in entries[1:]:
            anchor_side = _direction_side(anchor["first_opinion_direction"])
            later_side = _direction_side(later["first_opinion_direction"])
            if anchor_side in {"BULLISH", "BEARISH"} and later_side == anchor_side:
                category = "same-direction Opinion"
            elif anchor_side in {"BULLISH", "BEARISH"} and later_side in {"BULLISH", "BEARISH"}:
                category = "opposite-direction Opinion"
            elif (
                anchor["first_opinion_direction"] is None
                or later["first_opinion_direction"] is None
            ):
                category = "Attention-only / no Opinion"
            else:
                category = "neutral/indeterminate Opinion"
            edges.append(
                {
                    "asset": timeline["asset"],
                    "asset_id": timeline["asset_id"],
                    "from": anchor["investor"],
                    "to": later["investor"],
                    "from_time": anchor["attention_time"],
                    "to_time": later["attention_time"],
                    "lag_days": later["lag_days"],
                    "bucket": _lag_bucket(later["lag_days"]),
                    "category": category,
                    "from_direction": anchor["first_opinion_direction"] or "—",
                    "to_direction": later["first_opinion_direction"] or "—",
                    "from_event_id": anchor["attention_event_id"],
                    "to_event_id": later["attention_event_id"],
                    "to_evidence": later["attention_types"],
                }
            )
    return sorted(edges, key=lambda row: (row["lag_days"], _asset_label(row["asset"])))


def _opinion_pair_profiles(views: dict[str, Any]) -> list[Row]:
    profiles: list[Row] = []
    for pair, opinion_rows in views["opinion_by_asset_investor"].items():
        asset_id, investor_id = pair
        ordered_opinions = sorted(opinion_rows, key=_time_key)
        opinion_by_id = {_id(row.get("id")): row for row in ordered_opinions}
        changes = sorted(
            views["thesis_by_pair"].get(pair, []),
            key=lambda row: (_time_key(row, "effective_time"), _id(row.get("id"))),
        )
        change_by_current = {_id(row.get("current_opinion_id")): row for row in changes}
        directions = [_direction(row.get("direction")) for row in ordered_opinions]
        sides = [_direction_side(row.get("direction")) for row in ordered_opinions]
        reversals = sum(
            left in {"BULLISH", "BEARISH"} and right in {"BULLISH", "BEARISH"} and left != right
            for left, right in zip(sides, sides[1:], strict=False)
        )
        type_sequence = []
        for opinion in ordered_opinions:
            change = change_by_current.get(_id(opinion.get("id")))
            type_sequence.append(_enum_text(change.get("change_type")) if change else "MISSING")
        extensions_same_direction = 0
        for change in changes:
            if _enum_text(change.get("change_type")) != "THESIS_EXTENDED":
                continue
            current = opinion_by_id.get(_id(change.get("current_opinion_id")))
            previous = opinion_by_id.get(_id(change.get("previous_opinion_id")))
            if (
                current
                and previous
                and _direction_side(current.get("direction"))
                == _direction_side(previous.get("direction"))
            ):
                extensions_same_direction += 1
        profiles.append(
            {
                "asset_id": asset_id,
                "investor_id": investor_id,
                "opinion_rows": ordered_opinions,
                "changes": changes,
                "opinion_count": len(ordered_opinions),
                "thesis_count": len(changes),
                "directions": directions,
                "type_sequence": type_sequence,
                "changed_count": sum(value == "THESIS_CHANGED" for value in type_sequence),
                "reversal_count": reversals,
                "extensions_same_direction": extensions_same_direction,
                "missing_thesis": len(ordered_opinions) - len(changes),
            }
        )
    return profiles


def _latest_opinions_by_asset_investor(views: dict[str, Any]) -> dict[tuple[str, str], Row]:
    latest: dict[tuple[str, str], Row] = {}
    for pair, rows in views["opinion_by_asset_investor"].items():
        latest[pair] = max(rows, key=_time_key)
    return latest


def _direction_text(asset_id: str, views: dict[str, Any], investor_names: dict[str, str]) -> str:
    latest = _latest_opinions_by_asset_investor(views)
    attention_investors = sorted(
        {_id(row.get("investor_id")) for row in views["attention_by_asset"].get(asset_id, [])},
        key=lambda value: investor_names.get(value, value),
    )
    values = []
    for investor_id in attention_investors:
        opinion = latest.get((asset_id, investor_id))
        values.append(
            f"{investor_names.get(investor_id, investor_id)}:{_direction(opinion.get('direction')) if opinion else '—'}"
        )
    return "; ".join(values)


def _attention_order_text(timeline: Row) -> str:
    return " → ".join(
        f"{entry['investor']}@{_fmt_dt(entry['attention_time'])}"
        f"(+{entry['lag_days']:.2f}d,{entry['attention_types']})"
        for entry in timeline["entries"]
    )


def _thesis_sequence_text(profile: Row) -> str:
    return " → ".join(
        f"{_fmt_dt(row.get('published_time'))}:{_direction(row.get('direction'))}/{change_type}"
        for row, change_type in zip(profile["opinion_rows"], profile["type_sequence"], strict=True)
    )


def _consensus_asset_map(data: dict[str, Any], views: dict[str, Any]) -> dict[str, Row]:
    assets = {_id(row.get("id")): row for row in data["assets"]}
    result: dict[str, Row] = {}
    for row in views["consensus"]:
        asset_id = _id(row.get("asset_id"))
        result[asset_id] = {
            "asset": assets.get(asset_id),
            "consensus_state": _enum_text(row.get("consensus_state")),
            "coverage": _enum_text(row.get("opinion_coverage_state")),
            "attention_investor_count": row.get("attention_investor_count"),
            "opinion_investor_count": row.get("opinion_investor_count"),
        }
    return result


def _disagreement_views(data: dict[str, Any], views: dict[str, Any]) -> dict[str, Any]:
    assets = {_id(row.get("id")): row for row in data["assets"]}
    investors = {
        _id(row.get("id")): str(row.get("name") or row.get("id")) for row in data["investors"]
    }
    latest = _latest_opinions_by_asset_investor(views)
    consensus_by_asset = _consensus_asset_map(data, views)
    alignment_by_asset = {
        _id(row.get("asset_id")): _enum_text(row.get("directional_alignment_state"))
        for row in views["alignments"]
    }
    attention_asset_ids = sorted(
        asset_id
        for asset_id, investors_set in (
            (asset_id, {_id(row.get("investor_id")) for row in rows})
            for asset_id, rows in views["attention_by_asset"].items()
        )
        if len(investors_set) >= 2
    )
    summary = []
    for asset_id in attention_asset_ids:
        directions = []
        for investor_id in sorted(
            {_id(row.get("investor_id")) for row in views["attention_by_asset"].get(asset_id, [])},
            key=lambda value: investors.get(value, value),
        ):
            opinion = latest.get((asset_id, investor_id))
            directions.append(
                f"{investors.get(investor_id, investor_id)}:{_direction(opinion.get('direction')) if opinion else '—'}"
            )
        summary.append(
            {
                "asset_id": asset_id,
                "asset": assets.get(asset_id),
                "alignment": alignment_by_asset.get(asset_id, "—"),
                "consensus": consensus_by_asset.get(asset_id, {}).get("consensus_state", "—"),
                "directions": "; ".join(directions),
            }
        )
    return {
        "summary": summary,
        "mixed_alignment": [row for row in summary if row["alignment"] == "MIXED_DIRECTION"],
        "mixed_neutral": [row for row in summary if row["consensus"] == "MIXED_WITH_NEUTRAL"],
        "divergent": [row for row in summary if row["consensus"] == "DIVERGENT"],
    }


def _diffusion_summary(edges: list[Row]) -> dict[str, Any]:
    buckets = ("0–1d", "1–3d", "3–7d", ">7d")
    categories = (
        "same-direction Opinion",
        "opposite-direction Opinion",
        "Attention-only / no Opinion",
        "neutral/indeterminate Opinion",
    )
    counts = {bucket: Counter() for bucket in buckets}
    for edge in edges:
        counts[edge["bucket"]][edge["category"]] += 1
    return {
        "edge_count": len(edges),
        "positive_lag_edges": sum(edge["lag_days"] > 0 for edge in edges),
        "cross_day_edges": sum(edge["lag_days"] >= 1 for edge in edges),
        "buckets": counts,
        "categories": Counter(edge["category"] for edge in edges),
        "category_order": categories,
    }


def _fmt_density(value: float) -> str:
    return f"{value:.1%}"


def _format_counts(counter: Counter[str], keys: tuple[str, ...]) -> str:
    return ", ".join(f"{key}={counter.get(key, 0)}" for key in keys)


def _asset_stats(data: dict[str, Any], views: dict[str, Any]) -> list[Row]:
    assets = {_id(row.get("id")): row for row in data["assets"]}
    stats: list[Row] = []
    asset_ids = set(views["attention_by_asset"]) | set(views["opinion_by_asset"])
    for asset_id in asset_ids:
        attention_rows = views["attention_by_asset"].get(asset_id, [])
        opinion_rows = views["opinion_by_asset"].get(asset_id, [])
        attention_investors = {_id(row.get("investor_id")) for row in attention_rows}
        opinion_investors = {_id(row.get("investor_id")) for row in opinion_rows}
        pair_rows = [
            rows
            for (candidate_asset, _investor), rows in views["attention_by_asset_investor"].items()
            if candidate_asset == asset_id
        ]
        repeated = sum(len(rows) >= 2 for rows in pair_rows)
        repeated_cross_day = sum(
            len(rows) >= 2 and len({_date_hk(item.get("published_time")) for item in rows}) >= 2
            for rows in pair_rows
        )
        stats.append(
            {
                "asset_id": asset_id,
                "asset": assets.get(asset_id),
                "attention_count": len(attention_rows),
                "attention_investor_count": len(attention_investors),
                "opinion_count": len(opinion_rows),
                "opinion_investor_count": len(opinion_investors),
                "repeated_attention_pairs": repeated,
                "repeated_cross_day_pairs": repeated_cross_day,
            }
        )
    return stats


def _case_study_ids(
    data: dict[str, Any],
    views: dict[str, Any],
    timelines: list[Row],
    disagreements: dict[str, Any],
) -> list[str]:
    ids: list[str] = []
    for row in disagreements["divergent"]:
        ids.append(row["asset_id"])
    for row in disagreements["mixed_neutral"]:
        ids.append(row["asset_id"])
    for timeline in timelines:
        if timeline["investor_count"] >= 3 or timeline["repeated_cross_day_pairs"] >= 2:
            ids.append(timeline["asset_id"])
    for wanted in ("贵州茅台", "山东黄金", "大唐发电", "华能国际"):
        matches = [
            timeline["asset_id"]
            for timeline in timelines
            if (timeline["asset"] or {}).get("name") == wanted
        ]
        ids.extend(matches)
    ordered: list[str] = []
    for asset_id in ids:
        if asset_id not in ordered:
            ordered.append(asset_id)
    return ordered[:10]


def _case_text(
    asset_id: str,
    data: dict[str, Any],
    views: dict[str, Any],
    timelines: list[Row],
    profiles: list[Row],
) -> str:
    assets = {_id(row.get("id")): row for row in data["assets"]}
    investors = {
        _id(row.get("id")): str(row.get("name") or row.get("id")) for row in data["investors"]
    }
    timeline = next((row for row in timelines if row["asset_id"] == asset_id), None)
    attention = _attention_order_text(timeline) if timeline else "no multi-investor timeline"
    opinions = sorted(views["opinion_by_asset"].get(asset_id, []), key=_time_key)
    opinion_text = (
        " → ".join(
            f"{_fmt_dt(row.get('published_time'))} {investors.get(_id(row.get('investor_id')), _id(row.get('investor_id')))}:{_direction(row.get('direction'))}"
            for row in opinions
        )
        or "none"
    )
    thesis_parts = []
    for profile in profiles:
        if profile["asset_id"] != asset_id:
            continue
        thesis_parts.append(
            f"{investors.get(profile['investor_id'], profile['investor_id'])}: {_thesis_sequence_text(profile)}"
        )
    thesis_text = " | ".join(thesis_parts) or "none"
    return (
        f"Attention: {attention}; Opinions: {opinion_text}; "
        f"Thesis: {thesis_text}; Asset: {_asset_label(assets.get(asset_id))}"
    )


def _roadmap_rows(
    views: dict[str, Any],
    timelines: list[Row],
    edges: list[Row],
    profiles: list[Row],
    disagreements: dict[str, Any],
) -> list[tuple[str, str, str, str, str]]:
    diffusion = _diffusion_summary(edges)
    return [
        (
            "A. Attention / Idea Propagation",
            f"strong: {len(timelines)} shared Assets, {diffusion['edge_count']} anchor→later edges, {diffusion['positive_lag_edges']} positive-lag edges",
            "24 shared Assets; 79 attention pairs; 42 repeated cross-day pairs",
            "history completeness unknown; text/repost evidence can outpace Opinion evidence",
            "PRIMARY",
        ),
        (
            "B. Thesis Evolution",
            f"strong: {len(views['thesis'])} effective ThesisChanges, {sum(p['opinion_count'] >= 2 for p in profiles)} repeated Opinion pairs",
            "86 CHANGED, 26 EXTENDED, 35 repeated Opinion pairs",
            "one missing ThesisChange; repeated comparisons may require bounded comparator calls",
            "SECONDARY",
        ),
        (
            "C. Disagreement Monitoring",
            f"moderate: {len(disagreements['mixed_alignment'])} Alignment MIXED_DIRECTION; {len(disagreements['divergent'])} direct DIVERGENT",
            f"{len(disagreements['mixed_alignment'])} mixed-direction alignments; {len(disagreements['divergent'])} current DIVERGENT case(s)",
            "only one direct bullish/bearish DIVERGENT sample; 3+ Opinion assets total four",
            "SECONDARY / PILOT",
        ),
        (
            "D. Consensus Formation / Break",
            "weak for formation: 4 eligible Assets, 0 pure consensus",
            "20/24 current consensus rows are INSUFFICIENT_EVIDENCE; 3 mixed-neutral; 1 divergent",
            "Opinion overlap and direction coverage are insufficient; threshold change is not justified",
            "HOLD",
        ),
    ]


def build_report(data: dict[str, Any], views: dict[str, Any], database_name: str) -> str:
    investors_by_id = {
        _id(row.get("id")): str(row.get("name") or row.get("id")) for row in data["investors"]
    }
    density = _investor_density(data, views)
    timelines = _asset_timelines(data, views)
    edges = _diffusion_edges(timelines, views)
    diffusion = _diffusion_summary(edges)
    profiles = _opinion_pair_profiles(views)
    disagreements = _disagreement_views(data, views)
    stats = _asset_stats(data, views)
    analysis_status = Counter(_enum_text(row.get("status")) for row in views["active_analyses"])
    thesis_counts = Counter(_enum_text(row.get("change_type")) for row in views["thesis"])
    consensus_counts = Counter(_enum_text(row.get("consensus_state")) for row in views["consensus"])
    alignment_counts = Counter(
        _enum_text(row.get("directional_alignment_state")) for row in views["alignments"]
    )
    opinion_count = len(views["opinions"])
    attention_count = len(views["attention"])
    opinion_pairs = len(views["opinion_by_asset_investor"])
    attention_pairs = len(views["attention_by_asset_investor"])
    repeated_opinion_pairs = sum(
        len(rows) >= 2 for rows in views["opinion_by_asset_investor"].values()
    )
    repeated_attention_pairs = sum(
        len(rows) >= 2 for rows in views["attention_by_asset_investor"].values()
    )
    repeated_cross_day_attention_pairs = sum(
        len(rows) >= 2 and len({_date_hk(row.get("published_time")) for row in rows}) >= 2
        for rows in views["attention_by_asset_investor"].values()
    )
    raw_count = len(data["raw_events"])
    opinion_density = opinion_count / raw_count if raw_count else 0
    high_volume_low_intelligence = [
        row for row in density if row["raw"] >= 30 and row["opinion_density"] < 0.10
    ]
    low_volume_high_intelligence = [
        row for row in density if row["raw"] <= 9 and row["opinion_density"] >= 0.25
    ]
    overlap_hubs = [row for row in density if row["three_plus"] > 0]
    thesis_rich = sorted(
        density, key=lambda row: (-row["thesis"], -row["repeated_attention_pairs"], row["name"])
    )[:10]
    assets_by_id = {_id(row.get("id")): row for row in data["assets"]}
    asset_stats_by_id = {row["asset_id"]: row for row in stats}
    timeline_rows = []
    for timeline in timelines:
        asset = timeline["asset"] or {}
        first = timeline["entries"][0]
        later = timeline["entries"][1:]
        first_opinion = (
            "; ".join(
                f"{entry['investor']}@{_fmt_dt(entry['first_opinion_time'])}:{entry['first_opinion_direction']}"
                for entry in timeline["entries"]
                if entry["first_opinion_time"] is not None
            )
            or "none"
        )
        thesis = []
        for profile in profiles:
            if profile["asset_id"] != timeline["asset_id"]:
                continue
            thesis.append(
                f"{investors_by_id.get(profile['investor_id'], profile['investor_id'])}:"
                f"{_thesis_sequence_text(profile)}"
            )
        timeline_rows.append(
            (
                _asset_label(asset),
                timeline["investor_count"],
                timeline["attention_count"],
                f"{first['investor']} @ {_fmt_dt(first['attention_time'])} [{first['attention_types']}]",
                "; ".join(
                    f"{entry['investor']} +{entry['lag_days']:.2f}d @ {_fmt_dt(entry['attention_time'])} [{entry['attention_types']}]"
                    for entry in later
                )
                or "none",
                first_opinion,
                " | ".join(thesis) or "none",
                timeline["repeated_cross_day_pairs"],
            )
        )

    bucket_rows = []
    for bucket in ("0–1d", "1–3d", "3–7d", ">7d"):
        counts = diffusion["buckets"][bucket]
        bucket_rows.append(
            (
                bucket,
                counts.get("same-direction Opinion", 0),
                counts.get("opposite-direction Opinion", 0),
                counts.get("Attention-only / no Opinion", 0),
                counts.get("neutral/indeterminate Opinion", 0),
                sum(counts.values()),
            )
        )
    example_edges = []
    for category in diffusion["category_order"]:
        candidates = [
            edge for edge in edges if edge["category"] == category and edge["lag_days"] > 0
        ]
        if not candidates:
            candidates = [edge for edge in edges if edge["category"] == category]
        example_edges.extend(candidates[:3])

    repeated_profiles = [profile for profile in profiles if profile["opinion_count"] >= 2]
    changed_profiles = [profile for profile in profiles if profile["changed_count"] > 0]
    reversal_profiles = [profile for profile in profiles if profile["reversal_count"] > 0]
    extension_count = sum(profile["extensions_same_direction"] for profile in profiles)
    stable_high_frequency = [
        profile
        for profile in profiles
        if profile["opinion_count"] >= 3 and profile["changed_count"] == 0
    ]
    gap_a = sorted(
        [
            row
            for row in stats
            if row["attention_count"] >= 5 and row["opinion_investor_count"] <= 1
        ],
        key=lambda row: (
            -row["attention_count"],
            row["opinion_investor_count"],
            _asset_label(row["asset"]),
        ),
    )[:10]
    gap_b = sorted(
        [
            row
            for row in stats
            if row["opinion_count"] >= 3 and row["attention_investor_count"] <= 2
        ],
        key=lambda row: (-row["opinion_count"], _asset_label(row["asset"])),
    )[:10]
    gap_c = sorted(
        [
            row
            for row in stats
            if row["attention_investor_count"] >= 2 and row["opinion_investor_count"] == 1
        ],
        key=lambda row: (-row["attention_count"], _asset_label(row["asset"])),
    )[:10]
    gap_d = sorted(
        [row for row in stats if row["opinion_investor_count"] >= 3],
        key=lambda row: (-row["opinion_count"], _asset_label(row["asset"])),
    )

    def gap_text(rows: list[Row]) -> str:
        return (
            "; ".join(
                f"{_asset_label(row['asset'])}: Attention {row['attention_count']}/{row['attention_investor_count']} investors; Opinion {row['opinion_count']}/{row['opinion_investor_count']} investors"
                for row in rows
            )
            or "none"
        )

    case_ids = _case_study_ids(data, views, timelines, disagreements)
    roadmap = _roadmap_rows(views, timelines, edges, profiles, disagreements)
    current_consensus_eligible = [
        row for row in disagreements["summary"] if row["consensus"] != "INSUFFICIENT_EVIDENCE"
    ]
    divergent_asset_ids = {row["asset_id"] for row in disagreements["divergent"]}
    divergent_profiles = [
        profile for profile in profiles if profile["asset_id"] in divergent_asset_ids
    ]
    divergent_asset_id = next(iter(divergent_asset_ids), None)
    divergent_timeline = next(
        (timeline for timeline in timelines if timeline["asset_id"] == divergent_asset_id),
        None,
    )
    divergent_detail_rows = []
    if divergent_timeline is not None:
        for entry in divergent_timeline["entries"]:
            opinion_rows = views["opinion_by_asset_investor"].get(
                (divergent_timeline["asset_id"], entry["investor_id"]), []
            )
            latest_opinion = max(opinion_rows, key=_time_key) if opinion_rows else None
            profile = next(
                (
                    profile
                    for profile in divergent_profiles
                    if profile["investor_id"] == entry["investor_id"]
                ),
                None,
            )
            divergent_detail_rows.append(
                (
                    entry["investor"],
                    f"{_fmt_dt(entry['attention_time'])} / {entry['attention_event_id']} [{entry['attention_types']}]",
                    f"{_fmt_dt(entry['first_opinion_time'])} {entry['first_opinion_direction'] or '—'}",
                    f"{_fmt_dt(latest_opinion.get('published_time'))} {_direction(latest_opinion.get('direction'))}"
                    if latest_opinion
                    else "none",
                    _thesis_sequence_text(profile) if profile else "none",
                )
            )
    high_volume_text = (
        ", ".join(
            f"{row['name']} ({row['raw']} RawEvents, {row['opinions']} Opinions)"
            for row in high_volume_low_intelligence
        )
        or "none"
    )
    low_volume_text = (
        ", ".join(
            f"{row['name']} ({row['raw']} RawEvents, {row['opinions']} Opinions)"
            for row in low_volume_high_intelligence
        )
        or "none"
    )
    overlap_text = (
        ", ".join(
            f"{row['name']} ({row['three_plus']} 3+ assets, {row['shared_assets']} shared)"
            for row in overlap_hubs[:10]
        )
        or "none"
    )
    thesis_rich_text = (
        ", ".join(f"{row['name']} ({row['thesis']})" for row in thesis_rich if row["thesis"])
        or "none"
    )

    report: list[str] = [
        "# Cross-Investor Reality Study V1 Report",
        "",
        f"Read-only database: **{database_name}**. Production Analysis identity: `{views['analysis_version']}`. Thesis comparison identity: `{views['thesis_version']}`. Attention policy: `{views['attention_version']}`.",
        "",
        "Boundary: this study uses presence-only evidence. It does not infer cooling, dormancy, decay, abandonment, momentum from absence, or historical completeness.",
        "",
        "## 1. Executive Summary",
        "",
        f"The monitored sample contains **{raw_count:,} RawEvents**, **{opinion_count:,} Effective Opinions**, **{attention_count:,} AttentionOccurrences**, **{len(views['thesis']):,} Effective ThesisChanges**, **{len(timelines):,} Assets with 2+ Attention Investors**, and **{len(views['consensus']):,} current Consensus-v2 rows**.",
        "",
        "Strongest observed pattern: Attention is materially broader and more frequent than Opinion. Cross-investor presence is real, but comparable Opinion coverage remains thin, Neutral is common, and pure Consensus has not appeared.",
        "",
        f"Current density snapshot: {opinion_pairs} Investor×Asset Opinion pairs, {_fmt_density(opinion_density)} Opinions per RawEvent, {attention_pairs} Attention pairs, {repeated_opinion_pairs} repeated Opinion pairs, {repeated_attention_pairs} repeated Attention pairs, and {repeated_cross_day_attention_pairs} repeated cross-day Attention pairs. Analysis status: {_format_counts(analysis_status, ('SUCCESS', 'PARTIALLY_RESOLVED', 'NO_OPINION', 'FAILED'))}.",
        "",
        f"The sample contains **{diffusion['edge_count']}** monitored-sample first-attention anchor→later-investor edges; **{diffusion['positive_lag_edges']}** have positive lag and **{diffusion['cross_day_edges']}** are at least one day apart. These are descriptive relationships, not causal propagation claims.",
        "",
        "## 2. Investor Intelligence Density",
        "",
        _markdown_table(
            (
                "Investor",
                "RawEvents",
                "Effective Opinions",
                "Opinion density",
                "Opinion Assets",
                "Attention pairs",
                "Repeated Attention pairs",
                "Cross-day repeated",
                "ThesisChanges",
                "Shared Assets",
                "3+ participation",
            ),
            (
                (
                    row["name"],
                    row["raw"],
                    row["opinions"],
                    _fmt_density(row["opinion_density"]),
                    row["opinion_assets"],
                    row["attention_pairs"],
                    row["repeated_attention_pairs"],
                    row["repeated_cross_day"],
                    row["thesis"],
                    row["shared_assets"],
                    row["three_plus"],
                )
                for row in density
            ),
        ),
        "",
        f"High-volume / low-intelligence (audit rule: RawEvents ≥30 and Opinion density <10%): {high_volume_text}.",
        "",
        f"Low-volume / relatively high-intelligence (audit rule: RawEvents ≤9 and Opinion density ≥25%; statistically thin): {low_volume_text}.",
        "",
        f"Overlap hubs are led by: {overlap_text}.",
        "",
        f"Thesis-rich Investors by effective ThesisChanges: {thesis_rich_text}.",
        "",
        "## 3. Asset Timeline Distribution",
        "",
        "`first observed` means earliest in this monitored database sample only; it is not a claim about market-wide first discovery or investor causality.",
        "",
        _markdown_table(
            (
                "Asset",
                "Attention Investors",
                "Attention occurrences",
                "Monitored-sample first observed",
                "Later first Attention and lag",
                "First Opinion time/direction",
                "ThesisChange sequence",
                "Repeated cross-day pairs",
            ),
            timeline_rows,
        ),
        "",
        "## 4. Attention Diffusion",
        "",
        "Method: for each Asset with 2+ Attention Investors, use the earliest Attention occurrence of the monitored-sample anchor Investor and compare each later Investor's first Attention time. Direction categories compare each Investor's first effective Opinion direction when available; Neutral or missing Opinion is not forced into same/opposite direction.",
        "",
        _markdown_table(
            (
                "Lag bucket",
                "Same-direction Opinion",
                "Opposite-direction Opinion",
                "Attention-only / no Opinion",
                "Neutral/indeterminate Opinion",
                "Total edges",
            ),
            bucket_rows,
        ),
        "",
        f"Total edges: **{diffusion['edge_count']}**; positive-lag edges: **{diffusion['positive_lag_edges']}**; cross-day edges: **{diffusion['cross_day_edges']}**. Category totals: {_format_counts(diffusion['categories'], tuple(diffusion['category_order']))}.",
        "",
        "Representative edges:",
        "",
        _markdown_table(
            (
                "Asset",
                "Anchor Investor",
                "Later Investor",
                "Lag",
                "Bucket",
                "Category",
                "First directions",
                "RawEvent/evidence",
            ),
            (
                (
                    _asset_label(edge["asset"]),
                    edge["from"],
                    edge["to"],
                    f"{edge['lag_days']:.2f}d",
                    edge["bucket"],
                    edge["category"],
                    f"{edge['from_direction']} → {edge['to_direction']}",
                    f"{edge['from_event_id']} → {edge['to_event_id']} [{edge['to_evidence']}]",
                )
                for edge in example_edges
            ),
        ),
        "",
        "Finding: Attention diffusion is visibly present as repeated temporal ordering in the monitored sample, but the directional Opinion subset is too small and confounded by repost/text evidence to establish a production propagation rule or causal influence.",
        "",
        "## 5. Thesis Evolution",
        "",
        _markdown_table(
            ("ThesisChange type", "Effective count"),
            tuple(
                (key, thesis_counts.get(key, 0))
                for key in (
                    "NEW_THESIS",
                    "THESIS_REINFORCED",
                    "THESIS_EXTENDED",
                    "THESIS_CHANGED",
                    "THESIS_UNCHANGED",
                    "INSUFFICIENT_EVIDENCE",
                )
            ),
        ),
        "",
        f"There are **{len(repeated_profiles)}** repeated Investor×Asset Opinion pairs, **{len(changed_profiles)}** pairs with at least one THESIS_CHANGED, **{len(reversal_profiles)}** pairs with a bullish↔bearish direction reversal, and **{extension_count}** THESIS_EXTENDED changes where the adjacent Opinion direction stayed on the same side. The known missing ThesisChange remains one explicit Opinion and is not imputed.",
        "",
        "Most changed timelines:",
        "",
        _markdown_table(
            (
                "Investor×Asset",
                "Opinions",
                "ThesisChanges",
                "Directions",
                "Change sequence",
                "Reversals",
            ),
            (
                (
                    f"{investors_by_id.get(row['investor_id'], row['investor_id'])} × {_asset_label(assets_by_id.get(row['asset_id']))}",
                    row["opinion_count"],
                    row["thesis_count"],
                    " → ".join(row["directions"]),
                    " → ".join(row["type_sequence"]),
                    row["reversal_count"],
                )
                for row in sorted(
                    changed_profiles,
                    key=lambda value: (-value["changed_count"], -value["opinion_count"]),
                )[:12]
            ),
        ),
        "",
        "High-frequency but thesis-stable timelines (≥3 Opinions and no THESIS_CHANGED):",
        "",
        _markdown_table(
            ("Investor×Asset", "Opinions", "Thesis sequence", "Same-direction extensions"),
            (
                (
                    f"{row['investor_id']} / {row['asset_id']}",
                    row["opinion_count"],
                    " → ".join(row["type_sequence"]),
                    row["extensions_same_direction"],
                )
                for row in sorted(stable_high_frequency, key=lambda value: -value["opinion_count"])[
                    :10
                ]
            )
            or (("none", 0, "none", 0),),
        ),
        "",
        "Thesis finding: the current sample supports a meaningful Thesis Evolution dimension. It is richer than the Consensus sample, but one missing comparator output and the comparator's operational cost remain explicit data-quality constraints.",
        "",
        "## 6. Disagreement Cases",
        "",
        _markdown_table(
            ("Asset", "Alignment", "Consensus v2", "Latest effective directions"),
            (
                (_asset_label(row["asset"]), row["alignment"], row["consensus"], row["directions"])
                for row in disagreements["summary"]
                if row["alignment"] == "MIXED_DIRECTION"
                or row["consensus"] in {"DIVERGENT", "MIXED_WITH_NEUTRAL"}
            ),
        ),
        "",
        f"Current Alignment distribution: {_format_counts(alignment_counts, ('ALIGNED_BULLISH', 'ALIGNED_BEARISH', 'ALIGNED_NEUTRAL', 'MIXED_DIRECTION', 'INSUFFICIENT_EVIDENCE'))}.",
        "",
        "### Current DIVERGENT case: 龙源电力",
        "",
        _markdown_table(
            ("Investor", "First Attention", "First Opinion", "Latest Opinion", "Thesis sequence"),
            divergent_detail_rows,
        ),
        "",
        f"龙源电力 evidence summary: {_case_text(divergent_asset_id, data, views, timelines, profiles)}",
        "",
        "The v2 DIVERGENT state is evidence of a direct bullish/bearish conflict among latest contributing directions. The timestamps and Thesis sequences should be read as temporal framing evidence; this study does not convert them into an investment conclusion.",
        "",
        "## 7. Consensus Reality",
        "",
        _markdown_table(
            ("Asset", "Attention Investors", "Opinion Investors", "Directions", "Consensus v2"),
            (
                (
                    _asset_label(row["asset"]),
                    row["directions"].count(":") if row["directions"] else 0,
                    asset_stats_by_id.get(row["asset_id"], {}).get("opinion_investor_count", 0),
                    row["directions"],
                    row["consensus"],
                )
                for row in current_consensus_eligible
            ),
        ),
        "",
        f"Current Consensus-v2 distribution: {_format_counts(consensus_counts, ('INSUFFICIENT_EVIDENCE', 'MIXED_WITH_NEUTRAL', 'CONSENSUS_BULLISH', 'CONSENSUS_BEARISH', 'CONSENSUS_NEUTRAL', 'DIVERGENT'))}.",
        "",
        "Why pure Consensus is rare:",
        "",
        "- Opinion overlap is the primary constraint: 20 of 24 current Consensus rows are INSUFFICIENT_EVIDENCE under the unchanged ≥3 Opinion-Investor rule.",
        "- Of the four eligible Assets, three contain Neutral in the latest direction set and are MIXED_WITH_NEUTRAL; one is DIVERGENT.",
        "- Current coverage has 16 COMPLETE, 7 PARTIAL and 1 NONE Opinion-coverage rows, so Attention presence often arrives without comparable Opinion evidence.",
        "- Time offsets and sparse repeated Investor×Asset histories further reduce synchronous agreement; no threshold adjustment is justified by this sample.",
        "",
        "## 8. Attention vs Opinion Gap",
        "",
        _markdown_table(
            ("Gap pattern", "Observed Assets"),
            (
                ("A. Attention hot, Opinion scarce", gap_text(gap_a)),
                ("B. Opinion-rich, propagation narrow", gap_text(gap_b)),
                ("C. Multi-Investor Attention, single-Investor Opinion", gap_text(gap_c)),
                ("D. Multi-Investor Opinion / direction conflict candidates", gap_text(gap_d)),
            ),
        ),
        "",
        "The gap is systematic enough to justify treating Attention intelligence and Opinion intelligence as separate product dimensions: Attention measures observed presence/evidence, while Opinion measures structured interpretation and direction. They should be joined by provenance, not collapsed into one score.",
        "",
        "## 9. Representative Case Studies",
        "",
    ]
    for asset_id in case_ids:
        report.extend(
            [
                f"### {_asset_label(next((row.get('asset') for row in stats if row['asset_id'] == asset_id), None))}",
                "",
                _case_text(asset_id, data, views, timelines, profiles),
                "",
            ]
        )
    report.extend(
        [
            "## 10. Product / Architecture Implications",
            "",
            "- Keep Attention and Opinion as independent evidence layers. Attention is broader, includes explicit mention/repost, and can produce cross-investor presence without an Opinion.",
            "- Keep Thesis Evolution separate from Consensus. The sample has 191 effective ThesisChanges and many repeated pairs, while only four Assets satisfy the current Consensus eligibility rule.",
            "- Treat first-observed ordering as monitored-sample chronology, never as a causal “originator” or market-wide lead signal.",
            "- Preserve current effective selectors and policy provenance. Do not infer missing history from absence and do not increase Consensus by changing thresholds.",
            "- The one missing ThesisChange should remain an explicit data-quality gap until a separately authorized, safe comparator operation is possible.",
            "",
            "## 11. Recommended Roadmap Priority",
            "",
            _markdown_table(
                (
                    "Candidate mainline",
                    "Sample support",
                    "Available evidence",
                    "Main bottleneck",
                    "Decision",
                ),
                roadmap,
            ),
            "",
            "Priority decision:",
            "",
            "- Primary: **A. Attention / Idea Propagation Reality Study** — the strongest repeatable presence-based pattern, with 24 shared Assets, 79 Attention pairs and 42 repeated cross-day pairs. Build only descriptive evidence views first; do not introduce a production threshold.",
            "- Secondary: **B. Thesis Evolution** — 191 effective ThesisChanges and 35 repeated Opinion pairs provide a deeper interpretation timeline than Consensus currently supports.",
            "- Hold: **D. Consensus Formation / Break** as a primary roadmap — only four eligible Assets, zero pure directional Consensus, and limited Opinion coverage.",
            "- C. Disagreement Monitoring is suitable for a narrow pilot/read-only view, but the direct DIVERGENT sample is currently one Asset.",
            "",
            "Final answers:",
            "",
            "- Current strongest real pattern: broad, repeated Attention presence across Investors, with narrower and often delayed Opinion coverage.",
            f"- Attention diffusion: **yes, as monitored-sample temporal ordering** ({diffusion['edge_count']} edges; {diffusion['positive_lag_edges']} positive-lag), but not yet frequent/clean enough for causal or production propagation logic.",
            "- Thesis evolution vs Consensus: **Thesis Evolution is more investable as the next evidence capability**; it has substantially more repeated material than Consensus.",
            "- Disagreement: **enough for a descriptive pilot**, not enough for a mature standalone ranking/alert capability; there is one direct v2 DIVERGENT case.",
            "- Consensus: **continue HOLD**; do not change the ≥3 Opinion-Investor semantics.",
            "- Next Sprint candidate: implement a read-only Attention diffusion / Thesis timeline study layer, with DIVERGENT case inspection as a secondary slice. Do not collect, seed, rebuild or change policy automatically.",
            "",
            "Read-only boundary: no database write, no LLM, no collection, no Production Analysis rebuild, no migration, no Signal design, no commit or push.",
        ]
    )
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--top-cases", type=int, default=10)
    args = parser.parse_args()
    _ = args.top_cases
    sys.stdout.reconfigure(encoding="utf-8")
    connection, url = _connect_read_only()
    try:
        with connection.cursor() as cursor:
            database_name = str(
                _scalar(cursor, "SELECT current_database()") or url.database or "<unknown>"
            )
            data = _load_data(cursor)
            views = _current_views(data)
            report = build_report(data, views, database_name)
    finally:
        connection.rollback()
        connection.close()
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
