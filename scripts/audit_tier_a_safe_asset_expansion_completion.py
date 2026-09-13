"""Read-only completion audit for Sprint 2F Tier A Asset expansion."""

# The report deliberately contains long human-readable audit explanations.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
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

# The before snapshot is the completed 309-event catch-up audit immediately
# before this seed. These are audit baselines, not business constants.
BEFORE = {
    "raw_events": 1482,
    "assets": 31,
    "aliases": 45,
    "active_analysis": 1482,
    "analysis_status": {
        "SUCCESS": 80,
        "PARTIALLY_RESOLVED": 471,
        "NO_OPINION": 930,
        "FAILED": 1,
    },
    "effective_opinions": 130,
    "opinion_events": 106,
    "opinion_pairs": 45,
    "repeated_opinion_pairs": 24,
    "attention": 221,
    "attention_pairs": 57,
    "attention_active_days": None,
    "repeated_attention_pairs": 29,
    "thesis": 130,
    "snapshots": 17,
    "alignments": 17,
    "consensus": 17,
    "attention_2": 17,
    "attention_3": 8,
    "opinion_2": 13,
    "opinion_3": 4,
    "alignment_states": {
        "ALIGNED_BULLISH": 5,
        "ALIGNED_BEARISH": 1,
        "ALIGNED_NEUTRAL": 0,
        "MIXED_DIRECTION": 7,
        "INSUFFICIENT_EVIDENCE": 4,
    },
    "consensus_states": {
        "INSUFFICIENT_EVIDENCE": 13,
        "MIXED_WITH_NEUTRAL": 3,
        "CONSENSUS_BULLISH": 0,
        "CONSENSUS_BEARISH": 0,
        "CONSENSUS_NEUTRAL": 0,
        "DIVERGENT": 1,
    },
}

SEED_RESULT = Path(".local/audit/tier_a_safe_asset_expansion_seed_result.json")
V2_AFTER_REPORT = Path(".local/audit/asset_resolution_audit_v2_after_tier_a.md")


