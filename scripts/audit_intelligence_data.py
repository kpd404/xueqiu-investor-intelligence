"""Read-only calibration audit for the Sprint 2F intelligence data foundation."""

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import psycopg
from sqlalchemy.engine import make_url

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
    get_settings,
)
from contracts import CONSISTENCY_POLICY_VERSION


@dataclass(frozen=True)
class AttentionRow:
    occurrence_id: UUID
    investor_id: UUID
    asset_id: UUID
    event_id: UUID
    published_time: datetime
    evidence_types: tuple[str, ...]


@dataclass(frozen=True)
class OpinionRow:
    opinion_id: UUID
    investor_id: UUID
    asset_id: UUID
    event_id: UUID
    published_time: datetime
    direction: str


@dataclass(frozen=True)
class ThesisRow:
    thesis_change_id: UUID
    investor_id: UUID
    asset_id: UUID
    previous_opinion_id: UUID | None
    previous_event_id: UUID | None
    current_opinion_id: UUID
    current_event_id: UUID
    effective_time: datetime
    change_type: str


@dataclass(frozen=True)
class BatchRow:
    batch_id: UUID
    portfolio_id: UUID
    snapshot_time: datetime
    source: str
    external_id: str


@dataclass(frozen=True)
class ActionRow:
    action_id: UUID
    portfolio_id: UUID
    asset_id: UUID | None
    previous_batch_id: UUID
    current_batch_id: UUID
    effective_time: datetime
    action_type: str


_PORTFOLIO_INVESTORS: dict[UUID, UUID] = {}


def _connect() -> psycopg.Connection[Any]:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            f"Sprint 2F.0 audit requires PostgreSQL; configured backend is {url.get_backend_name()}"
        )
    return psycopg.connect(
        host=url.host,
        port=url.port,
        dbname=url.database,
        user=url.username,
        password=url.password,
    )


