"""Read-only PostgreSQL inventory for the Current Database Reality Study.

This script deliberately stops at observation.  It uses one PostgreSQL
repeatable-read, read-only transaction, never imports an LLM client, and does
not call any application pipeline or derived-artifact service.

The report distinguishes:

* the current production Opinion-analysis identity from historical identities;
* effective Opinion/Attention/Thesis rows from immutable or superseded rows;
* policy-compatible cross-investor rows from the latest persisted lineage head;
* observed collection facts from collection provenance (which may not exist in
  the current RawEvent schema).

The historical-depth thresholds in this file are audit-only classifications.
They are not persisted and are not part of the product domain model.
"""

# The report intentionally contains long human-readable diagnostic strings.
# Keep the project-wide line-length check from obscuring the actual audit code.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import psycopg
from sqlalchemy.engine import URL, make_url

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
    get_settings,
)
from contracts import (
    BEHAVIOR_SNAPSHOT_POLICY_VERSION,
    CONSISTENCY_POLICY_VERSION,
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
)

HK = timezone(timedelta(hours=8), name="Asia/Hong_Kong")
ELIGIBLE_ANALYSIS_STATUSES = {"SUCCESS", "PARTIALLY_RESOLVED"}
ALL_ANALYSIS_STATUSES = ("SUCCESS", "PARTIALLY_RESOLVED", "NO_OPINION", "FAILED")
PROVENANCE_KEYS = (
    "collection_type",
    "collection_mode",
    "collection_origin",
    "ingestion_mode",
    "ingestion_source",
    "collector_type",
    "capture_type",
    "feed_type",
    "source_type",
)
CORE_TABLES = (
    "investors",
    "assets",
    "asset_aliases",
    "raw_events",
    "event_analyses",
    "opinions",
    "attention_occurrences",
    "thesis_changes",
    "cross_investor_asset_snapshots",
    "cross_investor_asset_alignments",
    "cross_investor_consensus_evidences",
    "portfolio",
    "portfolio_snapshot_batches",
    "position_snapshots",
    "portfolio_actions",
    "investor_action_consistencies",
    "investor_action_claims",
    "investor_asset_states",
    "investor_asset_state_changes",
    "investor_behavior_snapshots",
    "signals",
)

Row = dict[str, Any]


def _enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def _id(value: Any) -> str:
    return str(value) if value is not None else ""


def _id_int(value: Any) -> int:
    try:
        return int(str(value).replace("-", ""), 16)
    except (TypeError, ValueError):
        return 0


def _as_hk(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=HK)
    return value.astimezone(HK)


def _date_hk(value: Any) -> date | None:
    normalized = _as_hk(value)
    return normalized.date() if normalized is not None else None


def _fmt_dt(value: Any) -> str:
    normalized = _as_hk(value)
    return normalized.isoformat(timespec="seconds") if normalized else "—"