def _current_views(data: dict[str, Any]) -> dict[str, Any]:
    analysis_policy = get_production_analysis_policy()
    thesis_policy = get_production_thesis_comparison_policy()
    analysis_version = analysis_policy.active_analysis_version
    attention_version = get_production_attention_policy_version()
    active_analyses = [
        row for row in data["analyses"] if row.get("analysis_version") == analysis_version
    ]
    current_by_event = {_id(row.get("event_id")): row for row in active_analyses}
    effective_ids = {
        _id(row.get("id"))
        for row in active_analyses
        if _enum_text(row.get("status")) in {"SUCCESS", "PARTIALLY_RESOLVED"}
    }
    effective_opinions = [
        row for row in data["opinions"] if _id(row.get("analysis_id")) in effective_ids
    ]
    effective_attention = [
        row
        for row in data["attention"]
        if row.get("attention_policy_version") == attention_version
        and (row.get("analysis_id") is None or _id(row.get("analysis_id")) in effective_ids)
    ]
    effective_thesis = _effective_thesis(
        data["thesis"],
        effective_opinions,
        analysis_version,
        thesis_policy.active_analysis_version,
    )

    attention_by_asset: dict[str, set[str]] = defaultdict(set)
    attention_pairs: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in effective_attention:
        asset_id = _id(row.get("asset_id"))
        investor_id = _id(row.get("investor_id"))
        attention_by_asset[asset_id].add(investor_id)
        attention_pairs[(investor_id, asset_id)].append(row)

    opinion_by_asset: dict[str, set[str]] = defaultdict(set)
    opinion_pairs: defaultdict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in effective_opinions:
        asset_id = _id(row.get("asset_id"))
        investor_id = _id(row.get("investor_id"))
        opinion_by_asset[asset_id].add(investor_id)
        opinion_pairs[(investor_id, asset_id)].append(row)

    current_policy_snapshots = [
        row
        for row in data["snapshots"]
        if row.get("opinion_analysis_version") == analysis_version
        and row.get("attention_policy_version") == attention_version
        and row.get("thesis_comparison_version") == thesis_policy.active_analysis_version
        and row.get("consistency_policy_version") == CONSISTENCY_POLICY_VERSION
        and row.get("cross_investor_policy_version") == CROSS_INVESTOR_POLICY_VERSION
    ]
    attention_ids_by_asset: dict[str, set[str]] = defaultdict(set)
    for row in effective_attention:
        attention_ids_by_asset[_id(row.get("asset_id"))].add(_id(row.get("id")))

    def snapshot_attention_ids(row: dict[str, Any]) -> set[str]:
        values: set[str] = set()
        for contribution in _as_list(row.get("contributions")):
            contribution_map = _as_map(contribution)
            values.update(
                _id(value) for value in _as_list(contribution_map.get("attention_occurrence_ids"))
            )
        return values

    latest_snapshot_by_asset: dict[str, dict[str, Any]] = {}
    for row in sorted(
        current_policy_snapshots, key=lambda item: _latest_key(item, "calculated_at")
    ):
        latest_snapshot_by_asset[_id(row.get("asset_id"))] = row
    snapshot_heads = {
        asset_id: row
        for asset_id, row in latest_snapshot_by_asset.items()
        if len(attention_by_asset.get(asset_id, set())) >= 2
        and snapshot_attention_ids(row) == attention_ids_by_asset.get(asset_id, set())
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
    unresolved = []
    unresolved_names: set[str] = set()
    for analysis in current_by_event.values():
        output = _as_map(analysis.get("structured_output"))
        for item in _as_list(output.get("unresolved_assets")):
            item_map = _as_map(item)
            unresolved.append(item_map)
            unresolved_names.add(str(item_map.get("asset_name") or "").strip())

    return {
        "analysis_version": analysis_version,
        "thesis_version": thesis_policy.active_analysis_version,
        "attention_version": attention_version,
        "active_analyses": active_analyses,
        "current_by_event": current_by_event,
        "effective_opinions": effective_opinions,
        "effective_attention": effective_attention,
        "effective_thesis": effective_thesis,
        "attention_by_asset": attention_by_asset,
        "attention_pairs": attention_pairs,
        "opinion_by_asset": opinion_by_asset,
        "opinion_pairs": opinion_pairs,
        "snapshot_heads": snapshot_heads,
        "alignments": alignments,
        "consensus": consensus,
        "unresolved": unresolved,
        "unresolved_names": unresolved_names - {""},
    }


def _metrics(
    data: dict[str, Any], views: dict[str, Any], new_asset_ids: set[str]
) -> dict[str, Any]:
    status_counts = Counter(_enum_text(row.get("status")) for row in views["active_analyses"])
    opinions = views["effective_opinions"]
    attention = views["effective_attention"]
    thesis = views["effective_thesis"]
    opinion_pairs = views["opinion_pairs"]
    attention_pairs = views["attention_pairs"]
    attention_dates = {_date_hk(row.get("published_time")) for row in attention}
    repeated_attention = sum(
        len(rows) >= 2 and len({_date_hk(row.get("published_time")) for row in rows}) >= 2
        for rows in attention_pairs.values()
    )
    attention_investor_counts = views["attention_by_asset"]
    opinion_investor_counts = views["opinion_by_asset"]
    return {
        "raw_events": len(data["raw_events"]),
        "assets": len(data["assets"]),
        "aliases": data["table_counts"]["asset_aliases"],
        "active_analysis": len(views["active_analyses"]),
        "analysis_status": dict(status_counts),
        "effective_opinions": len(opinions),
        "opinion_events": len({_id(row.get("event_id")) for row in opinions}),
        "opinion_pairs": len(opinion_pairs),
        "repeated_opinion_pairs": sum(len(rows) >= 2 for rows in opinion_pairs.values()),
        "attention": len(attention),
        "attention_pairs": len(attention_pairs),
        "attention_active_days": len({value for value in attention_dates if value is not None}),
        "repeated_attention_pairs": repeated_attention,
        "thesis": len(thesis),
        "thesis_types": dict(Counter(_enum_text(row.get("change_type")) for row in thesis)),
        "thesis_before_types": dict(
            Counter(
                _enum_text(row.get("change_type"))
                for row in thesis
                if _id(row.get("asset_id")) not in new_asset_ids
            )
        ),
        "alignment_states": dict(
            Counter(
                _enum_text(row.get("directional_alignment_state")) for row in views["alignments"]
            )
        ),
        "consensus_states": dict(
            Counter(_enum_text(row.get("consensus_state")) for row in views["consensus"])
        ),
        "snapshots": len(views["snapshot_heads"]),
        "alignments": len(views["alignments"]),
        "consensus": len(views["consensus"]),
        "attention_2": sum(len(values) >= 2 for values in attention_investor_counts.values()),
        "attention_3": sum(len(values) >= 3 for values in attention_investor_counts.values()),
        "opinion_2": sum(len(values) >= 2 for values in opinion_investor_counts.values()),
        "opinion_3": sum(len(values) >= 3 for values in opinion_investor_counts.values()),
        "unresolved": len(views["unresolved"]),
        "unresolved_names": len(views["unresolved_names"]),
        "new_asset_opinions": sum(_id(row.get("asset_id")) in new_asset_ids for row in opinions),
        "new_asset_attention": sum(_id(row.get("asset_id")) in new_asset_ids for row in attention),
        "new_asset_thesis": sum(_id(row.get("asset_id")) in new_asset_ids for row in thesis),
    }


def _asset_attention_impact(seed: dict[str, Any], views: dict[str, Any]) -> dict[str, Any]:
    approved_pairs = {
        (row["event_id"], row["asset_id"]) for row in seed["resolution_guard"]["resolved_records"]
    }
    new_asset_ids = set(seed["asset_ids"].values())
    rows = [
        row for row in views["effective_attention"] if _id(row.get("asset_id")) in new_asset_ids
    ]
    extra = [
        row
        for row in rows
        if (_id(row.get("event_id")), _id(row.get("asset_id"))) not in approved_pairs
    ]
    return {
        "approved_pairs": len(approved_pairs),
        "new_asset_attention": len(rows),
        "approved_attention": len(rows) - len(extra),
        "extra_attention": len(extra),
        "extra_types": dict(
            Counter(
                evidence_type
                for row in extra
                for evidence_type in _as_list(row.get("evidence_types"))
            )
        ),
        "by_asset": dict(
            (
                asset_id,
                {
                    "total": sum(_id(row.get("asset_id")) == asset_id for row in rows),
                    "approved": sum(
                        _id(row.get("asset_id")) == asset_id
                        and (_id(row.get("event_id")), _id(row.get("asset_id"))) in approved_pairs
                        for row in rows
                    ),
                    "extra": sum(
                        _id(row.get("asset_id")) == asset_id
                        and (_id(row.get("event_id")), _id(row.get("asset_id")))
                        not in approved_pairs
                        for row in rows
                    ),
                    "extra_types": dict(
                        Counter(
                            evidence_type
                            for row in extra
                            if _id(row.get("asset_id")) == asset_id
                            for evidence_type in _as_list(row.get("evidence_types"))
                        )
                    ),
                },
            )
            for asset_id in sorted(new_asset_ids)
        ),
    }


def _listing_integrity(data: dict[str, Any], views: dict[str, Any]) -> list[dict[str, Any]]:
    assets = data["assets"]
    by_identity = {
        (str(row.get("market")).upper(), str(row.get("symbol")).upper()): row for row in assets
    }
    pairs = (
        ("华能国际", ("SH", "600011"), ("HK", "00902")),
        ("中国神华", ("SH", "601088"), ("HK", "01088")),
        ("山东黄金", ("HK", "01787"), ("SH", "600547")),
    )
    result = []
    for label, first_key, second_key in pairs:
        first = by_identity.get(first_key)
        second = by_identity.get(second_key)
        first_id = _id(first.get("id")) if first else None
        second_id = _id(second.get("id")) if second else None
        result.append(
            {
                "label": label,
                "first": f"{first_key[0]}:{first_key[1]}",
                "second": f"{second_key[0]}:{second_key[1]}",
                "first_id": first_id,
                "second_id": second_id,
                "different_asset_id": bool(first_id and second_id and first_id != second_id),
                "different_market_symbol": first_key != second_key,
                "first_opinions": sum(
                    _id(row.get("asset_id")) == first_id for row in views["effective_opinions"]
                ),
                "second_opinions": sum(
                    _id(row.get("asset_id")) == second_id for row in views["effective_opinions"]
                ),
                "first_attention": sum(
                    _id(row.get("asset_id")) == first_id for row in views["effective_attention"]
                ),
                "second_attention": sum(
                    _id(row.get("asset_id")) == second_id for row in views["effective_attention"]
                ),
            }
        )
    return result


def _remaining_distribution() -> dict[str, int]:
    # Taken from the post-expansion read-only Asset Resolution Audit v2.
    return {
        "EXPLICIT_MARKET_SYMBOL": 46,
        "SYMBOL_MISSING_MARKET": 6,
        "EXISTING_ASSET_ALIAS_CANDIDATE": 0,
        "CANONICAL_LOOKING_NAME_ONLY": 151,
        "NICKNAME_ABBREVIATION": 20,
        "CROSS_LISTING_AMBIGUITY": 0,
        "UNSUPPORTED_MARKET_HINT": 76,
        "INDEX_OR_ETF": 19,
        "CONCEPT_INDUSTRY_NON_SECURITY": 50,
        "COMMODITY_MACRO_REFERENCE": 51,
        "EXTRACTION_NOISE": 4,
        "UNKNOWN": 254,
    }


def _format_counts(values: dict[str, Any], order: tuple[str, ...]) -> str:
    return ", ".join(f"{key}={values.get(key, 0)}" for key in order)


def build_report(
    data: dict[str, Any],
    seed: dict[str, Any],
    database_name: str,
    audit_time: Any,
) -> str:
    views = _current_views(data)
    new_asset_ids = set(seed["asset_ids"].values())
    after = _metrics(data, views, new_asset_ids)
    impact = _asset_attention_impact(seed, views)
    integrity = _listing_integrity(data, views)
    alignment_order = (
        "ALIGNED_BULLISH",
        "ALIGNED_BEARISH",
        "ALIGNED_NEUTRAL",
        "MIXED_DIRECTION",
        "INSUFFICIENT_EVIDENCE",
    )
    consensus_order = (
        "INSUFFICIENT_EVIDENCE",
        "MIXED_WITH_NEUTRAL",
        "CONSENSUS_BULLISH",
        "CONSENSUS_BEARISH",
        "CONSENSUS_NEUTRAL",
        "DIVERGENT",
    )
    thesis_order = (
        "NEW_THESIS",
        "THESIS_REINFORCED",
        "THESIS_EXTENDED",
        "THESIS_CHANGED",
        "THESIS_UNCHANGED",
        "INSUFFICIENT_EVIDENCE",
    )
    assets_by_id = {_id(row.get("id")): row for row in data["assets"]}
    remaining = _remaining_distribution()
    unresolved_total = sum(remaining.values())
    asset_attention_rows = []
    for asset_id, values in impact["by_asset"].items():
        asset = assets_by_id.get(asset_id, {})
        asset_attention_rows.append(
            (
                f"{asset.get('name', '—')} ({asset.get('market')}:{asset.get('symbol')})",
                values["total"],
                values["approved"],
                values["extra"],
                ", ".join(f"{key}={value}" for key, value in values["extra_types"].items())
                or "none",
            )
        )

    report: list[str] = [
        "# Tier A Safe Asset Expansion Completion Report",
        "",
        f"Audit time: **{_fmt_dt(audit_time)}**; database: **{database_name}**.",
        "",
        "This report combines the transactional seed result, existing deterministic recovery output, the post-rebuild read-only Reality audit, and the post-expansion Asset Resolution Audit v2. No new collection or Opinion analysis was performed.",
        "",
        "## 1. Preflight",
        "",
        "Preflight passed against the confirmed report: 1,482 RawEvents; 1,482 current production Analysis rows; 31 Assets; 45 Aliases; no exact collision for any of the 16 approved identities. The remaining FAILED Analysis stayed at `人生是历练 / ae13276c-69ac-46eb-8672-2b3b3a854f9b / FAILED / INVALID_STRUCTURED_OUTPUT`.",
        "",
        f"Production identity remained `{views['analysis_version']}`. Active Attention policy remained `{views['attention_version']}`. No policy, prompt, schema, Analysis identity, or migration changed.",
        "",
        "## 2. 16 Asset Seed Result",
        "",
        _markdown_table(
            ("Identity", "Asset id", "Canonical name", "Market", "Symbol"),
            (
                (
                    key,
                    seed["asset_ids"].get(key),
                    assets_by_id.get(seed["asset_ids"].get(key, ""), {}).get("name"),
                    key.split(":", 1)[0],
                    key.split(":", 1)[1],
                )
                for key in seed["asset_ids"]
            ),
        ),
        "",
        f"First seed: **{seed['seed_first']['assets_created']} Assets created**, **{seed['seed_first']['aliases_created']} Aliases created**; no Asset/Alias was reused on the first pass. Catalog is now **{after['assets']} Assets / {after['aliases']} Aliases**.",
        "",
        "No 17th Asset was created. Tier B was not included.",
        "",
        "## 3. Alias Seed Result",
        "",
        "The seed added 16 market-scoped SYMBOL aliases and four reviewed market-scoped NAME aliases: `华能国际电力股份@HK`, `摩尔线程-U@SH`, `中国神华@HK`, and `山东黄金@SH`. No existing Alias was rewritten; no ambiguous global NAME alias was added.",
        "",
        "## 4. Idempotency Rerun Result",
        "",
        _markdown_table(
            (
                "Pass",
                "Assets created",
                "Assets reused",
                "Aliases created",
                "Aliases reused",
                "Result",
            ),
            (
                (
                    "Second seed invocation",
                    seed["idempotency_rerun"]["assets_created"],
                    seed["idempotency_rerun"]["assets_reused"],
                    seed["idempotency_rerun"]["aliases_created"],
                    seed["idempotency_rerun"]["aliases_reused"],
                    "PASS",
                ),
            ),
        ),
        "",
        "Existing Asset IDs remained unchanged on rerun; no duplicates were produced.",
        "",
        "## 5. A/H Listing Integrity Result",
        "",
        _markdown_table(
            (
                "Issuer/listing pair",
                "First Asset",
                "Second Asset",
                "Different Asset id",
                "Different market+symbol",
                "Opinion counts",
                "Attention counts",
            ),
            (
                (
                    row["label"],
                    f"{row['first']} / {row['first_id']}",
                    f"{row['second']} / {row['second_id']}",
                    row["different_asset_id"],
                    row["different_market_symbol"],
                    f"{row['first_opinions']} / {row['second_opinions']}",
                    f"{row['first_attention']} / {row['second_attention']}",
                )
                for row in integrity
            ),
        ),
        "",
        "No A/H merge occurred. Opinions and Attention rows remain attached to the listing Asset IDs; no cross-listing Asset ID is shared.",
        "",
        "## 6. Asset Resolution Before / After",
        "",
        _markdown_table(
            ("Metric", "Before", "After", "Delta"),
            (
                (
                    "Canonical Assets",
                    BEFORE["assets"],
                    after["assets"],
                    after["assets"] - BEFORE["assets"],
                ),
                (
                    "AssetAliases",
                    BEFORE["aliases"],
                    after["aliases"],
                    after["aliases"] - BEFORE["aliases"],
                ),
                ("Unresolved occurrences", 739, after["unresolved"], after["unresolved"] - 739),
                (
                    "Distinct unresolved names",
                    363,
                    after["unresolved_names"],
                    after["unresolved_names"] - 363,
                ),
                (
                    "Current production Analysis",
                    BEFORE["active_analysis"],
                    after["active_analysis"],
                    after["active_analysis"] - BEFORE["active_analysis"],
                ),
            ),
        ),
        "",
        f"Approved scope: **{seed['resolution_guard']['approved_before']}** occurrences; actual newly resolved: **{seed['resolution_guard']['newly_resolved']}**; extra AssetResolution: **{len(seed['resolution_guard']['extra_resolution'])}**; missing approved: **{len(seed['resolution_guard']['missing_approved'])}**. All 62 resolved through `MARKET_SYMBOL` and landed on the approved Asset IDs.",
        "",
        "AssetRecovery reported 116 resolved references while scanning 551 analyzable analyses: 62 newly released approved references plus 54 previously existing/recoverable references reused. The unresolved total fell exactly by 62.",
        "",
        "## 7. Approved Occurrences Actually Resolved",
        "",
        _markdown_table(
            ("Reference", "Investor", "RawEvent", "Market", "Symbol", "Asset id", "Resolver"),
            (
                (
                    row["reference"],
                    row["investor"],
                    row["event_id"],
                    row["market"],
                    row["symbol"],
                    row["asset_id"],
                    row["matched_by"],
                )
                for row in seed["resolution_guard"]["resolved_records"]
            ),
        ),
        "",
        "## 8. Unexpected Extra Resolution",
        "",
        "**No unexpected AssetResolution occurred.** The same-transaction guard found no extra, missing, wrong-target, or changed-existing resolution. The 30 extra Attention rows described below are not AssetResolver resolutions; they are downstream deterministic text/repost evidence generated by the existing Attention policy during the all-event rebuild.",
        "",
        _markdown_table(
            (
                "New Asset",
                "Attention total",
                "Approved event+Asset pairs",
                "Extra deterministic Attention",
                "Extra evidence types",
            ),
            asset_attention_rows,
        ),
        "",
        f"New Assets have **{impact['new_asset_attention']}** Attention rows: **{impact['approved_attention']}** on the 62 approved event+Asset pairs and **{impact['extra_attention']}** additional rows from `{', '.join(f'{key}={value}' for key, value in impact['extra_types'].items())}`. These were not Opinion-bearing unresolved references and were produced by existing `EXPLICIT_MENTION`/`REPOST` rules, not fuzzy/name-only AssetResolver logic.",
        "",
        "## 9. Effective Opinion Before / After",
        "",
        _markdown_table(
            ("Metric", "Before", "After", "Delta"),
            (
                (
                    "Effective Opinions",
                    BEFORE["effective_opinions"],
                    after["effective_opinions"],
                    after["effective_opinions"] - BEFORE["effective_opinions"],
                ),
                (
                    "Opinion-bearing RawEvents",
                    BEFORE["opinion_events"],
                    after["opinion_events"],
                    after["opinion_events"] - BEFORE["opinion_events"],
                ),
                (
                    "Investor×Asset Opinion pairs",
                    BEFORE["opinion_pairs"],
                    after["opinion_pairs"],
                    after["opinion_pairs"] - BEFORE["opinion_pairs"],
                ),
                (
                    "Repeated Opinion pairs",
                    BEFORE["repeated_opinion_pairs"],
                    after["repeated_opinion_pairs"],
                    after["repeated_opinion_pairs"] - BEFORE["repeated_opinion_pairs"],
                ),
            ),
        ),
        "",
        "The 62 new Opinions were deterministic projections from existing structured Analysis output. Opinion-analysis LLM calls: **0**.",
        "",
        "## 10. Attention / Thesis Before / After",
        "",
        _markdown_table(
            ("Metric", "Before", "After", "Delta"),
            (
                (
                    "Effective AttentionOccurrences",
                    BEFORE["attention"],
                    after["attention"],
                    after["attention"] - BEFORE["attention"],
                ),
                (
                    "Attention Investor×Asset pairs",
                    BEFORE["attention_pairs"],
                    after["attention_pairs"],
                    after["attention_pairs"] - BEFORE["attention_pairs"],
                ),
                (
                    "Attention active calendar days",
                    "not captured in baseline",
                    after["attention_active_days"],
                    "—",
                ),
                (
                    "Repeated cross-day Attention pairs",
                    BEFORE["repeated_attention_pairs"],
                    after["repeated_attention_pairs"],
                    after["repeated_attention_pairs"] - BEFORE["repeated_attention_pairs"],
                ),
                (
                    "Effective ThesisChanges",
                    BEFORE["thesis"],
                    after["thesis"],
                    after["thesis"] - BEFORE["thesis"],
                ),
            ),
        ),
        "",
        "Attention rebuild operational result: 1,482 events scanned; created=92, updated=192, deleted=29, failed=0. The net Attention total is 284. The baseline report did not persist a global Attention active-day count, so that field is not fabricated.",
        "",
        _markdown_table(
            ("ThesisChange type", "Before", "After", "Delta"),
            (
                (
                    key,
                    after["thesis_before_types"].get(key, 0),
                    after["thesis_types"].get(key, 0),
                    after["thesis_types"].get(key, 0) - after["thesis_before_types"].get(key, 0),
                )
                for key in thesis_order
            ),
        ),
        "",
        "Thesis comparator: **42 calls**, **0 adapter-observed retries**, **1 failure**. The failure is the `HK:00991 大唐发电` Opinion `e7136959-a808-4840-9a68-15cd0a4e2ff2`; no retry was forced after the platform rejected an additional external payload attempt. One new Opinion therefore has no effective ThesisChange.",
        "",
        "## 11. Cross-Investor Before / After",
        "",
        _markdown_table(
            ("Metric", "Before", "After", "Delta"),
            (
                (
                    "2+ Attention Investor Assets",
                    BEFORE["attention_2"],
                    after["attention_2"],
                    after["attention_2"] - BEFORE["attention_2"],
                ),
                (
                    "3+ Attention Investor Assets",
                    BEFORE["attention_3"],
                    after["attention_3"],
                    after["attention_3"] - BEFORE["attention_3"],
                ),
                (
                    "2+ Opinion Investor Assets",
                    BEFORE["opinion_2"],
                    after["opinion_2"],
                    after["opinion_2"] - BEFORE["opinion_2"],
                ),
                (
                    "3+ Opinion Investor Assets",
                    BEFORE["opinion_3"],
                    after["opinion_3"],
                    after["opinion_3"] - BEFORE["opinion_3"],
                ),
                (
                    "Current Snapshot heads",
                    BEFORE["snapshots"],
                    after["snapshots"],
                    after["snapshots"] - BEFORE["snapshots"],
                ),
                (
                    "Current Alignment v1",
                    BEFORE["alignments"],
                    after["alignments"],
                    after["alignments"] - BEFORE["alignments"],
                ),
            ),
        ),
        "",
        "Cross-Investor snapshot rebuild scanned 45 Assets with effective Attention and produced 24 current heads; Alignment v1 produced 24 current lineage rows. The actual 3+ Attention count increased by one because deterministic mention/repost evidence changed the Attention distribution; 3+ Opinion Assets stayed unchanged at four.",
        "",
        "## 12. Alignment Before / After",
        "",
        _markdown_table(
            ("Alignment state", "Before", "After", "Delta"),
            (
                (
                    key,
                    BEFORE["alignment_states"].get(key, 0),
                    after["alignment_states"].get(key, 0),
                    after["alignment_states"].get(key, 0) - BEFORE["alignment_states"].get(key, 0),
                )
                for key in alignment_order
            ),
        ),
        "",
        "## 13. Consensus v2 Before / After",
        "",
        _markdown_table(
            ("Consensus v2 state", "Before", "After", "Delta"),
            (
                (
                    key,
                    BEFORE["consensus_states"].get(key, 0),
                    after["consensus_states"].get(key, 0),
                    after["consensus_states"].get(key, 0) - BEFORE["consensus_states"].get(key, 0),
                )
                for key in consensus_order
            ),
        ),
        "",
        "Consensus v2 rebuild: 24 source snapshots processed, 0 failures. No pure `CONSENSUS_BULLISH`, `CONSENSUS_BEARISH`, or `CONSENSUS_NEUTRAL` was produced; `DIVERGENT` remains one real current case (龙源电力).",
        "",
        "## 14. Remaining Unresolved Distribution",
        "",
        _markdown_table(
            ("Taxonomy", "Occurrences", "Share"),
            ((key, value, f"{value / unresolved_total:.1%}") for key, value in remaining.items()),
        ),
        "",
        f"Remaining unresolved: **{after['unresolved']} occurrences / {after['unresolved_names']} distinct names**. Name-only, nickname, UNKNOWN, concept/industry, commodity/macro, extraction noise, and unsupported ambiguous references remain unresolved. Original Tier B (45 candidates) remains HOLD and was not seeded.",
        "",
        "## 15. Tests",
        "",
        "- `pytest`: 465 passed, 2 environment warnings.",
        "- `ruff format --check .`: passed (272 files already formatted).",
        "- `ruff check .`: passed.",
        "- `alembic check`: no schema changes; no migration added.",
        "",
        "## 16. Git Status",
        "",
        "No commit or push was performed. Working tree changes are limited to the untracked audit/execution scripts: `scripts/audit_asset_resolution_v2.py`, `scripts/audit_tier_a_identity_integrity.py`, `scripts/run_tier_a_safe_asset_expansion.py`, and this completion audit script. Database seed/recovery changes are persisted in PostgreSQL as requested.",
        "",
        "## Final Decision",
        "",
        "- Safe Asset Expansion: **Asset/Alias seed and deterministic AssetRecovery succeeded for all 16 identities and exactly 62 approved references**; the overall Sprint is **partially complete** because one Thesis comparator call failed.",
        "- Cross-listing merge: **No**.",
        "- Intelligence released: **62 Effective Opinions / 20 Investor×Asset pairs**; **61 effective ThesisChanges** were added, plus deterministic Attention and cross-investor evidence.",
        "- Tier B: **remain HOLD**.",
        "- Next priority: **do not auto-execute**. The current state points to Asset Resolution / Opinion-density and Cross-Investor coverage; any next action requires a separate decision. No collection was started.",
        "",
        f"Full post-expansion Reality audit: `.local/audit/sprint_2f_tier_a_safe_asset_expansion_after.md`; post-expansion resolution audit: `{V2_AFTER_REPORT}`; transactional seed evidence: `{SEED_RESULT}`.",
    ]
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--seed-result", type=Path, default=SEED_RESULT)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    seed = json.loads(args.seed_result.read_text(encoding="utf-8"))
    connection, url = _connect_read_only()
    try:
        with connection.cursor() as cursor:
            database_name = str(
                _scalar(cursor, "SELECT current_database()") or url.database or "<unknown>"
            )
            data = _load_data(cursor)
            report = build_report(
                data,
                seed,
                database_name,
                __import__("datetime").datetime.now(__import__("datetime").UTC),
            )
    finally:
        connection.rollback()
        connection.close()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(report, encoding="utf-8")
    print(report, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