def _fetchall(statement: str, params: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    # Use short independent read connections; this avoids a local psycopg
    # result-format quirk while keeping the audit strictly read-only.
    with _connect() as connection:
        with connection.cursor() as cursor:
            cursor.execute(statement, params)
            return list(cursor.fetchall())


def _fetchone(statement: str, params: tuple[Any, ...] = ()) -> tuple[Any, ...] | None:
    rows = _fetchall(statement, params)
    return rows[0] if rows else None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _uuid(value: Any) -> UUID:
    return value if isinstance(value, UUID) else UUID(str(value))


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _strings(value: Any) -> tuple[str, ...]:
    return tuple(str(item) for item in value) if isinstance(value, (list, tuple)) else ()


def _span_days(earliest: datetime | None, latest: datetime | None) -> float:
    if earliest is None or latest is None:
        return 0.0
    return (_utc(latest) - _utc(earliest)).total_seconds() / 86400


def _counter_text(values: Counter[Any]) -> str:
    return ", ".join(f"{key}={value}" for key, value in values.most_common()) or "none"


def _section(title: str) -> None:
    print(f"\n## {title}")


def _load_opinions(version: str) -> list[OpinionRow]:
    rows = _fetchall(
        """
        SELECT o.id, o.investor_id, o.asset_id, o.event_id,
               r.published_time, o.direction
        FROM opinions o
        JOIN raw_events r ON r.id = o.event_id
        JOIN event_analyses ea ON ea.id = o.analysis_id
        WHERE ea.analysis_version = %s
          AND ea.status IN ('SUCCESS', 'PARTIALLY_RESOLVED')
        ORDER BY o.investor_id, o.asset_id, r.published_time, r.id, o.id
        """,
        (version,),
    )
    return [
        OpinionRow(
            opinion_id=_uuid(row[0]),
            investor_id=_uuid(row[1]),
            asset_id=_uuid(row[2]),
            event_id=_uuid(row[3]),
            published_time=_utc(row[4]),
            direction=getattr(row[5], "value", str(row[5])),
        )
        for row in rows
    ]


def _load_attention(analysis_version: str, attention_version: str) -> list[AttentionRow]:
    rows = _fetchall(
        """
        SELECT ao.id, ao.investor_id, ao.asset_id, ao.event_id,
               ao.published_time, ao.evidence_types
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
        ORDER BY ao.published_time, ao.id
        """,
        (attention_version, analysis_version),
    )
    return [
        AttentionRow(
            occurrence_id=_uuid(row[0]),
            investor_id=_uuid(row[1]),
            asset_id=_uuid(row[2]),
            event_id=_uuid(row[3]),
            published_time=_utc(row[4]),
            evidence_types=_strings(row[5]),
        )
        for row in rows
    ]


def _load_thesis(
    opinions: list[OpinionRow],
    analysis_version: str,
    comparison_version: str,
) -> list[ThesisRow]:
    predecessor: dict[UUID, tuple[UUID | None, UUID | None]] = {}
    previous_by_pair: dict[tuple[UUID, UUID], tuple[UUID, UUID]] = {}
    for opinion in opinions:
        pair = (opinion.investor_id, opinion.asset_id)
        predecessor[opinion.opinion_id] = previous_by_pair.get(pair, (None, None))
        previous_by_pair[pair] = (opinion.opinion_id, opinion.event_id)

    rows = _fetchall(
        """
        SELECT tc.id, tc.investor_id, tc.asset_id,
               tc.previous_opinion_id, tc.previous_event_id,
               tc.current_opinion_id, tc.current_event_id,
               tc.effective_time, tc.change_type
        FROM thesis_changes tc
        JOIN opinions o ON o.id = tc.current_opinion_id
        JOIN event_analyses ea ON ea.id = o.analysis_id
        WHERE tc.opinion_analysis_version = %s
          AND tc.comparison_version = %s
          AND ea.analysis_version = %s
          AND ea.status IN ('SUCCESS', 'PARTIALLY_RESOLVED')
        ORDER BY tc.effective_time, tc.id
        """,
        (analysis_version, comparison_version, analysis_version),
    )
    result: list[ThesisRow] = []
    for row in rows:
        current_id = _uuid(row[5])
        expected = predecessor.get(current_id)
        if expected is None:
            continue
        previous_id = _uuid(row[3]) if row[3] is not None else None
        previous_event = _uuid(row[4]) if row[4] is not None else None
        if (previous_id, previous_event) != expected:
            continue
        result.append(
            ThesisRow(
                thesis_change_id=_uuid(row[0]),
                investor_id=_uuid(row[1]),
                asset_id=_uuid(row[2]),
                previous_opinion_id=previous_id,
                previous_event_id=previous_event,
                current_opinion_id=current_id,
                current_event_id=_uuid(row[6]),
                effective_time=_utc(row[7]),
                change_type=getattr(row[8], "value", str(row[8])),
            )
        )
    return result


def _load_batches() -> list[BatchRow]:
    return [
        BatchRow(
            batch_id=_uuid(row[0]),
            portfolio_id=_uuid(row[1]),
            snapshot_time=_utc(row[2]),
            source=str(row[3]),
            external_id=str(row[4]),
        )
        for row in _fetchall(
            """
            SELECT id, portfolio_id, snapshot_time, source, external_id
            FROM portfolio_snapshot_batches
            ORDER BY portfolio_id, snapshot_time, source, external_id, id
            """
        )
    ]


def _load_actions() -> list[ActionRow]:
    return [
        ActionRow(
            action_id=_uuid(row[0]),
            portfolio_id=_uuid(row[1]),
            asset_id=_uuid(row[2]) if row[2] is not None else None,
            previous_batch_id=_uuid(row[3]),
            current_batch_id=_uuid(row[4]),
            effective_time=_utc(row[5]),
            action_type=getattr(row[6], "value", str(row[6])),
        )
        for row in _fetchall(
            """
            SELECT id, portfolio_id, asset_id, previous_snapshot_batch_id,
                   current_snapshot_batch_id, effective_time, action_type
            FROM portfolio_actions
            ORDER BY effective_time, id
            """
        )
    ]


def _effective_actions(batches: list[BatchRow], actions: list[ActionRow]) -> list[ActionRow]:
    by_portfolio: dict[UUID, list[BatchRow]] = defaultdict(list)
    for batch in batches:
        by_portfolio[batch.portfolio_id].append(batch)
    adjacent: set[tuple[UUID, UUID]] = set()
    for timeline in by_portfolio.values():
        timeline.sort(
            key=lambda value: (
                value.snapshot_time,
                value.source,
                value.external_id,
                value.batch_id.int,
            )
        )
        adjacent.update(
            (previous.batch_id, current.batch_id)
            for previous, current in zip(timeline, timeline[1:], strict=False)
        )
    return [
        action
        for action in actions
        if (action.previous_batch_id, action.current_batch_id) in adjacent
    ]


def _load_consistencies(
    opinions: list[OpinionRow],
    actions: list[ActionRow],
    analysis_version: str,
) -> list[tuple[UUID, UUID, str, datetime]]:
    if not actions:
        return []
    action_ids = tuple(str(action.action_id) for action in actions)
    placeholders = ",".join("%s" for _ in action_ids)
    rows = _fetchall(
        f"""
        SELECT id, investor_id, asset_id, opinion_id, portfolio_action_id,
               consistency_type, effective_time
        FROM investor_action_consistencies
        WHERE opinion_analysis_version = %s
          AND consistency_policy_version = %s
          AND portfolio_action_id IN ({placeholders})
        ORDER BY effective_time, id
        """,
        (analysis_version, CONSISTENCY_POLICY_VERSION, *action_ids),
    )
    candidates = {
        (_uuid(row[4]), _uuid(row[3])): (
            _uuid(row[0]),
            _uuid(row[1]),
            _uuid(row[2]),
            str(getattr(row[5], "value", row[5])),
            _utc(row[6]),
        )
        for row in rows
    }
    opinions_by_pair: dict[tuple[UUID, UUID], list[OpinionRow]] = defaultdict(list)
    for opinion in opinions:
        opinions_by_pair[(opinion.investor_id, opinion.asset_id)].append(opinion)
    result: list[tuple[UUID, UUID, str, datetime]] = []
    for action in actions:
        if action.asset_id is None:
            continue
        investor_id = _PORTFOLIO_INVESTORS.get(action.portfolio_id)
        if investor_id is None:
            continue
        timeline = opinions_by_pair.get((investor_id, action.asset_id), [])
        eligible = [item for item in timeline if item.published_time <= action.effective_time]
        if not eligible:
            continue
        candidate = candidates.get((action.action_id, eligible[-1].opinion_id))
        if candidate is not None:
            result.append((candidate[0], candidate[1], candidate[3], candidate[4]))
    return result


def _print_dataset(raw_count: int) -> tuple[datetime | None, datetime | None]:
    _section("Dataset coverage")
    earliest, latest = _fetchone("SELECT min(published_time), max(published_time) FROM raw_events")
    print(f"Investors: {int(_fetchone('SELECT count(*) FROM investors')[0])}")
    print(f"RawEvents: {raw_count}")
    print(f"EventAnalyses: {int(_fetchone('SELECT count(*) FROM event_analyses')[0])}")
    print(f"Earliest published_time: {earliest}")
    print(f"Latest published_time: {latest}")
    print(f"Observed span days: {_span_days(earliest, latest):.2f}")
    print("RawEvents by Investor:")
    for name, investor_id, count in _fetchall(
        """
        SELECT i.name, i.id, count(r.id)
        FROM investors i
        LEFT JOIN raw_events r ON r.investor_id = i.id
        GROUP BY i.id, i.name
        ORDER BY count(r.id) DESC, i.name, i.id
        """
    ):
        print(f"  {name} [{investor_id}]: {count}")
    return (_utc(earliest) if earliest else None, _utc(latest) if latest else None)


def _print_resolution(analysis_version: str) -> None:
    _section("Asset resolution")
    rows = _fetchall(
        """
        SELECT ea.event_id, re.investor_id, re.published_time, ea.status, ea.structured_output
        FROM event_analyses ea
        JOIN raw_events re ON re.id = ea.event_id
        WHERE ea.analysis_version = %s
        ORDER BY re.published_time, ea.event_id, ea.id
        """,
        (analysis_version,),
    )
    unresolved: list[
        tuple[str, str | None, str | None, UUID, UUID, datetime, str, tuple[str, ...]]
    ] = []
    status_counts: Counter[str] = Counter()
    for event_id, investor_id, published_time, status, structured in rows:
        status_counts[str(getattr(status, "value", status))] += 1
        for hint in _mapping(structured).get("unresolved_assets", ()):
            item = _mapping(hint)
            candidate_ids = tuple(
                str(candidate) for candidate in item.get("candidate_asset_ids", ())
            )
            unresolved.append(
                (
                    str(item.get("asset_name") or "<missing>"),
                    str(item["symbol"]) if item.get("symbol") else None,
                    str(item["market"]) if item.get("market") else None,
                    _uuid(event_id),
                    _uuid(investor_id),
                    _utc(published_time),
                    str(item.get("reason") or getattr(status, "value", status)),
                    candidate_ids,
                )
            )
    print(f"Canonical Asset master count: {_fetchone('SELECT count(*) FROM assets')[0]}")
    print(f"AssetAlias count: {_fetchone('SELECT count(*) FROM asset_aliases')[0]}")
    print(f"Active Analysis status distribution: {_counter_text(status_counts)}")
    resolved_rows = _fetchone(
        "SELECT count(*) FROM opinions o "
        "JOIN event_analyses ea ON ea.id = o.analysis_id "
        "WHERE ea.analysis_version = %s "
        "AND ea.status IN ('SUCCESS', 'PARTIALLY_RESOLVED')",
        (analysis_version,),
    )[0]
    print(f"Active resolved Opinion rows: {resolved_rows}")
    print(f"Active unresolved entries: {len(unresolved)}")
    print(
        f"Active unique unresolved names: {len({item[0].strip().lower() for item in unresolved})}"
    )
    frequencies = Counter(item[0] for item in unresolved)
    print(f"High-frequency unresolved references: {_counter_text(frequencies)}")
    if unresolved:
        print("Unresolved samples:")
        shown: set[str] = set()
        for item in sorted(
            unresolved,
            key=lambda value: (-frequencies[value[0]], value[0], value[5], value[3].int),
        ):
            name, symbol, market, event_id, investor_id, published_time, reason, _ = item
            if name in shown:
                continue
            shown.add(name)
            print(
                f"  {name}: symbol={symbol or '-'} market={market or '-'} "
                f"event={event_id} investor={investor_id} time={published_time} reason={reason}"
            )
            if len(shown) >= 20:
                break
        ambiguous = sum(len(item[7]) >= 2 for item in unresolved)
        print(f"Ambiguous unresolved entries (2+ candidates): {ambiguous}")
        explicit_candidates = sorted(
            {(item[0], item[1], item[2]) for item in unresolved if item[1] and item[2]}
        )
        print(
            "Deterministic Asset Master candidates (explicit symbol+market): "
            f"{explicit_candidates or 'none'}"
        )
        partial_candidates = sorted(
            {(item[0], item[1], item[2]) for item in unresolved if item[1] and not item[2]}
        )
        print(
            "Partial symbol evidence (market confirmation still required): "
            f"{partial_candidates or 'none'}"
        )
    else:
        print("Ambiguous unresolved entries (2+ candidates): 0")
        print("Deterministic Asset Master candidates (explicit symbol+market): none")
        print("Partial symbol evidence (market confirmation still required): none")


def _print_attention(
    attention: list[AttentionRow],
    investor_names: dict[UUID, str],
    asset_names: dict[UUID, str],
) -> None:
    _section("Attention")
    pair_times: dict[tuple[UUID, UUID], list[datetime]] = defaultdict(list)
    for row in attention:
        pair_times[(row.investor_id, row.asset_id)].append(row.published_time)
    pair_stats = {
        pair: (len(times), len({value.date() for value in times}))
        for pair, times in pair_times.items()
    }
    evidence_membership = Counter(
        evidence_type for row in attention for evidence_type in set(row.evidence_types)
    )
    print(f"AttentionOccurrence total: {len(attention)}")
    print(f"Distinct Investor x Asset pairs: {len(pair_stats)}")
    print(f"New attention count (first observed pair in dataset): {len(pair_stats)}")
    print(f"Evidence membership: {_counter_text(evidence_membership)}")
    print("Occurrence_count x distinct_active_days distribution:")
    for (count, days), pair_count in sorted(Counter(pair_stats.values()).items()):
        print(f"  occurrences={count}, active_days={days}: {pair_count} pairs")
    examples = [pair for pair, stats in pair_stats.items() if stats in {(3, 1), (3, 3)}]
    if examples:
        print("Density examples:")
        for investor_id, asset_id in sorted(
            examples, key=lambda value: (str(value[0]), str(value[1]))
        ):
            count, days = pair_stats[(investor_id, asset_id)]
            print(
                f"  {investor_names.get(investor_id, investor_id)} x "
                f"{asset_names.get(asset_id, asset_id)}: occurrences={count}, active_days={days}"
            )
    else:
        print("Density examples (3 occurrences/1 day vs 3 occurrences/3 days): not observed")


def _print_opinion(
    opinions: list[OpinionRow],
    raw_event_count: int,
    investor_names: dict[UUID, str],
    asset_names: dict[UUID, str],
) -> None:
    _section("Production-effective Opinion")
    pair_counts = Counter((row.investor_id, row.asset_id) for row in opinions)
    repeated = {pair: count for pair, count in pair_counts.items() if count >= 2}
    print(f"Effective Opinion count: {len(opinions)}")
    print(
        f"Opinion / RawEvent ratio: {len(opinions) / raw_event_count:.4f}"
        if raw_event_count
        else "Opinion / RawEvent ratio: n/a"
    )
    print(f"Distinct Investor x Asset pairs: {len(pair_counts)}")
    print(f"Repeated Investor x Asset pairs: {len(repeated)}")
    print(f"Direction distribution: {_counter_text(Counter(row.direction for row in opinions))}")
    for (investor_id, asset_id), count in sorted(
        repeated.items(), key=lambda item: (-item[1], str(item[0][0]), str(item[0][1]))
    )[:30]:
        print(
            f"  {investor_names.get(investor_id, investor_id)} x "
            f"{asset_names.get(asset_id, asset_id)}: {count}"
        )


def _print_thesis(
    thesis: list[ThesisRow],
    investor_names: dict[UUID, str],
    asset_names: dict[UUID, str],
) -> None:
    _section("Effective ThesisChange")
    pair_counts = Counter((row.investor_id, row.asset_id) for row in thesis)
    print(f"Effective ThesisChange total: {len(thesis)}")
    print(f"Change type distribution: {_counter_text(Counter(row.change_type for row in thesis))}")
    print(
        f"Pairs with repeated thesis history: {sum(count >= 2 for count in pair_counts.values())}"
    )
    for row in thesis[:20]:
        print(
            f"  {investor_names.get(row.investor_id, row.investor_id)} x "
            f"{asset_names.get(row.asset_id, row.asset_id)} "
            f"{row.effective_time} {row.change_type}"
        )


def _print_overlap(
    attention: list[AttentionRow],
    opinions: list[OpinionRow],
    investor_names: dict[UUID, str],
    asset_names: dict[UUID, str],
) -> None:
    _section("Cross-investor overlap")
    pair_counts = Counter((row.investor_id, row.asset_id) for row in attention)
    investors_by_asset: dict[UUID, set[UUID]] = defaultdict(set)
    for investor_id, asset_id in pair_counts:
        investors_by_asset[asset_id].add(investor_id)
    overlap = Counter(len(value) for value in investors_by_asset.values())
    print(f"Assets observed by 1 Investor: {overlap.get(1, 0)}")
    print(f"Assets observed by 2 Investors: {overlap.get(2, 0)}")
    print(f"Assets observed by 3+ Investors: {sum(v for k, v in overlap.items() if k >= 3)}")
    latest: dict[tuple[UUID, UUID], OpinionRow] = {}
    for opinion in opinions:
        latest[(opinion.investor_id, opinion.asset_id)] = opinion
    for asset_id, investors in sorted(
        investors_by_asset.items(), key=lambda item: (-len(item[1]), str(item[0]))
    )[:20]:
        if len(investors) < 2:
            continue
        directions = [
            latest[(investor_id, asset_id)].direction
            for investor_id in investors
            if (investor_id, asset_id) in latest
        ]
        total_attention = sum(
            count
            for (investor_id, observed_asset), count in pair_counts.items()
            if observed_asset == asset_id
        )
        names = sorted(
            investor_names.get(investor_id, str(investor_id)) for investor_id in investors
        )
        print(
            f"  {asset_names.get(asset_id, asset_id)}: investors={len(investors)} "
            f"names={'; '.join(names)} attention={total_attention} "
            f"latest_directions={','.join(sorted(directions)) or 'none'}"
        )


def _print_portfolio(
    batches: list[BatchRow],
    actions: list[ActionRow],
    opinions: list[OpinionRow],
    analysis_version: str,
) -> tuple[list[ActionRow], int]:
    _section("Portfolio reality check")
    rows = _fetchall("SELECT id, investor_id FROM portfolio ORDER BY id")
    _PORTFOLIO_INVESTORS.clear()
    _PORTFOLIO_INVESTORS.update({_uuid(row[0]): _uuid(row[1]) for row in rows})
    effective = _effective_actions(batches, actions)
    print(f"Investors with Portfolio: {len({_uuid(row[1]) for row in rows})}")
    print(f"Portfolio count: {len(rows)}")
    print(f"SnapshotBatch count: {len(batches)}")
    print(f"PositionSnapshot count: {_fetchone('SELECT count(*) FROM position_snapshots')[0]}")
    print(f"Effective PortfolioAction count: {len(effective)}")
    effective_consistency = _load_consistencies(opinions, effective, analysis_version)
    consistency_total = _fetchone("SELECT count(*) FROM investor_action_consistencies")[0]
    print(f"InvestorActionConsistency rows: {consistency_total}")
    print(f"Effective InvestorActionConsistency count: {len(effective_consistency)}")
    print(
        "Portfolio classification: A. fact stream available"
        if effective and opinions
        else "Portfolio classification: B. sparse/auxiliary evidence"
    )
    return effective, len(effective_consistency)


def _print_sample_bias() -> None:
    _section("Investor sample bias")
    styles = _fetchall(
        "SELECT investment_style, count(*) FROM investors "
        "WHERE investment_style IS NOT NULL "
        "GROUP BY investment_style ORDER BY count(*) DESC"
    )
    industries = _fetchall(
        "SELECT industry, count(*) FROM assets "
        "WHERE industry IS NOT NULL GROUP BY industry ORDER BY count(*) DESC"
    )
    themes = _fetchall(
        "SELECT themes FROM assets WHERE themes IS NOT NULL AND themes::text <> '[]'"
    )
    if not styles and not industries and not themes:
        print("INSUFFICIENT_DATA: style/industry/theme fields are not populated.")
        return
    print(f"Investment style distribution: {styles or 'INSUFFICIENT_DATA'}")
    print(f"Asset industry distribution: {industries or 'INSUFFICIENT_DATA'}")
    theme_counter: Counter[str] = Counter()
    for (value,) in themes:
        if isinstance(value, list):
            theme_counter.update(str(item) for item in value)
    print(f"Asset theme distribution: {theme_counter or 'INSUFFICIENT_DATA'}")


def _print_quality(
    raw_count: int,
    analysis_version: str,
    attention: list[AttentionRow],
    opinions: list[OpinionRow],
    effective_actions: list[ActionRow],
    effective_consistency_count: int,
) -> None:
    _section("Data quality")
    active_analysis = int(
        _fetchone(
            "SELECT count(*) FROM event_analyses WHERE analysis_version = %s",
            (analysis_version,),
        )[0]
    )
    failed = int(
        _fetchone(
            "SELECT count(*) FROM event_analyses WHERE analysis_version = %s AND status = 'FAILED'",
            (analysis_version,),
        )[0]
    )
    print(
        f"Active Analysis missing rate: {(raw_count - active_analysis) / raw_count:.4f}"
        if raw_count
        else "Active Analysis missing rate: n/a"
    )
    print(f"Active FAILED Analysis rows: {failed}")
    attention_event_count = len({row.event_id for row in attention})
    print(f"RawEvents without effective Attention: {raw_count - attention_event_count}")
    print(f"Effective Opinion rows: {len(opinions)}")
    print(f"Effective PortfolioAction rows: {len(effective_actions)}")
    print(f"Effective InvestorActionConsistency rows: {effective_consistency_count}")
    unique_occurrences = len({(row.event_id, row.asset_id) for row in attention})
    print(f"Duplicate effective event x asset occurrences: {len(attention) - unique_occurrences}")
    print("Inactive Analysis fallback: excluded by effective selectors.")
    print("Quoted/repost attribution and alias issues: targeted review required; no inference.")


def _print_recommendation(
    attention: list[AttentionRow],
    opinions: list[OpinionRow],
    thesis: list[ThesisRow],
    effective_actions: list[ActionRow],
) -> None:
    _section("Recommendation")
    shared_assets = sum(
        len({row.investor_id for row in attention if row.asset_id == asset_id}) >= 2
        for asset_id in {row.asset_id for row in attention}
    )
    repeated_opinions = sum(
        count >= 2
        for count in Counter((row.investor_id, row.asset_id) for row in opinions).values()
    )
    repeated_thesis = sum(
        count >= 2 for count in Counter((row.investor_id, row.asset_id) for row in thesis).values()
    )
    print(f"Shared assets with >=2 Investors: {shared_assets}")
    print(f"Repeated Opinion pairs: {repeated_opinions}")
    print(f"Repeated ThesisChange pairs: {repeated_thesis}")
    print(f"Effective PortfolioAction facts: {len(effective_actions)}")
    print(
        "Consensus/Divergence: overlap foundation exists at calibration scale."
        if shared_assets
        else "Consensus/Divergence: NOT READY; no multi-investor overlap observed."
    )
    print("Attention Momentum: keep paused until natural multi-week coverage exists.")
    print(
        "Portfolio priority: auxiliary evidence."
        if not effective_actions
        else "Portfolio priority: fact stream available but still requires broader coverage."
    )
    if repeated_opinions and repeated_thesis:
        print(
            "Next priority: Cross-Investor overlap/consensus design, then "
            "Attention/Opinion quality."
        )
    elif repeated_opinions:
        print("Next priority: Opinion timeline quality before consensus implementation.")
    elif attention:
        print("Next priority: Attention evidence coverage and temporal sampling.")
    else:
        print("Next priority: data collection coverage.")
    print("2F.1: design discussion only; production Momentum remains out of scope.")
    print("2F.2/2F.3: current thesis/portfolio coverage is sparse.")


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    policy = get_production_analysis_policy()
    thesis_policy = get_production_thesis_comparison_policy()
    analysis_version = policy.active_analysis_version
    attention_policy_version = get_production_attention_policy_version()
    thesis_version = thesis_policy.active_analysis_version
    _print_environment(analysis_version, attention_policy_version, thesis_version)
    raw_count = int(_fetchone("SELECT count(*) FROM raw_events")[0])
    earliest, latest = _print_dataset(raw_count)
    opinions = _load_opinions(analysis_version)
    attention = _load_attention(analysis_version, attention_policy_version)
    thesis = _load_thesis(opinions, analysis_version, thesis_version)
    batches = _load_batches()
    actions = _load_actions()
    assets = {_uuid(row[0]): str(row[1]) for row in _fetchall("SELECT id, name FROM assets")}
    investors = {_uuid(row[0]): str(row[1]) for row in _fetchall("SELECT id, name FROM investors")}
    _print_resolution(analysis_version)
    _print_attention(attention, investors, assets)
    _print_opinion(opinions, raw_count, investors, assets)
    _print_thesis(thesis, investors, assets)
    _print_overlap(attention, opinions, investors, assets)
    effective_actions, effective_consistency_count = _print_portfolio(
        batches,
        actions,
        opinions,
        analysis_version,
    )
    _print_sample_bias()
    _print_quality(
        raw_count,
        analysis_version,
        attention,
        opinions,
        effective_actions,
        effective_consistency_count,
    )
    _print_recommendation(attention, opinions, thesis, effective_actions)
    print(
        f"\nAudit time range: {earliest} -> {latest}; span_days={_span_days(earliest, latest):.2f}"
    )
    return 0


def _print_environment(analysis_version: str, attention_version: str, thesis_version: str) -> None:
    _section("Environment")
    print(f"Database backend: {make_url(get_settings().database_url).get_backend_name()}")
    print(f"Opinion analysis version: {analysis_version}")
    print(f"Attention policy version: {attention_version}")
    print(f"Thesis comparison version: {thesis_version}")
    print(f"Consistency policy version: {CONSISTENCY_POLICY_VERSION}")


if __name__ == "__main__":
    raise SystemExit(main())