def _fmt_number(value: float | int | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def _pct(numerator: int | float, denominator: int | float) -> str:
    if not denominator:
        return "—"
    return f"{numerator / denominator:.1%}"


def _span_days(earliest: datetime | None, latest: datetime | None) -> float:
    if earliest is None or latest is None:
        return 0.0
    return max(0.0, (latest - earliest).total_seconds() / 86400)


def _as_map(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _as_list(value: Any) -> list[Any]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _md(value: Any) -> str:
    if value is None or value == "":
        return "—"
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _markdown_table(headers: Iterable[str], rows: Iterable[Iterable[Any]]) -> str:
    header_values = [_md(value) for value in headers]
    body = [[_md(value) for value in row] for row in rows]
    lines = [
        "| " + " | ".join(header_values) + " |",
        "| " + " | ".join("---" for _ in header_values) + " |",
    ]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def _top_labels(counter: Counter[str], labels: dict[str, str], limit: int = 5) -> str:
    if not counter:
        return "none"
    return ", ".join(
        f"{labels.get(key, key)} ({count})" for key, count in counter.most_common(limit)
    )


def _latest_key(row: Row, time_field: str) -> tuple[datetime, int]:
    value = _as_hk(row.get(time_field))
    if value is None:
        value = datetime.min.replace(tzinfo=HK)
    return value, _id_int(row.get("id"))


def _connect_read_only() -> tuple[psycopg.Connection[Any], URL]:
    settings = get_settings()
    url = make_url(settings.database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            "Current Database Reality Study requires PostgreSQL; "
            f"configured backend is {url.get_backend_name()}"
        )
    connection = psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
    )
    with connection.cursor() as cursor:
        # This is the first statement in the transaction.  It makes an
        # accidental INSERT/UPDATE/DDL fail at the database boundary.
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute("SET LOCAL TIME ZONE 'Asia/Hong_Kong'")
        cursor.execute("SET LOCAL statement_timeout = '60000'")
    return connection, url


def _fetch(cursor: psycopg.Cursor[Any], statement: str, params: tuple[Any, ...] = ()) -> list[Row]:
    cursor.execute(statement, params)
    columns = [column.name for column in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def _scalar(cursor: psycopg.Cursor[Any], statement: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(statement, params)
    row = cursor.fetchone()
    return row[0] if row else None


def _load_data(cursor: psycopg.Cursor[Any]) -> dict[str, Any]:
    existing_tables = {
        row["table_name"]
        for row in _fetch(
            cursor,
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
            ORDER BY table_name
            """,
        )
    }

    def table_rows(table: str, statement: str) -> list[Row]:
        return _fetch(cursor, statement) if table in existing_tables else []

    table_counts: dict[str, int | None] = {}
    for table in CORE_TABLES:
        table_counts[table] = (
            int(_scalar(cursor, f"SELECT count(*) FROM {table}"))
            if table in existing_tables
            else None
        )

    investors = table_rows(
        "investors",
        """
        SELECT id, name, platform, platform_user_id, quality_score,
               investment_style
        FROM investors
        ORDER BY name, id
        """,
    )
    assets = table_rows(
        "assets",
        """
        SELECT id, name, symbol, market, industry, themes
        FROM assets
        ORDER BY name, market, symbol, id
        """,
    )
    raw_events = table_rows(
        "raw_events",
        """
        SELECT id, investor_id, event_type, source, published_time,
               collected_time, raw_data
        FROM raw_events
        ORDER BY published_time, id
        """,
    )
    analyses = table_rows(
        "event_analyses",
        """
        SELECT id, event_id, analysis_version, model_version, prompt_version,
               schema_version, status, investment_related, generated_time,
               calculated_at, confidence, structured_output, provider_metadata
        FROM event_analyses
        ORDER BY event_id, calculated_at, id
        """,
    )
    opinions = table_rows(
        "opinions",
        """
        SELECT o.id, o.event_id, o.analysis_id, o.investor_id, o.asset_id,
               o.direction, o.strength, o.confidence, o.generated_time,
               o.model_version, r.published_time
        FROM opinions o
        JOIN raw_events r ON r.id = o.event_id
        ORDER BY o.investor_id, o.asset_id, r.published_time, r.id, o.id
        """,
    )
    attention = table_rows(
        "attention_occurrences",
        """
        SELECT id, investor_id, asset_id, event_id, published_time,
               evidence_types, analysis_id, opinion_id,
               attention_policy_version, calculated_at
        FROM attention_occurrences
        ORDER BY investor_id, asset_id, published_time, id
        """,
    )
    thesis = table_rows(
        "thesis_changes",
        """
        SELECT id, investor_id, asset_id, previous_opinion_id,
               current_opinion_id, previous_event_id, current_event_id,
               effective_time, change_type, confidence,
               opinion_analysis_version, comparison_version, calculated_at
        FROM thesis_changes
        ORDER BY effective_time, id
        """,
    )
    snapshots = table_rows(
        "cross_investor_asset_snapshots",
        """
        SELECT id, asset_id, as_of, window_start, window_end,
               attention_occurrence_count, attention_investor_count,
               opinion_count, opinion_investor_count, contributions,
               opinion_analysis_version, attention_policy_version,
               thesis_comparison_version, consistency_policy_version,
               cross_investor_policy_version, calculated_at
        FROM cross_investor_asset_snapshots
        ORDER BY asset_id, calculated_at, id
        """,
    )
    alignments = table_rows(
        "cross_investor_asset_alignments",
        """
        SELECT id, asset_id, source_snapshot_id, opinion_coverage_state,
               directional_alignment_state, alignment_policy_version,
               input_identity, calculated_at, created_at
        FROM cross_investor_asset_alignments
        ORDER BY asset_id, created_at, id
        """,
    )
    consensus = table_rows(
        "cross_investor_consensus_evidences",
        """
        SELECT id, asset_id, source_snapshot_id, source_alignment_id,
               attention_investor_count, opinion_investor_count,
               bullish_investor_count, bearish_investor_count,
               neutral_investor_count, opinion_coverage_state,
               consensus_state, contributing_investor_ids, latest_opinions,
               consensus_policy_version, calculated_at, created_at
        FROM cross_investor_consensus_evidences
        ORDER BY asset_id, created_at, id
        """,
    )
    portfolios = table_rows(
        "portfolio",
        """
        SELECT id, investor_id, source, external_id, name, status
        FROM portfolio
        ORDER BY investor_id, id
        """,
    )
    batches = table_rows(
        "portfolio_snapshot_batches",
        """
        SELECT id, portfolio_id, snapshot_time, source, external_id,
               completeness
        FROM portfolio_snapshot_batches
        ORDER BY portfolio_id, snapshot_time, source, external_id, id
        """,
    )
    positions = table_rows(
        "position_snapshots",
        """
        SELECT id, portfolio_id, snapshot_batch_id, asset_id,
               asset_reference_id, weight, snapshot_time, source_type
        FROM position_snapshots
        ORDER BY portfolio_id, snapshot_time, id
        """,
    )
    actions = table_rows(
        "portfolio_actions",
        """
        SELECT id, portfolio_id, asset_id, asset_reference_id,
               previous_snapshot_batch_id, current_snapshot_batch_id,
               previous_position_snapshot_id, current_position_snapshot_id,
               previous_snapshot_id, current_snapshot_id, action_type,
               effective_time, calculated_at, created_at
        FROM portfolio_actions
        ORDER BY portfolio_id, effective_time, id
        """,
    )
    consistencies = table_rows(
        "investor_action_consistencies",
        """
        SELECT id, investor_id, asset_id, opinion_id, portfolio_action_id,
               action_type, consistency_type, effective_time,
               opinion_analysis_version, consistency_policy_version
        FROM investor_action_consistencies
        ORDER BY investor_id, effective_time, id
        """,
    )
    claims = table_rows(
        "investor_action_claims",
        """
        SELECT id, investor_id, asset_id, asset_reference_id, event_id,
               claim_type, published_time, analysis_version
        FROM investor_action_claims
        ORDER BY investor_id, published_time, id
        """,
    )
    states = table_rows(
        "investor_asset_states",
        """
        SELECT id, investor_id, asset_id, attention_level, direction,
               mention_count, last_activity_time, last_material_change_time
        FROM investor_asset_states
        ORDER BY investor_id, asset_id, id
        """,
    )
    state_changes = table_rows(
        "investor_asset_state_changes",
        """
        SELECT id, investor_id, asset_id, transition_type, effective_time,
               state_policy_version
        FROM investor_asset_state_changes
        ORDER BY investor_id, asset_id, effective_time, id
        """,
    )
    behavior_snapshots = table_rows(
        "investor_behavior_snapshots",
        """
        SELECT id, investor_id, as_of, window_start, window_end,
               attention_asset_count, attention_occurrence_count,
               opinion_count, thesis_change_count, portfolio_action_count,
               active_analysis_version, thesis_comparison_version,
               consistency_policy_version, attention_policy_version,
               behavior_policy_version, calculated_at
        FROM investor_behavior_snapshots
        ORDER BY investor_id, calculated_at, id
        """,
    )
    signals = table_rows(
        "signals",
        """
        SELECT id, asset_id, signal_score, signal_level, created_at
        FROM signals
        ORDER BY created_at, id
        """,
    )
    return {
        "existing_tables": existing_tables,
        "table_counts": table_counts,
        "investors": investors,
        "assets": assets,
        "raw_events": raw_events,
        "analyses": analyses,
        "opinions": opinions,
        "attention": attention,
        "thesis": thesis,
        "snapshots": snapshots,
        "alignments": alignments,
        "consensus": consensus,
        "portfolios": portfolios,
        "batches": batches,
        "positions": positions,
        "actions": actions,
        "consistencies": consistencies,
        "claims": claims,
        "states": states,
        "state_changes": state_changes,
        "behavior_snapshots": behavior_snapshots,
        "signals": signals,
    }


def _classify_history(raw_count: int, span_days: float, active_days: int) -> str:
    """Audit-only history classification; never persisted as business state."""

    if raw_count >= 50 and span_days >= 25 and active_days >= 10:
        return "DEEP_HISTORY"
    if raw_count >= 10 and (span_days >= 7 or active_days >= 5):
        return "MEDIUM_HISTORY"
    if raw_count >= 2 and (span_days >= 1 or active_days >= 2):
        return "SHALLOW_HISTORY"
    return "MINIMAL_DATA"


def _consensus_v2_state(
    opinion_investor_count: int,
    bullish: int,
    bearish: int,
    neutral: int,
) -> str:
    if opinion_investor_count < 3:
        return "INSUFFICIENT_EVIDENCE"
    if bullish and bearish:
        return "DIVERGENT"
    if (bullish and neutral) or (bearish and neutral):
        return "MIXED_WITH_NEUTRAL"
    if bullish:
        return "CONSENSUS_BULLISH"
    if bearish:
        return "CONSENSUS_BEARISH"
    return "CONSENSUS_NEUTRAL"


def _effective_thesis(
    all_thesis: list[Row],
    effective_opinions: list[Row],
    analysis_version: str,
    comparison_version: str,
) -> list[Row]:
    ordered_opinions = sorted(
        effective_opinions,
        key=lambda row: (
            _id(row.get("investor_id")),
            _id(row.get("asset_id")),
            _as_hk(row.get("published_time")) or datetime.min.replace(tzinfo=HK),
            _id_int(row.get("event_id")),
            _id_int(row.get("id")),
        ),
    )
    expected_previous: dict[str, tuple[str | None, str | None]] = {}
    previous_by_pair: dict[tuple[str, str], tuple[str, str]] = {}
    opinion_by_id: dict[str, Row] = {}
    for opinion in ordered_opinions:
        opinion_id = _id(opinion.get("id"))
        opinion_by_id[opinion_id] = opinion
        pair = (_id(opinion.get("investor_id")), _id(opinion.get("asset_id")))
        expected_previous[opinion_id] = previous_by_pair.get(pair, (None, None))
        previous_by_pair[pair] = (opinion_id, _id(opinion.get("event_id")))

    effective: list[Row] = []
    for item in all_thesis:
        if item.get("opinion_analysis_version") != analysis_version:
            continue
        if item.get("comparison_version") != comparison_version:
            continue
        current_opinion_id = _id(item.get("current_opinion_id"))
        current = opinion_by_id.get(current_opinion_id)
        if current is None:
            continue
        if item.get("current_event_id") is not None and _id(item.get("current_event_id")) != _id(
            current.get("event_id")
        ):
            continue
        if _id(item.get("investor_id")) != _id(current.get("investor_id")):
            continue
        if _id(item.get("asset_id")) != _id(current.get("asset_id")):
            continue
        expected = expected_previous.get(current_opinion_id)
        if expected is None:
            continue
        actual = (
            _id(item.get("previous_opinion_id")) if item.get("previous_opinion_id") else None,
            _id(item.get("previous_event_id")) if item.get("previous_event_id") else None,
        )
        if actual != expected:
            continue
        effective.append(item)
    return effective


def _effective_portfolio_actions(batches: list[Row], actions: list[Row]) -> list[Row]:
    by_portfolio: dict[str, list[Row]] = defaultdict(list)
    for batch in batches:
        by_portfolio[_id(batch.get("portfolio_id"))].append(batch)
    adjacent: set[tuple[str, str]] = set()
    for timeline in by_portfolio.values():
        timeline.sort(
            key=lambda row: (
                _as_hk(row.get("snapshot_time")) or datetime.min.replace(tzinfo=HK),
                str(row.get("source") or ""),
                str(row.get("external_id") or ""),
                _id_int(row.get("id")),
            )
        )
        adjacent.update(
            (_id(previous.get("id")), _id(current.get("id")))
            for previous, current in zip(timeline, timeline[1:], strict=False)
        )
    return [
        action
        for action in actions
        if (
            _id(action.get("previous_snapshot_batch_id")),
            _id(action.get("current_snapshot_batch_id")),
        )
        in adjacent
    ]


def _effective_consistencies(
    consistencies: list[Row],
    effective_actions: list[Row],
    portfolios: list[Row],
    effective_opinions: list[Row],
    analysis_version: str,
) -> list[Row]:
    portfolio_investor = {_id(row.get("id")): _id(row.get("investor_id")) for row in portfolios}
    action_by_id = {_id(row.get("id")): row for row in effective_actions}
    opinions_by_pair: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for opinion in effective_opinions:
        opinions_by_pair[(_id(opinion.get("investor_id")), _id(opinion.get("asset_id")))].append(
            opinion
        )
    for timeline in opinions_by_pair.values():
        timeline.sort(
            key=lambda row: (
                _as_hk(row.get("published_time")) or datetime.min.replace(tzinfo=HK),
                _id_int(row.get("event_id")),
                _id_int(row.get("id")),
            )
        )

    result: list[Row] = []
    for item in consistencies:
        if item.get("opinion_analysis_version") != analysis_version:
            continue
        if item.get("consistency_policy_version") != CONSISTENCY_POLICY_VERSION:
            continue
        action = action_by_id.get(_id(item.get("portfolio_action_id")))
        if action is None or item.get("asset_id") is None:
            continue
        investor_id = portfolio_investor.get(_id(action.get("portfolio_id")))
        if investor_id is None or investor_id != _id(item.get("investor_id")):
            continue
        action_time = _as_hk(action.get("effective_time"))
        candidates = [
            opinion
            for opinion in opinions_by_pair.get((investor_id, _id(item.get("asset_id"))), [])
            if action_time is None
            or (_as_hk(opinion.get("published_time")) or datetime.max.replace(tzinfo=HK))
            <= action_time
        ]
        if candidates and _id(item.get("opinion_id")) == _id(candidates[-1].get("id")):
            result.append(item)
    return result


def _provenance_report(raw_events: list[Row]) -> tuple[Counter[str], dict[str, Counter[str]], bool]:
    source_counts: Counter[str] = Counter()
    marker_values: dict[str, Counter[str]] = {key: Counter() for key in PROVENANCE_KEYS}
    for event in raw_events:
        source_counts[str(event.get("source") or "<NULL>")] += 1
        raw_data = _as_map(event.get("raw_data"))
        for key in PROVENANCE_KEYS:
            value = raw_data.get(key)
            if value is None:
                continue
            if isinstance(value, (dict, list, tuple)):
                normalized = str(value)
            else:
                normalized = str(value).strip()
            if normalized:
                marker_values[key][normalized] += 1

    # A marker is considered reliable only if it is populated and carries an
    # explicit collection category, rather than merely repeating `source`.
    recognized = {
        "following",
        "following_feed",
        "feed",
        "profile",
        "profile_history",
        "history",
        "manual",
        "other",
    }
    reliable = False
    for values in marker_values.values():
        normalized_values = {value.lower().replace("-", "_") for value in values}
        if normalized_values and normalized_values <= recognized and len(normalized_values) >= 2:
            reliable = True
    return source_counts, marker_values, reliable


def _build_report(data: dict[str, Any], database_name: str, audit_time: datetime) -> str:
    investors = data["investors"]
    assets = data["assets"]
    raw_events = data["raw_events"]
    all_analyses = data["analyses"]
    all_opinions = data["opinions"]
    all_attention = data["attention"]
    all_thesis = data["thesis"]
    all_snapshots = data["snapshots"]
    all_alignments = data["alignments"]
    all_consensus = data["consensus"]
    portfolios = data["portfolios"]
    batches = data["batches"]
    positions = data["positions"]
    actions = data["actions"]
    consistencies = data["consistencies"]
    behavior_snapshots = data["behavior_snapshots"]
    signals = data["signals"]
    table_counts = data["table_counts"]

    opinion_policy = get_production_analysis_policy()
    thesis_policy = get_production_thesis_comparison_policy()
    active_spec = opinion_policy.active_spec
    analysis_version = opinion_policy.active_analysis_version
    thesis_version = thesis_policy.active_analysis_version
    attention_version = get_production_attention_policy_version()

    raw_by_id = {_id(row.get("id")): row for row in raw_events}
    investor_by_id = {_id(row.get("id")): row for row in investors}
    investor_names = {key: str(row.get("name") or key) for key, row in investor_by_id.items()}
    asset_by_id = {_id(row.get("id")): row for row in assets}
    asset_names = {key: str(row.get("name") or key) for key, row in asset_by_id.items()}

    active_analysis_rows = [
        row for row in all_analyses if row.get("analysis_version") == analysis_version
    ]
    active_analysis_by_event_candidates: dict[str, list[Row]] = defaultdict(list)
    for row in active_analysis_rows:
        active_analysis_by_event_candidates[_id(row.get("event_id"))].append(row)
    current_analysis_by_event: dict[str, Row] = {}
    for event_id, candidates in active_analysis_by_event_candidates.items():
        current_analysis_by_event[event_id] = max(
            candidates, key=lambda row: _latest_key(row, "calculated_at")
        )
    current_analysis_rows = list(current_analysis_by_event.values())
    effective_analysis_ids = {
        _id(row.get("id"))
        for row in active_analysis_rows
        if _enum_text(row.get("status")) in ELIGIBLE_ANALYSIS_STATUSES
    }
    effective_opinions = [
        row for row in all_opinions if _id(row.get("analysis_id")) in effective_analysis_ids
    ]
    effective_attention = [
        row
        for row in all_attention
        if row.get("attention_policy_version") == attention_version
        and (
            row.get("analysis_id") is None or _id(row.get("analysis_id")) in effective_analysis_ids
        )
    ]
    effective_thesis = _effective_thesis(
        all_thesis,
        effective_opinions,
        analysis_version,
        thesis_version,
    )

    effective_actions = _effective_portfolio_actions(batches, actions)
    effective_consistencies = _effective_consistencies(
        consistencies,
        effective_actions,
        portfolios,
        effective_opinions,
        analysis_version,
    )

    # Cross-investor policy-compatible rows use every upstream production
    # identity.  The latest persisted head is then narrowed by exact current
    # Attention occurrence IDs, matching the repository's late-fact rule.
    def current_snapshot_policy(row: Row) -> bool:
        return (
            row.get("opinion_analysis_version") == analysis_version
            and row.get("attention_policy_version") == attention_version
            and row.get("thesis_comparison_version") == thesis_version
            and row.get("consistency_policy_version") == CONSISTENCY_POLICY_VERSION
            and row.get("cross_investor_policy_version") == CROSS_INVESTOR_POLICY_VERSION
        )

    current_policy_snapshots = [row for row in all_snapshots if current_snapshot_policy(row)]
    snapshot_by_id = {_id(row.get("id")): row for row in all_snapshots}

    def snapshot_attention_ids(row: Row) -> set[str]:
        result: set[str] = set()
        for contribution in _as_list(row.get("contributions")):
            contribution_map = _as_map(contribution)
            result.update(
                _id(value) for value in _as_list(contribution_map.get("attention_occurrence_ids"))
            )
        return result

    current_attention_ids_by_asset: dict[str, set[str]] = defaultdict(set)
    current_attention_investors_by_asset: dict[str, set[str]] = defaultdict(set)
    for row in effective_attention:
        asset_id = _id(row.get("asset_id"))
        current_attention_ids_by_asset[asset_id].add(_id(row.get("id")))
        current_attention_investors_by_asset[asset_id].add(_id(row.get("investor_id")))
    latest_snapshot_by_asset: dict[str, Row] = {}
    for row in sorted(
        current_policy_snapshots, key=lambda item: _latest_key(item, "calculated_at")
    ):
        latest_snapshot_by_asset[_id(row.get("asset_id"))] = row
    current_snapshot_heads = {
        asset_id: row
        for asset_id, row in latest_snapshot_by_asset.items()
        if len(current_attention_investors_by_asset.get(asset_id, set())) >= 2
        and snapshot_attention_ids(row) == current_attention_ids_by_asset.get(asset_id, set())
    }
    current_snapshot_head_ids = {_id(row.get("id")) for row in current_snapshot_heads.values()}

    current_policy_alignments = [
        row
        for row in all_alignments
        if row.get("alignment_policy_version") == CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION
    ]
    effective_alignments = [
        row
        for row in current_policy_alignments
        if _id(row.get("source_snapshot_id")) in current_snapshot_head_ids
        and _id(snapshot_by_id.get(_id(row.get("source_snapshot_id")), {}).get("asset_id"))
        == _id(row.get("asset_id"))
    ]
    effective_alignment_ids = {_id(row.get("id")) for row in effective_alignments}
    current_policy_consensus = [
        row
        for row in all_consensus
        if row.get("consensus_policy_version") == CROSS_INVESTOR_CONSENSUS_POLICY_VERSION
    ]
    effective_consensus = [
        row
        for row in current_policy_consensus
        if _id(row.get("source_snapshot_id")) in current_snapshot_head_ids
        and _id(row.get("source_alignment_id")) in effective_alignment_ids
        and _id(snapshot_by_id.get(_id(row.get("source_snapshot_id")), {}).get("asset_id"))
        == _id(row.get("asset_id"))
    ]

    # Investor- and asset-level effective evidence indexes.
    raw_by_investor: dict[str, list[Row]] = defaultdict(list)
    for row in raw_events:
        raw_by_investor[_id(row.get("investor_id"))].append(row)
    current_analysis_by_investor: dict[str, list[Row]] = defaultdict(list)
    for event_id, row in current_analysis_by_event.items():
        raw = raw_by_id.get(event_id)
        if raw is not None:
            current_analysis_by_investor[_id(raw.get("investor_id"))].append(row)
    opinion_by_investor: dict[str, list[Row]] = defaultdict(list)
    opinion_by_asset: dict[str, list[Row]] = defaultdict(list)
    opinions_by_pair: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in effective_opinions:
        investor_id = _id(row.get("investor_id"))
        asset_id = _id(row.get("asset_id"))
        opinion_by_investor[investor_id].append(row)
        opinion_by_asset[asset_id].append(row)
        opinions_by_pair[(investor_id, asset_id)].append(row)
    attention_by_investor: dict[str, list[Row]] = defaultdict(list)
    attention_by_asset: dict[str, list[Row]] = defaultdict(list)
    attention_by_pair: dict[tuple[str, str], list[Row]] = defaultdict(list)
    for row in effective_attention:
        investor_id = _id(row.get("investor_id"))
        asset_id = _id(row.get("asset_id"))
        attention_by_investor[investor_id].append(row)
        attention_by_asset[asset_id].append(row)
        attention_by_pair[(investor_id, asset_id)].append(row)
    thesis_by_investor: dict[str, list[Row]] = defaultdict(list)
    thesis_by_asset: dict[str, list[Row]] = defaultdict(list)
    for row in effective_thesis:
        thesis_by_investor[_id(row.get("investor_id"))].append(row)
        thesis_by_asset[_id(row.get("asset_id"))].append(row)

    latest_opinion_by_pair: dict[tuple[str, str], Row] = {}
    for pair, rows in opinions_by_pair.items():
        latest_opinion_by_pair[pair] = max(
            rows,
            key=lambda row: (
                _as_hk(row.get("published_time")) or datetime.min.replace(tzinfo=HK),
                _id_int(row.get("event_id")),
                _id_int(row.get("id")),
            ),
        )

    attention_investors_by_asset = {
        asset_id: {_id(row.get("investor_id")) for row in rows}
        for asset_id, rows in attention_by_asset.items()
    }
    opinion_investors_by_asset = {
        asset_id: {_id(row.get("investor_id")) for row in rows}
        for asset_id, rows in opinion_by_asset.items()
    }

    unresolved_by_investor: Counter[str] = Counter()
    unresolved_names_by_investor: dict[str, set[str]] = defaultdict(set)
    unresolved_total = 0
    for event_id, analysis in current_analysis_by_event.items():
        raw = raw_by_id.get(event_id)
        if raw is None:
            continue
        investor_id = _id(raw.get("investor_id"))
        for item in _as_list(_as_map(analysis.get("structured_output")).get("unresolved_assets")):
            item_map = _as_map(item)
            name = str(item_map.get("asset_name") or "<missing>").strip()
            unresolved_by_investor[investor_id] += 1
            unresolved_names_by_investor[investor_id].add(name)
            unresolved_total += 1

    metrics: dict[str, dict[str, Any]] = {}
    for investor in investors:
        investor_id = _id(investor.get("id"))
        investor_raw = raw_by_investor.get(investor_id, [])
        times = [_as_hk(row.get("published_time")) for row in investor_raw]
        times = [value for value in times if value is not None]
        earliest = min(times) if times else None
        latest = max(times) if times else None
        active_days = len({_date_hk(value) for value in times if _date_hk(value) is not None})
        current_analysis = current_analysis_by_investor.get(investor_id, [])
        status_counts = Counter(_enum_text(row.get("status")) for row in current_analysis)
        investor_opinions = opinion_by_investor.get(investor_id, [])
        investor_attention = attention_by_investor.get(investor_id, [])
        investor_thesis = thesis_by_investor.get(investor_id, [])
        unprocessed = [
            row for row in investor_raw if _id(row.get("id")) not in current_analysis_by_event
        ]
        unprocessed_times = [_as_hk(row.get("published_time")) for row in unprocessed]
        unprocessed_times = [value for value in unprocessed_times if value is not None]
        repeated_opinion_pairs = sum(
            len(rows) >= 2
            for (pair_investor, _), rows in opinions_by_pair.items()
            if pair_investor == investor_id
        )
        repeated_attention_cross_day_pairs = 0
        for (pair_investor, _), rows in attention_by_pair.items():
            if pair_investor != investor_id:
                continue
            if len(rows) >= 2 and len({_date_hk(row.get("published_time")) for row in rows}) >= 2:
                repeated_attention_cross_day_pairs += 1
        attention_assets = {_id(row.get("asset_id")) for row in investor_attention}
        opinion_assets = {_id(row.get("asset_id")) for row in investor_opinions}
        resolved_assets = opinion_assets
        intelligence_event_ids = {_id(row.get("event_id")) for row in investor_opinions}
        intelligence_event_ids.update(_id(row.get("event_id")) for row in investor_attention)
        intelligence_event_ids.update(_id(row.get("current_event_id")) for row in investor_thesis)
        shared_assets = sum(
            len(attention_investors_by_asset.get(asset_id, set())) >= 2
            for asset_id in attention_assets
        )
        overlap_3plus = sum(
            len(attention_investors_by_asset.get(asset_id, set())) >= 3
            for asset_id in attention_assets
        )
        raw_count = len(investor_raw)
        active_analysis_count = len(current_analysis)
        depth = _classify_history(raw_count, _span_days(earliest, latest), active_days)
        metrics[investor_id] = {
            "id": investor_id,
            "name": str(investor.get("name") or investor_id),
            "platform": str(investor.get("platform") or "—"),
            "platform_user_id": str(investor.get("platform_user_id") or "—"),
            "raw_count": raw_count,
            "earliest": earliest,
            "latest": latest,
            "span_days": _span_days(earliest, latest),
            "active_days": active_days,
            "analysis_count": active_analysis_count,
            "missing_analysis": len(unprocessed),
            "status_counts": status_counts,
            "opinions": len(investor_opinions),
            "opinion_assets": len(opinion_assets),
            "attention": len(investor_attention),
            "attention_assets": len(attention_assets),
            "thesis": len(investor_thesis),
            "repeated_opinion_pairs": repeated_opinion_pairs,
            "repeated_attention_cross_day_pairs": repeated_attention_cross_day_pairs,
            "resolved_refs": len(investor_opinions),
            "resolved_assets": len(resolved_assets),
            "unresolved_refs": unresolved_by_investor[investor_id],
            "unresolved_names": len(unresolved_names_by_investor[investor_id]),
            "unprocessed_earliest": min(unprocessed_times) if unprocessed_times else None,
            "unprocessed_latest": max(unprocessed_times) if unprocessed_times else None,
            "analysis_coverage": active_analysis_count / raw_count if raw_count else 0.0,
            "opinion_density": len(investor_opinions) / raw_count if raw_count else 0.0,
            "intelligence_event_coverage": len(intelligence_event_ids) / raw_count
            if raw_count
            else 0.0,
            "shared_assets": shared_assets,
            "overlap_3plus": overlap_3plus,
            "depth": depth,
        }

    # Global pipeline units.
    raw_ids = set(raw_by_id)
    active_analysis_event_ids = set(current_analysis_by_event)
    effective_analysis_event_ids = {
        _id(row.get("event_id"))
        for row in current_analysis_rows
        if _enum_text(row.get("status")) in ELIGIBLE_ANALYSIS_STATUSES
    }
    effective_opinion_event_ids = {_id(row.get("event_id")) for row in effective_opinions}
    effective_attention_event_ids = {_id(row.get("event_id")) for row in effective_attention}
    effective_thesis_event_ids = {_id(row.get("current_event_id")) for row in effective_thesis}
    raw_only_event_ids = raw_ids - active_analysis_event_ids
    analyzed_without_opinion_event_ids = active_analysis_event_ids - effective_opinion_event_ids
    cross_attention_asset_ids = {
        asset_id
        for asset_id, investor_set in attention_investors_by_asset.items()
        if len(investor_set) >= 2
    }
    cross_opinion_asset_ids = {
        asset_id
        for asset_id, investor_set in opinion_investors_by_asset.items()
        if len(investor_set) >= 2
    }
    cross_opinion_3plus_asset_ids = {
        asset_id
        for asset_id, investor_set in opinion_investors_by_asset.items()
        if len(investor_set) >= 3
    }

    # Opinion density and high-volume/low-intelligence classifications.
    high_volume_low_density = [
        metric
        for metric in metrics.values()
        if metric["raw_count"] >= 30
        and (metric["opinion_density"] < 0.10 or metric["intelligence_event_coverage"] < 0.20)
    ]
    high_volume_low_density.sort(key=lambda item: (-item["raw_count"], item["name"]))

    # Current per-asset shared evidence and active v2 semantic classification.
    shared_assets: list[dict[str, Any]] = []
    for asset_id, attention_rows in attention_by_asset.items():
        attention_investors = attention_investors_by_asset.get(asset_id, set())
        if len(attention_investors) < 2:
            continue
        latest_directions: list[str] = []
        bullish = bearish = neutral = 0
        for investor_id in sorted(
            attention_investors, key=lambda key: investor_names.get(key, key)
        ):
            latest = latest_opinion_by_pair.get((investor_id, asset_id))
            if latest is None:
                latest_directions.append(f"{investor_names.get(investor_id, investor_id)}:—")
                continue
            direction = _enum_text(latest.get("direction"))
            latest_directions.append(f"{investor_names.get(investor_id, investor_id)}:{direction}")
            if direction in {"BULLISH", "STRONG_BULLISH"}:
                bullish += 1
            elif direction in {"BEARISH", "STRONG_BEARISH"}:
                bearish += 1
            elif direction == "NEUTRAL":
                neutral += 1
        opinion_investor_count = len(opinion_investors_by_asset.get(asset_id, set()))
        shared_assets.append(
            {
                "asset_id": asset_id,
                "name": asset_names.get(asset_id, asset_id),
                "attention_investor_count": len(attention_investors),
                "opinion_investor_count": opinion_investor_count,
                "attention_count": len(attention_rows),
                "opinion_count": len(opinion_by_asset.get(asset_id, [])),
                "latest_directions": "; ".join(latest_directions),
                "consensus_v2": _consensus_v2_state(
                    opinion_investor_count, bullish, bearish, neutral
                ),
                "snapshot_head": asset_id in current_snapshot_heads,
            }
        )
    shared_assets.sort(
        key=lambda item: (
            -item["attention_investor_count"],
            -item["opinion_investor_count"],
            -item["attention_count"],
            item["name"],
        )
    )

    # Persisted policy distributions.
    analysis_version_counts = Counter(
        str(row.get("analysis_version") or "<NULL>") for row in all_analyses
    )
    analysis_model_counts = Counter(
        str(row.get("model_version") or "<NULL>") for row in active_analysis_rows
    )
    opinion_model_counts = Counter(
        str(row.get("model_version") or "<NULL>") for row in effective_opinions
    )
    attention_policy_counts = Counter(
        str(row.get("attention_policy_version") or "<NULL>") for row in all_attention
    )
    thesis_policy_counts = Counter(
        f"{row.get('opinion_analysis_version')} + {row.get('comparison_version')}"
        for row in all_thesis
    )
    alignment_policy_counts = Counter(
        str(row.get("alignment_policy_version") or "<NULL>") for row in all_alignments
    )
    consensus_policy_counts = Counter(
        str(row.get("consensus_policy_version") or "<NULL>") for row in all_consensus
    )

    source_counts, marker_values, provenance_reliable = _provenance_report(raw_events)
    raw_earliest = min(
        (
            _as_hk(row.get("published_time"))
            for row in raw_events
            if _as_hk(row.get("published_time"))
        ),
        default=None,
    )
    raw_latest = max(
        (
            _as_hk(row.get("published_time"))
            for row in raw_events
            if _as_hk(row.get("published_time"))
        ),
        default=None,
    )
    source_text = (
        ", ".join(f"{key}={value}" for key, value in source_counts.most_common()) or "none"
    )

    # Global inventory table.  `historical/immutable` is intentionally marked
    # by semantic rule rather than implying that a master table is append-only.
    def count_text(value: int | None) -> str:
        return "table absent" if value is None else str(value)

    inventory_rows = [
        (
            "Investor",
            "investors",
            table_counts["investors"],
            table_counts["investors"],
            0,
            "current master rows",
        ),
        (
            "Asset",
            "assets",
            table_counts["assets"],
            table_counts["assets"],
            0,
            "canonical master rows",
        ),
        (
            "AssetAlias",
            "asset_aliases",
            table_counts["asset_aliases"],
            table_counts["asset_aliases"],
            0,
            "current alias master rows",
        ),
        (
            "RawEvent",
            "raw_events",
            table_counts["raw_events"],
            "n/a",
            table_counts["raw_events"],
            "immutable raw facts",
        ),
        (
            "EventAnalysis",
            "event_analyses",
            table_counts["event_analyses"],
            len(active_analysis_rows),
            (table_counts["event_analyses"] or 0) - len(active_analysis_rows),
            "current production identity by event; effective statuses are SUCCESS/PARTIALLY_RESOLVED",
        ),
        (
            "Opinion",
            "opinions",
            table_counts["opinions"],
            len(effective_opinions),
            (table_counts["opinions"] or 0) - len(effective_opinions),
            "effective rows join active production analysis and eligible status",
        ),
        (
            "AttentionOccurrence",
            "attention_occurrences",
            table_counts["attention_occurrences"],
            len(effective_attention),
            (table_counts["attention_occurrences"] or 0) - len(effective_attention),
            "active attention policy plus eligible linked analysis",
        ),
        (
            "ThesisChange",
            "thesis_changes",
            table_counts["thesis_changes"],
            len(effective_thesis),
            (table_counts["thesis_changes"] or 0) - len(effective_thesis),
            "current analysis/comparison policy plus predecessor-correct timeline",
        ),
        (
            "CrossInvestorAssetSnapshot",
            "cross_investor_asset_snapshots",
            table_counts["cross_investor_asset_snapshots"],
            len(current_snapshot_heads),
            (table_counts["cross_investor_asset_snapshots"] or 0) - len(current_snapshot_heads),
            "latest current-policy head whose Attention IDs equal current effective Attention",
        ),
        (
            "CrossInvestorAssetAlignment",
            "cross_investor_asset_alignments",
            table_counts["cross_investor_asset_alignments"],
            len(effective_alignments),
            (table_counts["cross_investor_asset_alignments"] or 0) - len(effective_alignments),
            "active Alignment v1 tied to current Snapshot head",
        ),
        (
            "CrossInvestorConsensusEvidence",
            "cross_investor_consensus_evidences",
            table_counts["cross_investor_consensus_evidences"],
            len(effective_consensus),
            (table_counts["cross_investor_consensus_evidences"] or 0) - len(effective_consensus),
            "active Consensus v2 tied to current Snapshot/Alignment lineage",
        ),
        (
            "Portfolio",
            "portfolio",
            table_counts["portfolio"],
            table_counts["portfolio"],
            0,
            "portfolio master rows; status is reported separately",
        ),
        (
            "PortfolioSnapshot",
            "portfolio_snapshot_batches",
            table_counts["portfolio_snapshot_batches"],
            "n/a",
            table_counts["portfolio_snapshot_batches"],
            "immutable portfolio snapshot batches",
        ),
        (
            "PositionSnapshot",
            "position_snapshots",
            table_counts["position_snapshots"],
            "n/a",
            table_counts["position_snapshots"],
            "immutable position facts",
        ),
        (
            "PortfolioAction",
            "portfolio_actions",
            table_counts["portfolio_actions"],
            len(effective_actions),
            (table_counts["portfolio_actions"] or 0) - len(effective_actions),
            "effective adjacent-batch transitions",
        ),
        (
            "InvestorActionConsistency",
            "investor_action_consistencies",
            table_counts["investor_action_consistencies"],
            len(effective_consistencies),
            (table_counts["investor_action_consistencies"] or 0) - len(effective_consistencies),
            "effective action plus latest opinion pairing",
        ),
        (
            "InvestorActionClaim",
            "investor_action_claims",
            table_counts["investor_action_claims"],
            "n/a",
            table_counts["investor_action_claims"],
            "textual action claims; no active selector",
        ),
        (
            "InvestorAssetState",
            "investor_asset_states",
            table_counts["investor_asset_states"],
            table_counts["investor_asset_states"],
            0,
            "current Investor x Asset state table",
        ),
        (
            "InvestorAssetStateChange",
            "investor_asset_state_changes",
            table_counts["investor_asset_state_changes"],
            "n/a",
            table_counts["investor_asset_state_changes"],
            "immutable state transitions",
        ),
        (
            "InvestorBehaviorSnapshot",
            "investor_behavior_snapshots",
            table_counts["investor_behavior_snapshots"],
            sum(
                1
                for row in behavior_snapshots
                if row.get("active_analysis_version") == analysis_version
                and row.get("attention_policy_version") == attention_version
                and row.get("behavior_policy_version") == BEHAVIOR_SNAPSHOT_POLICY_VERSION
            ),
            table_counts["investor_behavior_snapshots"],
            "policy-compatible rows; immutable snapshots",
        ),
        (
            "Signal",
            "signals",
            table_counts["signals"],
            "n/a",
            table_counts["signals"],
            "no active policy selector in Signal table",
        ),
    ]

    # Status counts on the selected current active Analysis identity.
    current_status_counts = Counter(_enum_text(row.get("status")) for row in current_analysis_rows)
    current_status_counts.update({status: 0 for status in ALL_ANALYSIS_STATUSES})
    current_status_counts = Counter(
        {key: current_status_counts[key] for key in ALL_ANALYSIS_STATUSES}
    )
    active_analysis_event_count = len(active_analysis_event_ids)
    active_effective_analysis_event_count = len(effective_analysis_event_ids)
    missing_analysis_count = len(raw_only_event_ids)

    report: list[str] = []
    report.append("# Current Database Reality & Investor Coverage Report")
    report.append("")
    report.append(
        f"Audit query time: **{_fmt_dt(audit_time)}**; database: **{database_name}**; "
        "backend: **PostgreSQL**; transaction: **REPEATABLE READ + READ ONLY**; "
        "published dates/spans use **Asia/Hong_Kong**."
    )
    report.append("")
    report.append("## 1. Executive Summary")
    report.append("")
    report.append(
        f"The database contains **{len(raw_events):,} RawEvents** from **{len(investors)} Investors**, "
        f"covering **{_fmt_dt(raw_earliest)} → {_fmt_dt(raw_latest)}** "
        f"({_span_days(raw_earliest, raw_latest):.2f} observed days)."
    )
    report.append("")
    report.append(
        f"Current production Analysis identity exists for **{active_analysis_event_count:,} / {len(raw_events):,} RawEvents "
        f"({_pct(active_analysis_event_count, len(raw_events))})**; **{missing_analysis_count:,}** remain RawEvent-only. "
        f"Of the active identity, **{active_effective_analysis_event_count:,}** are analyzable "
        "(SUCCESS or PARTIALLY_RESOLVED)."
    )
    report.append("")
    report.append(
        f"Effective intelligence currently consists of **{len(effective_opinions):,} Opinions** "
        f"across **{len(effective_opinion_event_ids):,} RawEvents**, **{len(effective_attention):,} AttentionOccurrences**, "
        f"and **{len(effective_thesis):,} predecessor-correct ThesisChanges**. "
        f"Cross-investor evidence covers **{len(cross_attention_asset_ids):,} Assets with 2+ Attention Investors**; "
        f"only **{len(cross_opinion_3plus_asset_ids):,} Asset** is Consensus-v2 eligible under the >=3 Opinion-Investor rule."
    )
    report.append("")
    report.append(
        f"There are **{len(portfolios):,} Portfolios**, **{len(batches):,} PortfolioSnapshot batches**, "
        f"**{len(effective_actions):,} effective PortfolioActions**, and **{len(signals):,} Signals**."
    )
    report.append("")
    report.append(
        f"The immediate bottlenecks are **Analysis coverage for the {missing_analysis_count:,} RawEvents lacking current identity**, "
        "**asset resolution for unresolved references**, and **thin cross-investor Opinion overlap**. "
        "This audit does not select or start the next collection run."
    )

    report.append("")
    report.append("## 2. Database Totals")
    report.append("")
    report.append(
        _markdown_table(
            (
                "Entity",
                "Table",
                "Total rows",
                "Current/effective rows",
                "Historical/immutable rows",
                "Selection semantics",
            ),
            [
                (
                    entity,
                    table,
                    count_text(total),
                    count_text(current),
                    count_text(historical),
                    semantics,
                )
                for entity, table, total, current, historical, semantics in inventory_rows
            ],
        )
    )
    report.append("")
    report.append(
        "For master tables, `current` means the present row set because no temporal active selector exists. "
        "RawEvent, snapshot and change artifacts are immutable histories. EventAnalysis/Opinion/Attention/Thesis "
        "use explicit production identities and eligible statuses; cross-investor `current` is narrowed to the "
        "latest persisted current-policy lineage head, not merely `created_at` across all policies."
    )
    report.append("")
    report.append(
        f"Additional raw counts: `EventAnalysis` rows total **{len(all_analyses):,}** "
        f"({len(active_analysis_rows):,} current production identity, {len(all_analyses) - len(active_analysis_rows):,} other identities); "
        f"effective Opinion assets **{len({_id(row.get('asset_id')) for row in effective_opinions}):,}**; "
        f"current policy Snapshot rows before head narrowing **{len(current_policy_snapshots):,}**, "
        f"current Snapshot heads **{len(current_snapshot_heads):,}**, current Alignment lineage **{len(effective_alignments):,}**, "
        f"current Consensus-v2 lineage **{len(effective_consensus):,}**."
    )

    report.append("")
    report.append("## 3. Pipeline Stage Coverage")
    report.append("")
    report.append(
        _markdown_table(
            ("Stage", "Unit", "Count", "Coverage", "Main Investors", "Main Assets", "Current gap"),
            [
                (
                    "RawEvent",
                    "RawEvents",
                    len(raw_events),
                    "100% of database facts",
                    _top_labels(
                        Counter(_id(row.get("investor_id")) for row in raw_events), investor_names
                    ),
                    "not resolved at RawEvent stage",
                    "No gap at storage stage; facts are immutable",
                ),
                (
                    "→ Analysis",
                    "RawEvents with current production Analysis identity",
                    active_analysis_event_count,
                    f"{_pct(active_analysis_event_count, len(raw_events))}; missing {missing_analysis_count}",
                    _top_labels(
                        Counter(
                            _id(row.get("investor_id"))
                            for row in raw_events
                            if _id(row.get("id")) in active_analysis_event_ids
                        ),
                        investor_names,
                    ),
                    "—",
                    f"{missing_analysis_count} RawEvents have no current active Analysis",
                ),
                (
                    "→ Effective Analysis",
                    "RawEvents with SUCCESS/PARTIALLY_RESOLVED current Analysis",
                    active_effective_analysis_event_count,
                    f"{_pct(active_effective_analysis_event_count, len(raw_events))} of RawEvents; {_pct(active_effective_analysis_event_count, active_analysis_event_count)} of active Analysis",
                    _top_labels(
                        Counter(
                            _id(row.get("investor_id"))
                            for row in raw_events
                            if _id(row.get("id")) in effective_analysis_event_ids
                        ),
                        investor_names,
                    ),
                    "—",
                    f"{active_analysis_event_count - active_effective_analysis_event_count} active analyses are NO_OPINION/FAILED",
                ),
                (
                    "→ Opinion",
                    "effective Opinion rows / RawEvents bearing Opinion",
                    f"{len(effective_opinions)} / {len(effective_opinion_event_ids)}",
                    f"{_pct(len(effective_opinion_event_ids), len(raw_events))} RawEvents; {len(effective_opinions)} rows",
                    _top_labels(
                        Counter(_id(row.get("investor_id")) for row in effective_opinions),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(_id(row.get("asset_id")) for row in effective_opinions), asset_names
                    ),
                    f"{len(effective_analysis_event_ids - effective_opinion_event_ids)} analyzable/current events have no effective Opinion",
                ),
                (
                    "→ Attention",
                    "effective Attention rows / RawEvents bearing evidence",
                    f"{len(effective_attention)} / {len(effective_attention_event_ids)}",
                    f"{_pct(len(effective_attention_event_ids), len(raw_events))} RawEvents; {len(effective_attention)} rows",
                    _top_labels(
                        Counter(_id(row.get("investor_id")) for row in effective_attention),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(_id(row.get("asset_id")) for row in effective_attention),
                        asset_names,
                    ),
                    f"{len(raw_events) - len(effective_attention_event_ids)} RawEvents have no effective Attention evidence",
                ),
                (
                    "→ Thesis",
                    "effective predecessor-correct ThesisChange rows / current events",
                    f"{len(effective_thesis)} / {len(effective_thesis_event_ids)}",
                    f"{_pct(len(effective_thesis_event_ids), len(effective_opinion_event_ids))} of Opinion-bearing RawEvents",
                    _top_labels(
                        Counter(_id(row.get("investor_id")) for row in effective_thesis),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(_id(row.get("asset_id")) for row in effective_thesis), asset_names
                    ),
                    f"{len(effective_opinions) - len(effective_thesis)} Opinion rows have no effective ThesisChange artifact",
                ),
                (
                    "→ Cross-Investor",
                    "Assets with 2+ Attention Investors / current Snapshot heads / Alignment / Consensus-v2",
                    f"{len(cross_attention_asset_ids)} / {len(current_snapshot_heads)} / {len(effective_alignments)} / {len(effective_consensus)}",
                    f"{_pct(len(cross_attention_asset_ids), len(attention_by_asset))} of Assets with effective Attention",
                    _top_labels(
                        Counter(
                            investor_id
                            for asset_id in cross_attention_asset_ids
                            for investor_id in attention_investors_by_asset[asset_id]
                        ),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(asset_id for asset_id in cross_attention_asset_ids), asset_names
                    ),
                    f"Only {len(cross_opinion_3plus_asset_ids)} Asset reaches Consensus-v2 Opinion-Investor >=3",
                ),
            ],
        )
    )
    report.append("")
    report.append("### Active Analysis status")
    report.append("")
    report.append(
        _markdown_table(
            ("Status", "Current active Analysis rows/events", "Share of active identity"),
            [
                (
                    status,
                    current_status_counts[status],
                    _pct(current_status_counts[status], active_analysis_event_count),
                )
                for status in ALL_ANALYSIS_STATUSES
            ],
        )
    )
    report.append("")
    report.append(
        "Pipeline interpretation: `RawEvent → Analysis` counts any current production identity, including "
        "NO_OPINION/FAILED. `Opinion`, `Attention`, and `Thesis` counts are effective only when linked to the "
        "active production identity and eligible status; no inactive analysis fallback is used."
    )

    report.append("")
    report.append("## 4. Current Production Identity")
    report.append("")
    report.append(
        _markdown_table(
            ("Item", "Current value"),
            [
                ("Production Analysis identity", active_spec.analysis_version),
                ("Provider", active_spec.provider_id),
                ("Model", active_spec.model_version),
                ("Opinion prompt/version", active_spec.prompt_version),
                ("Opinion schema/version", active_spec.schema_version),
                ("Opinion analysis policy", active_spec.analysis_policy_version),
                ("Thesis comparison identity", thesis_version),
                ("Thesis comparison prompt", "thesis-comparison-v1"),
                ("Thesis comparison schema", "thesis-comparison-result-v1"),
                ("Attention active policy", attention_version),
                ("Consistency active policy", CONSISTENCY_POLICY_VERSION),
                ("Cross-Investor Snapshot active policy", CROSS_INVESTOR_POLICY_VERSION),
                ("Alignment active policy", CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION),
                ("Consensus active policy", CROSS_INVESTOR_CONSENSUS_POLICY_VERSION),
                ("Behavior Snapshot active policy", BEHAVIOR_SNAPSHOT_POLICY_VERSION),
                (
                    "Current Analysis selection rule",
                    "EventAnalysis.analysis_version = production identity; effective downstream status IN (SUCCESS, PARTIALLY_RESOLVED); no fallback",
                ),
            ],
        )
    )
    report.append("")
    report.append(
        f"Active Analysis rows by version: `{_top_labels(analysis_version_counts, {})}`. "
        f"Active production model values: `{_top_labels(analysis_model_counts, {})}`. "
        f"Effective Opinion model values: `{_top_labels(opinion_model_counts, {})}`."
    )
    report.append("")
    report.append(
        f"The database also contains historical Thesis policy combinations: `{_top_labels(thesis_policy_counts, {})}`; "
        f"Attention policies: `{_top_labels(attention_policy_counts, {})}`; Alignment policies: `{_top_labels(alignment_policy_counts, {})}`; "
        f"Consensus policies: `{_top_labels(consensus_policy_counts, {})}`."
    )

    report.append("")
    report.append("## 5. Investor Coverage Table")
    report.append("")
    report.append(
        _markdown_table(
            (
                "Investor",
                "Xueqiu user id",
                "RawEvents",
                "Earliest",
                "Latest",
                "Span days",
                "Active days",
                "Active Analysis",
                "Missing",
                "SUCCESS",
                "PARTIAL",
                "NO_OPINION",
                "FAILED",
                "Effective Opinions",
                "Opinion Assets",
                "Attention",
                "Attention Assets",
                "Thesis",
                "Repeated Opinion pairs",
                "Repeated cross-day Attention pairs",
                "Resolved refs",
                "Unresolved refs",
            ),
            [
                (
                    metric["name"],
                    metric["platform_user_id"],
                    metric["raw_count"],
                    _fmt_dt(metric["earliest"]),
                    _fmt_dt(metric["latest"]),
                    f"{metric['span_days']:.2f}",
                    metric["active_days"],
                    f"{metric['analysis_count']} ({_pct(metric['analysis_count'], metric['raw_count'])})",
                    metric["missing_analysis"],
                    metric["status_counts"]["SUCCESS"],
                    metric["status_counts"]["PARTIALLY_RESOLVED"],
                    metric["status_counts"]["NO_OPINION"],
                    metric["status_counts"]["FAILED"],
                    metric["opinions"],
                    metric["opinion_assets"],
                    metric["attention"],
                    metric["attention_assets"],
                    metric["thesis"],
                    metric["repeated_opinion_pairs"],
                    metric["repeated_attention_cross_day_pairs"],
                    metric["resolved_refs"],
                    metric["unresolved_refs"],
                )
                for metric in sorted(
                    metrics.values(), key=lambda item: (-item["raw_count"], item["name"])
                )
            ],
        )
    )
    report.append("")
    report.append(
        "`Resolved refs` is the count of effective canonical Opinion rows; `Opinion Assets` is its distinct Asset count. "
        "`Unresolved refs` is the count of `structured_output.unresolved_assets` in the selected current production Analysis "
        "for that Investor."
    )

    report.append("")
    report.append("## 6. Historical Coverage")
    report.append("")
    report.append(
        "The report makes no COMPLETE_HISTORY claim. It only describes observed `published_time` facts. "
        "Audit-only classification thresholds (not written to the domain model) are: **DEEP_HISTORY** = RawEvents ≥50, "
        "span ≥25 days, active days ≥10; **MEDIUM_HISTORY** = RawEvents ≥10 and (span ≥7 days or active days ≥5); "
        "**SHALLOW_HISTORY** = RawEvents ≥2 and (span ≥1 day or active days ≥2); otherwise **MINIMAL_DATA**."
    )
    report.append("")
    depth_counts = Counter(metric["depth"] for metric in metrics.values())
    report.append(
        _markdown_table(
            ("Classification", "Investor count", "Investor names"),
            [
                (
                    depth,
                    depth_counts[depth],
                    "; ".join(
                        metric["name"]
                        for metric in sorted(
                            metrics.values(), key=lambda item: (-item["raw_count"], item["name"])
                        )
                        if metric["depth"] == depth
                    )
                    or "none",
                )
                for depth in ("DEEP_HISTORY", "MEDIUM_HISTORY", "SHALLOW_HISTORY", "MINIMAL_DATA")
            ],
        )
    )
    report.append("")
    report.append(
        "The global observed range is only a database observation window. An Investor with a 30-day span may still "
        "have sparse active days or gaps inside that span; this is why span and active-day density are both shown."
    )

    report.append("")
    report.append("## 7. Analysis Coverage vs Raw Coverage")
    report.append("")
    report.append(
        "Unprocessed means the RawEvent has no selected current production Analysis identity. These rows are only "
        "reported; they were not sent to Production Analysis."
    )
    report.append("")
    report.append(
        _markdown_table(
            (
                "Investor",
                "RawEvents",
                "Active Analysis",
                "Unprocessed",
                "Unprocessed earliest",
                "Unprocessed latest",
                "Analysis coverage",
            ),
            [
                (
                    metric["name"],
                    metric["raw_count"],
                    metric["analysis_count"],
                    metric["missing_analysis"],
                    _fmt_dt(metric["unprocessed_earliest"]),
                    _fmt_dt(metric["unprocessed_latest"]),
                    _pct(metric["analysis_count"], metric["raw_count"]),
                )
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (-item["missing_analysis"], -item["raw_count"], item["name"]),
                )
                if metric["missing_analysis"] > 0
            ],
        )
    )
    report.append("")
    report.append(
        f"{sum(metric['missing_analysis'] > 0 for metric in metrics.values())} Investors have unprocessed RawEvents; "
        f"{sum(metric['missing_analysis'] for metric in metrics.values())} RawEvents total remain at RawEvent stage."
    )

    report.append("")
    report.append("## 8. Data Origin / Collection Type")
    report.append("")
    report.append(f"Persisted `RawEvent.source` values: **{source_text}**.")
    report.append("")
    marker_rows = [
        (
            key,
            sum(values.values()),
            ", ".join(f"{value}={count}" for value, count in values.most_common(10))
            or "not populated",
        )
        for key, values in marker_values.items()
    ]
    report.append(
        _markdown_table(
            ("Candidate provenance field", "Populated rows", "Observed values"), marker_rows
        )
    )
    report.append("")
    if provenance_reliable:
        report.append(
            "The database contains a populated explicit provenance marker with multiple recognized collection categories; per-Investor collection-type counts follow."
        )
        provenance_by_investor: dict[str, Counter[str]] = defaultdict(Counter)
        # This branch is intentionally conservative: only the recognized
        # explicit marker is used, never source, dates, URL shape or volume.
        for event in raw_events:
            raw_data = _as_map(event.get("raw_data"))
            for key in PROVENANCE_KEYS:
                value = raw_data.get(key)
                if value is not None and str(value).strip():
                    provenance_by_investor[_id(event.get("investor_id"))][str(value)] += 1
                    break
        report.append("")
        report.append(
            _markdown_table(
                ("Investor", "Collection type counts"),
                (
                    (
                        investor_names.get(investor_id, investor_id),
                        ", ".join(f"{key}={value}" for key, value in values.items()),
                    )
                    for investor_id, values in sorted(
                        provenance_by_investor.items(),
                        key=lambda item: investor_names.get(item[0], item[0]),
                    )
                ),
            )
        )
    else:
        report.append("**DATABASE DOES NOT PRESERVE RELIABLE COLLECTION-MODE PROVENANCE.**")
        report.append("")
        report.append(
            "The adapters persist both Following Feed and profile historical CDP captures with `source='xueqiu'`; "
            "the current RawEvent/raw_data fields do not carry a reliable explicit collection type. The report therefore "
            "does not infer origin from time ranges, URL shape, post volume, or event counts. Manual/other origin cannot "
            "be separated reliably unless an explicit marker is present."
        )

    report.append("")
    report.append("## 9. Asset / Cross-Investor Distribution")
    report.append("")
    report.append(
        f"Canonical Asset master count: **{len(assets):,}**. The following investor counts use current effective Attention "
        f"and effective Opinion evidence, not immutable historical rows."
    )
    attention_investor_distribution = Counter(
        len(value) for value in attention_investors_by_asset.values()
    )
    opinion_investor_distribution = Counter(
        len(value) for value in opinion_investors_by_asset.values()
    )
    report.append("")
    report.append(
        _markdown_table(
            ("Distribution", "Asset count"),
            (
                ("Assets with 1 Attention Investor", attention_investor_distribution.get(1, 0)),
                (
                    "Assets with 2 Attention Investors",
                    sum(
                        value for key, value in attention_investor_distribution.items() if key == 2
                    ),
                ),
                (
                    "Assets with 3+ Attention Investors",
                    sum(
                        value for key, value in attention_investor_distribution.items() if key >= 3
                    ),
                ),
                ("Assets with 2+ Attention Investors", len(cross_attention_asset_ids)),
                (
                    "Assets with 3+ Attention Investors",
                    sum(
                        value for key, value in attention_investor_distribution.items() if key >= 3
                    ),
                ),
                ("Assets with 1 Opinion Investor", opinion_investor_distribution.get(1, 0)),
                ("Assets with 2+ Opinion Investors", len(cross_opinion_asset_ids)),
                ("Assets with 3+ Opinion Investors", len(cross_opinion_3plus_asset_ids)),
            ),
        )
    )
    report.append("")
    report.append("### Top shared Assets")
    report.append("")
    report.append(
        _markdown_table(
            (
                "Asset",
                "Attention Investors",
                "Opinion Investors",
                "Latest directions",
                "Opinion count",
                "Attention count",
                "Consensus v2 semantics",
                "Current Snapshot head",
            ),
            (
                (
                    item["name"],
                    item["attention_investor_count"],
                    item["opinion_investor_count"],
                    item["latest_directions"],
                    item["opinion_count"],
                    item["attention_count"],
                    item["consensus_v2"],
                    "yes" if item["snapshot_head"] else "no",
                )
                for item in shared_assets
            ),
        )
    )
    report.append("")
    report.append(
        "Consensus-v2 semantics are applied to the latest effective Opinion per Attention Investor: fewer than 3 "
        "Opinion Investors is INSUFFICIENT_EVIDENCE; direct bullish/bearish conflict is DIVERGENT; a directional side "
        "combined only with Neutral is MIXED_WITH_NEUTRAL. Alignment MIXED_DIRECTION remains a broader, separate state."
    )

    report.append("")
    report.append("## 10. Current Data-stage Summary")
    report.append("")
    report.append(
        _markdown_table(
            ("Stage", "Count / unit", "Main Investors", "Main Assets", "Current gap"),
            (
                (
                    "Stage 1 — Raw facts only",
                    f"{len(raw_only_event_ids)} RawEvents without current Analysis",
                    _top_labels(
                        Counter(
                            _id(raw_by_id[event_id].get("investor_id"))
                            for event_id in raw_only_event_ids
                        ),
                        investor_names,
                    ),
                    "not yet resolved",
                    "Production Analysis is paused; these facts remain unprocessed",
                ),
                (
                    "Stage 2 — Analyzed, no effective Opinion",
                    f"{len(analyzed_without_opinion_event_ids)} RawEvents",
                    _top_labels(
                        Counter(
                            _id(raw_by_id[event_id].get("investor_id"))
                            for event_id in analyzed_without_opinion_event_ids
                        ),
                        investor_names,
                    ),
                    "unresolved/no-opinion events",
                    "NO_OPINION and unresolved assets prevent canonical Opinion coverage",
                ),
                (
                    "Stage 3 — Effective single-investor intelligence",
                    f"{len(effective_opinions)} Opinions; {len(opinions_by_pair)} Investor×Asset pairs; {len(effective_thesis)} ThesisChanges",
                    _top_labels(
                        Counter(_id(row.get("investor_id")) for row in effective_opinions),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(_id(row.get("asset_id")) for row in effective_opinions), asset_names
                    ),
                    f"{unresolved_total} unresolved asset references remain in current analyses",
                ),
                (
                    "Stage 4 — Cross-investor comparable evidence",
                    f"{len(cross_attention_asset_ids)} shared Attention Assets; {len(current_snapshot_heads)} Snapshot heads; {len(effective_alignments)} Alignments",
                    _top_labels(
                        Counter(
                            investor_id
                            for asset_id in cross_attention_asset_ids
                            for investor_id in attention_investors_by_asset[asset_id]
                        ),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(asset_id for asset_id in cross_attention_asset_ids), asset_names
                    ),
                    "most shared assets do not yet have >=3 Opinion Investors",
                ),
                (
                    "Stage 5 — Consensus-eligible evidence",
                    f"{len(cross_opinion_3plus_asset_ids)} fact-level Assets; {len(effective_consensus)} current Consensus-v2 rows",
                    _top_labels(
                        Counter(
                            investor_id
                            for asset_id in cross_opinion_3plus_asset_ids
                            for investor_id in opinion_investors_by_asset[asset_id]
                        ),
                        investor_names,
                    ),
                    _top_labels(
                        Counter(asset_id for asset_id in cross_opinion_3plus_asset_ids), asset_names
                    ),
                    "Opinion-Investor count and direction coverage are still sparse",
                ),
                (
                    "Stage 6 — Portfolio/behavior evidence",
                    f"{len(portfolios)} Portfolios; {len(batches)} batches; {len(positions)} positions; {len(effective_actions)} Actions; {len(effective_consistencies)} Consistencies; {len(behavior_snapshots)} BehaviorSnapshots; {len(signals)} Signals",
                    "none"
                    if not portfolios
                    else _top_labels(
                        Counter(_id(row.get("investor_id")) for row in portfolios), investor_names
                    ),
                    "none"
                    if not positions
                    else _top_labels(
                        Counter(
                            _id(row.get("asset_id"))
                            for row in positions
                            if row.get("asset_id") is not None
                        ),
                        asset_names,
                    ),
                    "no portfolio fact stream is currently present"
                    if not portfolios
                    else "broader portfolio history and effective alignment required",
                ),
            ),
        )
    )

    report.append("")
    report.append("## 11. Investor Coverage Matrix")
    report.append("")
    report.append(
        _markdown_table(
            (
                "Investor",
                "RawEvents",
                "Observed span",
                "Active days",
                "Analysis coverage",
                "Effective Opinions",
                "Attention",
                "Resolved Assets",
                "Shared Assets",
                "3+ overlap contribution",
                "Current data depth",
                "Main limitation",
            ),
            (
                (
                    metric["name"],
                    metric["raw_count"],
                    f"{metric['span_days']:.2f}d ({_fmt_dt(metric['earliest'])} → {_fmt_dt(metric['latest'])})",
                    metric["active_days"],
                    _pct(metric["analysis_count"], metric["raw_count"]),
                    metric["opinions"],
                    metric["attention"],
                    metric["resolved_assets"],
                    metric["shared_assets"],
                    metric["overlap_3plus"],
                    metric["depth"],
                    "; ".join(
                        part
                        for part in (
                            f"{metric['missing_analysis']} RawEvents unprocessed"
                            if metric["missing_analysis"]
                            else "",
                            f"{metric['unresolved_refs']} unresolved asset refs"
                            if metric["unresolved_refs"]
                            else "",
                            f"low intelligence-event density {_pct(metric['intelligence_event_coverage'] * metric['raw_count'], metric['raw_count'])}"
                            if metric["raw_count"] >= 30
                            and metric["intelligence_event_coverage"] < 0.20
                            else "",
                            "no shared Attention asset" if metric["shared_assets"] == 0 else "",
                            "no effective Opinion" if metric["opinions"] == 0 else "",
                        )
                        if part
                    )
                    or "no material gap at this audit granularity",
                )
                for metric in sorted(
                    metrics.values(), key=lambda item: (-item["raw_count"], item["name"])
                )
            ),
        )
    )
    report.append("")
    report.append("### Investor groups for human decision")
    report.append("")
    group_one = [
        metric
        for metric in metrics.values()
        if metric["depth"] == "DEEP_HISTORY"
        and metric["analysis_coverage"] >= 0.80
        and metric["intelligence_event_coverage"] >= 0.20
    ]
    group_two = [
        metric
        for metric in metrics.values()
        if metric["depth"] in {"DEEP_HISTORY", "MEDIUM_HISTORY"} and metric["missing_analysis"] > 0
    ]
    group_three = [metric for metric in metrics.values() if metric["raw_count"] <= 9]
    group_four = high_volume_low_density
    group_five = [
        metric
        for metric in metrics.values()
        if (metric["overlap_3plus"] >= 1 or metric["shared_assets"] >= 3)
        and (metric["missing_analysis"] > 0 or metric["analysis_coverage"] < 1.0)
    ]

    def group_line(items: list[dict[str, Any]]) -> str:
        return (
            "; ".join(
                f"{item['name']} (Raw {item['raw_count']}, span {item['span_days']:.1f}d, "
                f"analysis {_pct(item['analysis_count'], item['raw_count'])}, opinion {item['opinions']}, "
                f"shared {item['shared_assets']}, 3+ {item['overlap_3plus']})"
                for item in sorted(items, key=lambda value: (-value["raw_count"], value["name"]))
            )
            or "none"
        )

    report.append(
        _markdown_table(
            ("Group", "Audit rule", "Candidates and evidence"),
            (
                (
                    "① Already not urgent to add history",
                    "DEEP_HISTORY + analysis coverage ≥80% + intelligence-event coverage ≥20%",
                    group_line(group_one),
                ),
                (
                    "② Worth continuing historical coverage",
                    "DEEP/MEDIUM_HISTORY with unprocessed RawEvents",
                    group_line(group_two),
                ),
                ("③ Evidence too sparse; worth exploring", "RawEvents ≤9", group_line(group_three)),
                (
                    "④ High posting but low Intelligence density",
                    "RawEvents ≥30 and Opinion density <10% or intelligence-event coverage <20%",
                    group_line(group_four),
                ),
                (
                    "⑤ Existing high-value overlap; prioritize completion",
                    "3+ overlap contribution or ≥3 shared assets, with analysis incomplete",
                    group_line(group_five),
                ),
            ),
        )
    )
    report.append("")
    report.append(
        "These groups are deliberately non-exclusive diagnostic views. They are not an automated collection list and "
        "do not initiate collection."
    )

    report.append("")
    report.append("## 12. High-value Investor Groups")
    report.append("")
    report.append(
        "High-value overlap is determined by current effective Attention/Opinion evidence: an Investor contributes to a "
        "3+ overlap when it appears in an Asset's current Attention Investor set of at least three."
    )
    report.append("")
    report.append(
        _markdown_table(
            (
                "Investor",
                "Shared Assets",
                "3+ overlap contribution",
                "Effective Opinions",
                "Attention",
                "Unprocessed",
                "Why it matters",
            ),
            (
                (
                    metric["name"],
                    metric["shared_assets"],
                    metric["overlap_3plus"],
                    metric["opinions"],
                    metric["attention"],
                    metric["missing_analysis"],
                    "contributes to a 3+ shared-Asset set"
                    if metric["overlap_3plus"]
                    else "2-investor overlap only",
                )
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (
                        -item["overlap_3plus"],
                        -item["shared_assets"],
                        -item["opinions"],
                        item["name"],
                    ),
                )
                if metric["shared_assets"] > 0
            ),
        )
    )
    report.append("")
    report.append(
        "Highest current Opinion density is shown as `effective Opinion rows / RawEvents`; ratios for one-event "
        "Investors are mathematically high but statistically thin."
    )
    report.append("")
    report.append(
        _markdown_table(
            (
                "Investor",
                "RawEvents",
                "Effective Opinions",
                "Opinion density",
                "Intelligence-event coverage",
            ),
            (
                (
                    metric["name"],
                    metric["raw_count"],
                    metric["opinions"],
                    _pct(metric["opinions"], metric["raw_count"]),
                    _pct(
                        metric["intelligence_event_coverage"] * metric["raw_count"],
                        metric["raw_count"],
                    ),
                )
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (-item["opinion_density"], -item["raw_count"], item["name"]),
                )[:10]
            ),
        )
    )

    report.append("")
    report.append("## 13. Data Gaps")
    report.append("")
    gap_rows = [
        (
            "Investor history coverage",
            f"{sum(metric['depth'] in {'SHALLOW_HISTORY', 'MINIMAL_DATA'} for metric in metrics.values())} Investors are SHALLOW/MINIMAL; only {depth_counts['DEEP_HISTORY']} are DEEP",
            "Medium",
            "Expand history only after considering overlap and analysis backlog",
        ),
        (
            "Analysis coverage",
            f"{missing_analysis_count} RawEvents lack current Production Analysis; {current_status_counts['NO_OPINION']} active analyses are NO_OPINION",
            "High",
            "Current backlog is the largest pipeline-stage gap; remains paused in this sprint",
        ),
        (
            "Asset resolution",
            f"{unresolved_total} unresolved asset references across {len({name for names in unresolved_names_by_investor.values() for name in names})} distinct names",
            "High",
            "Canonical asset evidence is sparse relative to RawEvent volume",
        ),
        (
            "Opinion density",
            f"{len(effective_opinions)} effective Opinion rows over {len(raw_events)} RawEvents ({_pct(len(effective_opinions), len(raw_events))})",
            "High",
            "Interpretation layer is thin and unevenly distributed",
        ),
        (
            "Cross-Investor overlap",
            f"{len(cross_attention_asset_ids)} shared Attention Assets, {len(cross_opinion_asset_ids)} shared Opinion Assets, {len(cross_opinion_3plus_asset_ids)} Consensus-v2 eligible",
            "High",
            "Need more comparable effective Opinions on already-shared Assets",
        ),
        (
            "Portfolio/behavior",
            f"{len(portfolios)} portfolios and {len(effective_actions)} effective portfolio actions",
            "High",
            "No current portfolio fact stream",
        ),
        (
            "Collection provenance",
            "Following vs profile historical CDP vs manual cannot be separated reliably",
            "Medium",
            "Do not infer origin from time/volume; preserve explicit provenance in a future scoped change",
        ),
    ]
    report.append(
        _markdown_table(("Dimension", "Observed fact", "Audit priority", "Implication"), gap_rows)
    )

    report.append("")
    report.append("## 14. Suggested Next Collection Candidates")
    report.append("")
    candidate_high_overlap = [
        metric
        for metric in metrics.values()
        if metric["overlap_3plus"] > 0 and metric["missing_analysis"] > 0
    ]
    candidate_shared_incomplete = [
        metric
        for metric in metrics.values()
        if metric["shared_assets"] > 0
        and metric["depth"] in {"MEDIUM_HISTORY", "SHALLOW_HISTORY", "MINIMAL_DATA"}
    ]
    candidate_explore = [
        metric
        for metric in metrics.values()
        if metric["raw_count"] <= 9 and metric["shared_assets"] > 0
    ]
    report.append(
        _markdown_table(
            ("Candidate tier", "Candidate Investors", "Evidence basis"),
            (
                (
                    "A. High-value overlap with incomplete current pipeline",
                    group_line(candidate_high_overlap),
                    "Already contributes to an Asset observed by 3+ Attention Investors, and still has RawEvents without current Analysis",
                ),
                (
                    "B. Shared Assets but shallow/medium history",
                    group_line(candidate_shared_incomplete),
                    "An additional bounded history window could improve comparable Investor×Asset evidence, subject to human review",
                ),
                (
                    "C. Sparse but potentially informative exploration",
                    group_line(candidate_explore),
                    "Very little data today, but at least one shared Asset already exists",
                ),
                (
                    "D. Large RawEvent backlog / low Intelligence density",
                    group_line(high_volume_low_density),
                    "High volume alone does not imply priority; the bottleneck may be Analysis/asset resolution rather than collection",
                ),
            ),
        )
    )
    report.append("")
    report.append(
        "Candidate tiers are evidence-backed suggestions only. No final list is selected, and no collection is started. "
        "Because Analysis is currently paused, a human decision should weigh whether to first process the existing RawEvent "
        "backlog versus acquiring more history."
    )

    report.append("")
    report.append("## 15. Reality Study Findings")
    report.append("")
    findings = [
        ("1", "Current real RawEvents", f"{len(raw_events):,}"),
        (
            "2",
            "RawEvents with current Production Analysis identity",
            f"{active_analysis_event_count:,} ({_pct(active_analysis_event_count, len(raw_events))})",
        ),
        ("3", "RawEvents still only at RawEvent stage", f"{missing_analysis_count:,}"),
        (
            "4",
            "Deepest current observed Investors",
            "; ".join(
                metric["name"]
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (-item["span_days"], -item["raw_count"], item["name"]),
                )[:10]
            ),
        ),
        (
            "5",
            "Investors near 30d observed history",
            "; ".join(
                metric["name"]
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (-item["span_days"], -item["raw_count"], item["name"]),
                )
                if metric["span_days"] >= 25 and metric["raw_count"] >= 10
            )
            or "none",
        ),
        (
            "6",
            "Investors with only a few days or few rows",
            "; ".join(
                metric["name"]
                for metric in sorted(
                    metrics.values(), key=lambda item: (item["raw_count"], item["name"])
                )
                if metric["depth"] in {"MINIMAL_DATA", "SHALLOW_HISTORY"}
            )
            or "none",
        ),
        (
            "7",
            "Highest Opinion density",
            "; ".join(
                f"{metric['name']} {_pct(metric['opinions'], metric['raw_count'])} ({metric['opinions']}/{metric['raw_count']})"
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (-item["opinion_density"], -item["raw_count"], item["name"]),
                )[:10]
            )
            or "none",
        ),
        (
            "8",
            "High RawEvent but low Intelligence density",
            "; ".join(
                f"{metric['name']} (Raw {metric['raw_count']}, intelligence-event {_pct(metric['intelligence_event_coverage'] * metric['raw_count'], metric['raw_count'])})"
                for metric in high_volume_low_density
            )
            or "none",
        ),
        (
            "9",
            "Most important Cross-Investor overlap contributors",
            "; ".join(
                f"{metric['name']} (3+ overlap {metric['overlap_3plus']}, shared {metric['shared_assets']})"
                for metric in sorted(
                    metrics.values(),
                    key=lambda item: (
                        -item["overlap_3plus"],
                        -item["shared_assets"],
                        -item["opinions"],
                        item["name"],
                    ),
                )
                if metric["shared_assets"] > 0
            )
            or "none",
        ),
        (
            "10",
            "Next history candidates",
            "See Section 14; high-overlap incomplete candidates are suggestions, not an automated list",
        ),
        (
            "11",
            "Current bottleneck",
            "Analysis coverage + Asset Resolution + Opinion density + Cross-Investor overlap; Investor history is also shallow for many Investors; Portfolio evidence is absent",
        ),
    ]
    report.append(_markdown_table(("#", "Question", "Finding"), findings))

    report.append("")
    report.append("## 16. Recommended Next Decision")
    report.append("")
    report.append(
        "Keep CDP collection, LLM/Production Analysis, Intelligence rebuild and Signal generation paused until the human "
        "decision is made. The highest-information decision is whether to (a) resolve/inspect the existing Analysis "
        f"backlog of {missing_analysis_count:,} missing-identity RawEvents and {unresolved_total:,} unresolved asset references, or (b) collect more bounded history for the overlap candidates in "
        "Section 14. This report provides the evidence for that choice and performs neither action."
    )
    report.append("")
    report.append("### Read-only audit notes")
    report.append("")
    report.append(
        "No RawEvent, Analysis, Opinion, Attention, Thesis, Snapshot, Alignment, Consensus, Portfolio, State or Signal row "
        "was inserted, updated, deleted or rebuilt by this audit. No LLM provider was called."
    )
    report.append("")
    report.append(
        f"Raw source field distribution: `{source_text}`. Current analysis version: `{analysis_version}`. "
        f"Current Snapshot/Alignment/Consensus policies: `{CROSS_INVESTOR_POLICY_VERSION}` / "
        f"`{CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION}` / `{CROSS_INVESTOR_CONSENSUS_POLICY_VERSION}`."
    )
    return "\n".join(report) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional Markdown output path; database access remains read-only",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    connection, url = _connect_read_only()
    try:
        with connection.cursor() as cursor:
            database_name = str(
                _scalar(cursor, "SELECT current_database()") or url.database or "<unknown>"
            )
            data = _load_data(cursor)
            report = _build_report(data, database_name, datetime.now(HK))
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
