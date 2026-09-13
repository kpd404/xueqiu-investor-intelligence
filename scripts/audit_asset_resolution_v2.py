"""Read-only Asset Resolution Audit v2.

This audit reads the current production Analysis identity and the existing
Asset/Alias catalog in one PostgreSQL repeatable-read, read-only transaction.
It never calls an LLM, writes PostgreSQL, rebuilds Intelligence, or mutates
the Asset Master.  Taxonomy, priority and impact values are audit-only.
"""

# Long report expressions are intentional; the audit logic is still checked by
# Ruff.  This file-level exception keeps the report formatting readable.
# ruff: noqa: E501

from __future__ import annotations

import argparse
import sys
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import UUID

import psycopg
from sqlalchemy.engine import URL, make_url

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_settings,
)
from contracts import (
    AssetReference,
    AssetResolutionStatus,
    UnresolvedAsset,
    normalize_market_hint,
)
from resolution import AssetResolver

HK = timezone(timedelta(hours=8), name="Asia/Hong_Kong")
Row = dict[str, Any]


class Category:
    EXPLICIT_MARKET_SYMBOL = "EXPLICIT_MARKET_SYMBOL"
    SYMBOL_MISSING_MARKET = "SYMBOL_MISSING_MARKET"
    EXISTING_ASSET_ALIAS_CANDIDATE = "EXISTING_ASSET_ALIAS_CANDIDATE"
    CANONICAL_LOOKING_NAME_ONLY = "CANONICAL_LOOKING_NAME_ONLY"
    NICKNAME_ABBREVIATION = "NICKNAME_ABBREVIATION"
    CROSS_LISTING_AMBIGUITY = "CROSS_LISTING_AMBIGUITY"
    UNSUPPORTED_MARKET_HINT = "UNSUPPORTED_MARKET_HINT"
    INDEX_OR_ETF = "INDEX_OR_ETF"
    CONCEPT_INDUSTRY_NON_SECURITY = "CONCEPT_INDUSTRY_NON_SECURITY"
    COMMODITY_MACRO_REFERENCE = "COMMODITY_MACRO_REFERENCE"
    EXTRACTION_NOISE = "EXTRACTION_NOISE"
    UNKNOWN = "UNKNOWN"


CATEGORIES = tuple(
    vars(Category)[name]
    for name in (
        "EXPLICIT_MARKET_SYMBOL",
        "SYMBOL_MISSING_MARKET",
        "EXISTING_ASSET_ALIAS_CANDIDATE",
        "CANONICAL_LOOKING_NAME_ONLY",
        "NICKNAME_ABBREVIATION",
        "CROSS_LISTING_AMBIGUITY",
        "UNSUPPORTED_MARKET_HINT",
        "INDEX_OR_ETF",
        "CONCEPT_INDUSTRY_NON_SECURITY",
        "COMMODITY_MACRO_REFERENCE",
        "EXTRACTION_NOISE",
        "UNKNOWN",
    )
)
INDEX_TERMS = (
    "指数",
    "ETF",
    "沪深",
    "中证",
    "上证",
    "创业板",
    "科创板",
    "恒生指数",
    "标普",
    "纳斯达克",
    "MSCI",
    "KOSPI",
    "做多",
    "做空",
    "倍做",
    "杠杆",
)
CONCEPT_TERMS = (
    "行业",
    "板块",
    "煤炭股",
    "焦煤股",
    "煤炭",
    "光伏",
    "地产",
    "银行指数",
    "保险",
    "白酒",
    "有色",
    "消费股",
    "新能源发电",
    "磷化工",
    "面板",
    "软体股",
    "低估值",
    "高分红",
    "质优股",
    "大盘",
)
COMMODITY_TERMS = (
    "煤价",
    "焦煤期货",
    "焦煤2609",
    "焦煤2609合约",
    "焦煤",
    "动力煤",
    "喷吹煤",
    "原油",
    "油运",
    "油运市场",
    "油运运价",
    "航运",
    "航运板块",
    "箱运",
    "干散",
    "VLCC",
    "白银",
    "铜金",
)
NOISE_TERMS = (
    "未具名",
    "正文未具名",
    "该标的",
    "这个标的",
    "那只",
    "这家",
    "两个我最担心",
    "其它",
    "其他",
    "公司业绩对应",
    "作者未指名",
)
NICKNAME_TERMS = ("海控", "海能", "山金", "紫金", "五矿", "招行", "老窖", "康臣", "lc")
CANONICAL_SUFFIXES = (
    "股份",
    "集团",
    "控股",
    "国际",
    "银行",
    "证券",
    "保险",
    "能源",
    "电力",
    "汽车",
    "医药",
    "矿业",
    "铝业",
    "化工",
    "水泥",
    "科技",
    "传媒",
    "黄金",
    "铜业",
    "焦煤",
)


def ident(value: Any) -> str:
    return str(value) if value is not None else ""


def enum_text(value: Any) -> str:
    return str(getattr(value, "value", value))


def as_hk(value: Any) -> datetime | None:
    if not isinstance(value, datetime):
        return None
    return (
        value.replace(tzinfo=HK)
        if value.tzinfo is None or value.utcoffset() is None
        else value.astimezone(HK)
    )


def fmt_dt(value: Any) -> str:
    value = as_hk(value)
    return value.isoformat(timespec="seconds") if value else "—"


def date_hk(value: Any) -> date | None:
    value = as_hk(value)
    return value.date() if value else None


def pct(numerator: int | float, denominator: int | float) -> str:
    return "—" if not denominator else f"{numerator / denominator:.1%}"


def md(value: Any) -> str:
    return (
        "—"
        if value is None or value == ""
        else str(value).replace("|", "\\|").replace("\n", " ").strip()
    )


def table(headers: Iterable[Any], rows: Iterable[Iterable[Any]]) -> str:
    heads = [md(value) for value in headers]
    body = [[md(value) for value in row] for row in rows]
    lines = ["| " + " | ".join(heads) + " |", "| " + " | ".join("---" for _ in heads) + " |"]
    lines.extend("| " + " | ".join(row) + " |" for row in body)
    return "\n".join(lines)


def name_key(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def market_key(value: str | None) -> str | None:
    value = (value or "").strip().upper()
    return value or None


def symbol_key(value: str | None) -> str | None:
    value = (value or "").strip().upper()
    return value or None


def id_int(value: Any) -> int:
    try:
        return int(ident(value).replace("-", ""), 16)
    except ValueError:
        return 0


def analysis_key(row: Row) -> tuple[datetime, int]:
    return as_hk(row.get("calculated_at")) or datetime.min.replace(tzinfo=HK), id_int(row.get("id"))


def connect_read_only() -> tuple[psycopg.Connection[Any], URL]:
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError(
            f"Asset Resolution Audit v2 requires PostgreSQL, got {url.get_backend_name()}"
        )
    connection = psycopg.connect(
        host=url.host, port=url.port, dbname=url.database, user=url.username, password=url.password
    )
    with connection.cursor() as cursor:
        cursor.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
        cursor.execute("SET LOCAL TIME ZONE 'Asia/Hong_Kong'")
        cursor.execute("SET LOCAL statement_timeout = '60000'")
    return connection, url


def fetch(cursor: psycopg.Cursor[Any], statement: str, params: tuple[Any, ...] = ()) -> list[Row]:
    cursor.execute(statement, params)
    columns = [column.name for column in cursor.description or ()]
    return [dict(zip(columns, row, strict=True)) for row in cursor.fetchall()]


def scalar(cursor: psycopg.Cursor[Any], statement: str, params: tuple[Any, ...] = ()) -> Any:
    cursor.execute(statement, params)
    row = cursor.fetchone()
    return row[0] if row else None


class CatalogLookup:
    """Exact in-memory AssetLookup for the production AssetResolver."""

    def __init__(self, assets: list[Row], aliases: list[Row]) -> None:
        self.market_symbols: dict[tuple[str, str], set[UUID]] = defaultdict(set)
        self.aliases: dict[str, list[tuple[UUID, str | None]]] = defaultdict(list)
        for row in assets:
            market = market_key(row.get("market"))
            symbol = symbol_key(row.get("symbol"))
            if market and symbol:
                self.market_symbols[(market, symbol)].add(UUID(str(row["id"])))
        for row in aliases:
            alias = name_key(str(row.get("normalized_alias") or row.get("alias") or ""))
            if alias:
                self.aliases[alias].append(
                    (UUID(str(row["asset_id"])), market_key(row.get("market")))
                )

    def list_ids_by_market_symbol(self, market: str, symbol: str) -> Iterable[UUID]:
        return tuple(
            sorted(
                self.market_symbols.get(
                    (market_key(market) or "", symbol_key(symbol) or ""), set()
                ),
                key=lambda value: value.int,
            )
        )

    def list_ids_by_normalized_alias(
        self, normalized_alias: str, market: str | None = None
    ) -> Iterable[UUID]:
        wanted = market_key(market)
        values = {
            asset_id
            for asset_id, alias_market in self.aliases.get(name_key(normalized_alias), [])
            if (wanted is None and alias_market is None)
            or (wanted is not None and alias_market in {None, wanted})
        }
        return tuple(sorted(values, key=lambda value: value.int))


@dataclass(frozen=True)
class Occurrence:
    name: str
    symbol: str | None
    market: str | None
    investor_id: str
    event_id: str
    published_time: datetime
    status: str
    direction: str | None
    strength: float | None
    confidence: float | None
    other_opinion: bool
    stored_candidates: tuple[str, ...]
    stored_reason: str | None
    resolver_status: str
    resolver_reason: str | None
    matched_by: str | None
    resolver_asset_id: str | None
    normalized_symbol: str | None
    normalized_market: str | None
    category: str

    @property
    def complete(self) -> bool:
        return (
            self.direction is not None and self.strength is not None and self.confidence is not None
        )


@dataclass(frozen=True)
class Aggregate:
    key: tuple[str, str | None, str | None]
    rows: tuple[Occurrence, ...]

    @property
    def name(self) -> str:
        return self.rows[0].name

    @property
    def symbol(self) -> str | None:
        return self.rows[0].symbol

    @property
    def market(self) -> str | None:
        return self.rows[0].market

    @property
    def category(self) -> str:
        return self.rows[0].category

    @property
    def occurrence_count(self) -> int:
        return len(self.rows)

    @property
    def events(self) -> set[str]:
        return {row.event_id for row in self.rows}

    @property
    def investors(self) -> set[str]:
        return {row.investor_id for row in self.rows}

    @property
    def dates(self) -> set[date]:
        return {value for row in self.rows if (value := date_hk(row.published_time)) is not None}

    @property
    def repeated_cross_day(self) -> bool:
        return len(self.rows) >= 2 and len(self.dates) >= 2

    @property
    def multi_investor(self) -> bool:
        return len(self.investors) >= 2

    @property
    def resolver_asset_ids(self) -> set[str]:
        return {row.resolver_asset_id for row in self.rows if row.resolver_asset_id}

    @property
    def existing_target(self) -> str | None:
        return next(iter(self.resolver_asset_ids)) if len(self.resolver_asset_ids) == 1 else None

    @property
    def normalized_identity(self) -> tuple[str | None, str | None]:
        return self.rows[0].normalized_market, self.rows[0].normalized_symbol

    @property
    def proposed_identity(self) -> str | None:
        market, symbol = self.normalized_identity
        return f"{market}:{symbol}" if market and symbol else None

    @property
    def safe_new_identity(self) -> bool:
        return (
            self.existing_target is None
            and not self.resolver_asset_ids
            and not any(row.stored_candidates for row in self.rows)
            and self.proposed_identity is not None
            and self.category in {Category.EXPLICIT_MARKET_SYMBOL, Category.SYMBOL_MISSING_MARKET}
        )

    @property
    def target_key(self) -> str | None:
        if self.existing_target:
            return f"existing:{self.existing_target}"
        if self.safe_new_identity:
            return f"new:{self.proposed_identity}"
        return None


@dataclass(frozen=True)
class Impact:
    mode: str
    target_key: str | None
    label: str
    new_opinions: int | None
    new_pairs: int | None
    new_attention: int | None
    new_repeated_pairs: int | None
    delta_2_attention: int | None
    delta_3_attention: int | None
    delta_2_opinion: int | None
    delta_3_opinion: int | None
    note: str

    @property
    def score(self) -> int:
        return (
            (self.delta_3_opinion or 0) * 1000
            + (self.delta_3_attention or 0) * 500
            + (self.new_repeated_pairs or 0) * 100
            + (self.new_opinions or 0) * 10
            + (self.new_attention or 0)
        )


def classify(
    item: UnresolvedAsset,
    resolver_status: str,
    resolver_asset_id: str | None,
    stored_candidates: tuple[str, ...],
) -> str:
    name = item.asset_name.strip()
    market = item.market.strip() if item.market else None
    symbol = item.symbol.strip() if item.symbol else None
    if market and normalize_market_hint(market) is None:
        return Category.UNSUPPORTED_MARKET_HINT
    if len(stored_candidates) >= 2 or resolver_status == AssetResolutionStatus.AMBIGUOUS.value:
        return Category.CROSS_LISTING_AMBIGUITY
    if resolver_status == AssetResolutionStatus.RESOLVED.value or resolver_asset_id:
        return Category.EXISTING_ASSET_ALIAS_CANDIDATE
    if len(stored_candidates) == 1:
        return Category.EXISTING_ASSET_ALIAS_CANDIDATE
    lowered = name.casefold()
    if any(term.casefold() in lowered for term in INDEX_TERMS):
        return Category.INDEX_OR_ETF
    if market and symbol:
        return Category.EXPLICIT_MARKET_SYMBOL
    if symbol:
        return Category.SYMBOL_MISSING_MARKET
    if any(term.casefold() in lowered for term in CONCEPT_TERMS):
        return Category.CONCEPT_INDUSTRY_NON_SECURITY
    if any(term.casefold() in lowered for term in COMMODITY_TERMS):
        return Category.COMMODITY_MACRO_REFERENCE
    if any(term.casefold() in lowered for term in NOISE_TERMS):
        return Category.EXTRACTION_NOISE
    if lowered in {term.casefold() for term in NICKNAME_TERMS}:
        return Category.NICKNAME_ABBREVIATION
    if name.endswith(CANONICAL_SUFFIXES):
        return Category.CANONICAL_LOOKING_NAME_ONLY
    return Category.UNKNOWN


def load_occurrences(
    analyses: list[Row],
    raw_events: dict[str, Row],
    effective_opinions_by_event: dict[str, list[Row]],
    resolver: AssetResolver,
) -> tuple[list[Occurrence], int]:
    occurrences: list[Occurrence] = []
    parse_failures = 0
    for analysis in analyses:
        event_id = ident(analysis.get("event_id"))
        event = raw_events.get(event_id)
        if event is None:
            continue
        output = (
            analysis.get("structured_output")
            if isinstance(analysis.get("structured_output"), dict)
            else {}
        )
        values = output.get("unresolved_assets", [])
        if not isinstance(values, list):
            continue
        for value in values:
            try:
                item = UnresolvedAsset.model_validate(value)
            except Exception:
                parse_failures += 1
                continue
            reference = AssetReference(
                name_hint=item.asset_name, symbol_hint=item.symbol, market_hint=item.market
            )
            resolution = resolver.resolve(reference)
            stored_candidates = tuple(str(candidate) for candidate in item.candidate_asset_ids)
            resolver_asset_id = str(resolution.asset_id) if resolution.asset_id else None
            occurrences.append(
                Occurrence(
                    name=item.asset_name,
                    symbol=item.symbol,
                    market=item.market,
                    investor_id=ident(event.get("investor_id")),
                    event_id=event_id,
                    published_time=as_hk(event.get("published_time"))
                    or datetime.min.replace(tzinfo=HK),
                    status=enum_text(analysis.get("status")),
                    direction=enum_text(item.direction) if item.direction is not None else None,
                    strength=item.strength,
                    confidence=item.confidence,
                    other_opinion=bool(effective_opinions_by_event.get(event_id)),
                    stored_candidates=stored_candidates,
                    stored_reason=item.reason,
                    resolver_status=resolution.status.value,
                    resolver_reason=resolution.reason,
                    matched_by=resolution.matched_by,
                    resolver_asset_id=resolver_asset_id,
                    normalized_symbol=resolution.normalized_symbol,
                    normalized_market=resolution.normalized_market,
                    category=classify(
                        item, resolution.status.value, resolver_asset_id, stored_candidates
                    ),
                )
            )
    return occurrences, parse_failures


def aggregate_occurrences(occurrences: list[Occurrence]) -> list[Aggregate]:
    grouped: dict[tuple[str, str | None, str | None], list[Occurrence]] = defaultdict(list)
    for occurrence in occurrences:
        grouped[
            (
                name_key(occurrence.name),
                symbol_key(occurrence.symbol),
                market_key(occurrence.market),
            )
        ].append(occurrence)
    return [
        Aggregate(
            key=key,
            rows=tuple(sorted(values, key=lambda value: (value.published_time, value.event_id))),
        )
        for key, values in grouped.items()
    ]


def target_label(target_key: str, assets_by_id: dict[str, Row], aggregate: Aggregate) -> str:
    if target_key.startswith("existing:"):
        asset = assets_by_id.get(target_key.removeprefix("existing:"))
        if asset:
            return f"{asset.get('name')} ({asset.get('market')}:{asset.get('symbol')})"
    return f"{aggregate.name} ({aggregate.proposed_identity or 'identity unknown'}) [proposed]"


def target_occurrences(aggregates: list[Aggregate], target_key: str) -> list[Occurrence]:
    result: list[Occurrence] = []
    for aggregate in aggregates:
        if aggregate.target_key != target_key:
            continue
        if target_key.startswith("existing:"):
            asset_id = target_key.removeprefix("existing:")
            result.extend(
                row for row in aggregate.rows if row.resolver_asset_id == asset_id and row.complete
            )
        else:
            result.extend(row for row in aggregate.rows if row.complete)
    return result


def unknown_impact(target_key: str | None, label: str, note: str) -> Impact:
    return Impact(
        "UNKNOWN", target_key, label, None, None, None, None, None, None, None, None, note
    )


def impact_for_target(
    aggregates: list[Aggregate],
    target_key: str | None,
    assets_by_id: dict[str, Row],
    current_opinions_by_asset: dict[str, set[str]],
    current_attention_by_asset: dict[str, set[str]],
    opinion_pair_counts: Counter[tuple[str, str]],
    opinion_event_assets: set[tuple[str, str]],
    attention_event_assets: set[tuple[str, str]],
) -> Impact:
    aggregate = next((value for value in aggregates if value.target_key == target_key), None)
    if aggregate is None or target_key is None:
        return unknown_impact(
            target_key, "unknown identity", "No deterministic single Asset identity is available."
        )
    candidates = target_occurrences(aggregates, target_key)
    if not candidates:
        return unknown_impact(
            target_key,
            target_label(target_key, assets_by_id, aggregate),
            "Identity is deterministic but stored semantics are incomplete; no Opinion can be projected.",
        )
    existing_asset_id = (
        target_key.removeprefix("existing:") if target_key.startswith("existing:") else None
    )
    event_target = {(row.event_id, existing_asset_id or target_key) for row in candidates}
    investor_target = {(row.investor_id, existing_asset_id or target_key) for row in candidates}
    current_pair_keys = set(opinion_pair_counts)
    new_opinions = sum(
        (event_id, target) not in opinion_event_assets for event_id, target in event_target
    )
    new_pairs = sum(
        (investor_id, target) not in current_pair_keys for investor_id, target in investor_target
    )
    new_attention = sum(
        (event_id, target) not in attention_event_assets for event_id, target in event_target
    )
    after_pairs = Counter(opinion_pair_counts)
    for investor_id, _target in investor_target:
        count = sum(
            row.investor_id == investor_id and (existing_asset_id or target_key) == target_key
            for row in candidates
        )
        if existing_asset_id:
            count = sum(row.investor_id == investor_id for row in candidates)
        after_pairs[(investor_id, existing_asset_id or target_key)] += count
    new_repeated = sum(
        count >= 2 and opinion_pair_counts.get(pair, 0) < 2 for pair, count in after_pairs.items()
    )
    before_attention = (
        set(current_attention_by_asset.get(existing_asset_id, set()))
        if existing_asset_id
        else set()
    )
    before_opinion = (
        set(current_opinions_by_asset.get(existing_asset_id, set())) if existing_asset_id else set()
    )
    after_attention = before_attention | {row.investor_id for row in candidates}
    after_opinion = before_opinion | {row.investor_id for row in candidates}
    return Impact(
        "EXACT_EXISTING_ASSET" if existing_asset_id else "SIMULATED_SAFE_SEED",
        target_key,
        target_label(target_key, assets_by_id, aggregate),
        new_opinions,
        new_pairs,
        new_attention,
        new_repeated,
        int(len(before_attention) < 2 <= len(after_attention)),
        int(len(before_attention) < 3 <= len(after_attention)),
        int(len(before_opinion) < 2 <= len(after_opinion)),
        int(len(before_opinion) < 3 <= len(after_opinion)),
        "Existing canonical/alias identity is exact."
        if existing_asset_id
        else "Unique normalized market+symbol identity; safe-seed simulation only.",
    )


def tier_for(aggregate: Aggregate, impact: Impact, near_shared: bool) -> str:
    high = (
        aggregate.multi_investor
        or aggregate.repeated_cross_day
        or near_shared
        or bool(impact.delta_3_opinion)
        or bool(impact.delta_3_attention)
    )
    if impact.mode in {"EXACT_EXISTING_ASSET", "SIMULATED_SAFE_SEED"}:
        return "A" if high else "B"
    if aggregate.category in {
        Category.INDEX_OR_ETF,
        Category.CONCEPT_INDUSTRY_NON_SECURITY,
        Category.COMMODITY_MACRO_REFERENCE,
        Category.EXTRACTION_NOISE,
    }:
        return "D"
    if aggregate.category == Category.UNKNOWN:
        return "E"
    return "C"


def priority_score(aggregate: Aggregate, impact: Impact, near_shared: bool) -> int:
    return (
        (1000 if impact.delta_3_opinion else 0)
        + (500 if impact.delta_3_attention else 0)
        + (250 if aggregate.multi_investor else 0)
        + (150 if aggregate.repeated_cross_day else 0)
        + (100 if near_shared else 0)
        + impact.score
        + aggregate.occurrence_count
    )


def render_references(aggregates: list[Aggregate], investor_names: dict[str, str]) -> str:
    rows = []
    for aggregate in sorted(
        aggregates,
        key=lambda value: (-len(value.rows), value.name, value.symbol or "", value.market or ""),
    ):
        statuses = Counter(row.status for row in aggregate.rows)
        directions = Counter(row.direction for row in aggregate.rows if row.direction)
        other = sum(row.other_opinion for row in aggregate.rows)
        rows.append(
            (
                aggregate.name,
                aggregate.market,
                aggregate.symbol,
                len(aggregate.rows),
                len(aggregate.events),
                len(aggregate.investors),
                len(aggregate.dates),
                fmt_dt(min(row.published_time for row in aggregate.rows)),
                fmt_dt(max(row.published_time for row in aggregate.rows)),
                ", ".join(
                    sorted(investor_names.get(value, value) for value in aggregate.investors)
                ),
                "; ".join(f"{key}={value}" for key, value in sorted(statuses.items())),
                "; ".join(f"{key}={value}" for key, value in sorted(directions.items())) or "—",
                f"yes {other}/{len(aggregate.rows)}" if other else "no",
                aggregate.category,
                "; ".join(sorted({row.resolver_status for row in aggregate.rows})),
                "; ".join(
                    sorted({row.stored_reason for row in aggregate.rows if row.stored_reason})
                )
                or "—",
            )
        )
    return table(
        (
            "Reference name",
            "Market hint",
            "Symbol hint",
            "Occurrences",
            "RawEvents",
            "Investors",
            "Active days",
            "Earliest",
            "Latest",
            "Source Investors",
            "Analysis status",
            "Directions",
            "Other resolved Opinion",
            "Taxonomy",
            "Resolver status",
            "Stored reason",
        ),
        rows,
    )


def render_candidates(
    rows: list[tuple[Aggregate, Impact, str, int, bool]], investor_names: dict[str, str]
) -> str:
    values = []
    for aggregate, impact, tier, score, near_shared in rows:
        identity_reason = (
            f"one exact existing Asset: {impact.label}"
            if impact.mode == "EXACT_EXISTING_ASSET"
            else f"one normalized market+symbol absent from catalog: {aggregate.proposed_identity}"
            if impact.mode == "SIMULATED_SAFE_SEED"
            else "not uniquely established"
        )
        values.append(
            (
                tier,
                score,
                aggregate.name,
                aggregate.market,
                aggregate.symbol,
                aggregate.category,
                impact.label,
                identity_reason,
                len(aggregate.rows),
                len(aggregate.events),
                ", ".join(
                    sorted(investor_names.get(value, value) for value in aggregate.investors)
                ),
                len(aggregate.dates),
                "yes" if aggregate.multi_investor else "no",
                "yes" if aggregate.repeated_cross_day else "no",
                "yes" if near_shared else "no",
                impact.mode,
                impact.new_opinions,
                impact.new_pairs,
                impact.new_attention,
                impact.new_repeated_pairs,
                impact.delta_2_attention,
                impact.delta_3_attention,
                impact.delta_2_opinion,
                impact.delta_3_opinion,
                impact.note,
            )
        )
    return table(
        (
            "Tier",
            "Priority",
            "Reference",
            "Market",
            "Symbol",
            "Taxonomy",
            "Proposed/target canonical identity",
            "Why identity is unique",
            "Occurrences",
            "RawEvents",
            "Affected Investors",
            "Active days",
            "Multi-Investor",
            "Repeated cross-day",
            "Near shared Asset",
            "Impact mode",
            "New Opinions",
            "New Investor×Asset pairs",
            "New Attention",
            "New repeated Opinion pairs",
            "Δ 2+ Attention",
            "Δ 3+ Attention",
            "Δ 2+ Opinion",
            "Δ 3+ Opinion",
            "Impact note",
        ),
        values,
    )


def render_overlap(
    aggregates: list[Aggregate],
    impacts: dict[str, Impact],
    assets_by_id: dict[str, Row],
    investor_names: dict[str, str],
    attention_by_asset: dict[str, set[str]],
    opinions_by_asset: dict[str, set[str]],
) -> str:
    rows = []
    for aggregate in aggregates:
        asset_id = aggregate.existing_target
        if not asset_id or len(attention_by_asset.get(asset_id, set())) < 2:
            continue
        complete = [
            row for row in aggregate.rows if row.resolver_asset_id == asset_id and row.complete
        ]
        if not complete:
            continue
        attention_investors = attention_by_asset[asset_id]
        opinion_investors = opinions_by_asset.get(asset_id, set())
        candidate_investors = {row.investor_id for row in complete}
        missing_opinion = candidate_investors & attention_investors - opinion_investors
        new_attention = candidate_investors - attention_investors
        asset = assets_by_id.get(asset_id, {})
        impact = impacts.get(aggregate.target_key or "")
        rows.append(
            (
                f"{asset.get('name')} ({asset.get('market')}:{asset.get('symbol')})",
                len(attention_investors),
                ", ".join(
                    sorted(investor_names.get(value, value) for value in attention_investors)
                ),
                len(opinion_investors),
                ", ".join(sorted(investor_names.get(value, value) for value in opinion_investors))
                or "—",
                aggregate.name,
                len(aggregate.rows),
                ", ".join(
                    sorted(investor_names.get(value, value) for value in candidate_investors)
                ),
                ", ".join(sorted(investor_names.get(value, value) for value in missing_opinion))
                or "—",
                ", ".join(sorted(investor_names.get(value, value) for value in new_attention))
                or "—",
                impact.new_opinions if impact else "UNKNOWN",
                impact.delta_3_opinion if impact else "UNKNOWN",
            )
        )
    if not rows:
        return "No unresolved reference was deterministically mapped to an existing 2+ Attention Asset with complete Opinion semantics."
    return table(
        (
            "Current shared Asset",
            "Attention Investors",
            "Attention Investor names",
            "Opinion Investors",
            "Opinion Investor names",
            "Unresolved reference",
            "Occurrences",
            "Candidate Investors",
            "Missing Opinion among current Attention",
            "New Attention Investors",
            "New Opinions",
            "Δ 3+ Opinion Assets",
        ),
        rows,
    )


def render_fragmentation(
    aggregates: list[Aggregate], aliases: list[Row], assets_by_id: dict[str, Row]
) -> str:
    by_identity: dict[tuple[str, str], set[str]] = defaultdict(set)
    by_name: dict[str, set[tuple[str | None, str | None]]] = defaultdict(set)
    for aggregate in aggregates:
        market, symbol = aggregate.normalized_identity
        if market and symbol:
            by_identity[(market, symbol)].add(aggregate.name)
        by_name[name_key(aggregate.name)].add((aggregate.market, aggregate.symbol))
    rows = []
    for (market, symbol), names in sorted(by_identity.items()):
        if len(names) >= 2:
            rows.append(
                (
                    "same explicit market+symbol",
                    f"{market}:{symbol}",
                    "; ".join(sorted(names)),
                    "candidate name variants; do not merge",
                )
            )
    for key, identities in sorted(by_name.items()):
        if len(identities) >= 2:
            rows.append(
                (
                    "same normalized name, different hints",
                    key,
                    "; ".join(
                        f"{market or '-'}:{symbol or '-'}"
                        for market, symbol in sorted(identities, key=str)
                    ),
                    "possible cross-listing/conflicting hints; review only",
                )
            )
    alias_targets: dict[str, set[str]] = defaultdict(set)
    for alias in aliases:
        alias_targets[name_key(str(alias.get("normalized_alias") or alias.get("alias") or ""))].add(
            ident(alias.get("asset_id"))
        )
    for key, asset_ids in sorted(alias_targets.items()):
        if len(asset_ids) >= 2:
            members = []
            for asset_id in sorted(asset_ids):
                asset = assets_by_id.get(asset_id, {})
                members.append(
                    f"{asset.get('name', asset_id)} ({asset.get('market', '-')}:{asset.get('symbol', '-')})"
                )
            rows.append(
                (
                    "existing Alias maps to multiple Assets",
                    key,
                    "; ".join(members),
                    "catalog ambiguity; do not merge",
                )
            )
    if not rows:
        return "No deterministic fragmentation relation found. Fuzzy name similarity, suffix/prefix resemblance and A/H naming were not used."
    return table(("Relation", "Identity/key", "Candidate members", "Boundary"), rows)


def build_report(data: dict[str, Any], database_name: str, audit_time: datetime) -> str:
    investors = data["investors"]
    assets_by_id = data["assets"]
    aliases = data["aliases"]
    raw_by_id = data["raw_events"]
    all_analyses = data["analyses"]
    all_opinions = data["opinions"]
    all_attention = data["attention"]
    failures = data["failures"]
    analysis_version = data["analysis_version"]
    attention_version = data["attention_version"]
    investor_names = {key: str(value.get("name") or key) for key, value in investors.items()}

    current_analysis: dict[str, Row] = {}
    for row in all_analyses:
        event_id = ident(row.get("event_id"))
        previous = current_analysis.get(event_id)
        if previous is None or analysis_key(row) > analysis_key(previous):
            current_analysis[event_id] = row
    effective_analysis_ids = {
        ident(row.get("id"))
        for row in current_analysis.values()
        if enum_text(row.get("status")) in {"SUCCESS", "PARTIALLY_RESOLVED"}
    }
    effective_opinions = [
        row for row in all_opinions if ident(row.get("analysis_id")) in effective_analysis_ids
    ]
    opinions_by_event: dict[str, list[Row]] = defaultdict(list)
    opinion_pair_counts: Counter[tuple[str, str]] = Counter()
    opinions_by_asset: dict[str, set[str]] = defaultdict(set)
    opinion_event_assets: set[tuple[str, str]] = set()
    for row in effective_opinions:
        event_id, investor_id, asset_id = (
            ident(row.get("event_id")),
            ident(row.get("investor_id")),
            ident(row.get("asset_id")),
        )
        opinions_by_event[event_id].append(row)
        opinion_pair_counts[(investor_id, asset_id)] += 1
        opinions_by_asset[asset_id].add(investor_id)
        opinion_event_assets.add((event_id, asset_id))
    effective_attention = [
        row
        for row in all_attention
        if row.get("attention_policy_version") == attention_version
        and (
            row.get("analysis_id") is None
            or ident(row.get("analysis_id")) in effective_analysis_ids
        )
    ]
    attention_by_asset: dict[str, set[str]] = defaultdict(set)
    attention_event_assets: set[tuple[str, str]] = set()
    for row in effective_attention:
        asset_id = ident(row.get("asset_id"))
        attention_by_asset[asset_id].add(ident(row.get("investor_id")))
        attention_event_assets.add((ident(row.get("event_id")), asset_id))

    occurrences, parse_failures = load_occurrences(
        list(current_analysis.values()),
        raw_by_id,
        opinions_by_event,
        AssetResolver(data["lookup"]),
    )
    aggregates = aggregate_occurrences(occurrences)
    shared_attention_assets = {
        asset_id for asset_id, values in attention_by_asset.items() if len(values) >= 2
    }
    shared_attention_3_assets = {
        asset_id for asset_id, values in attention_by_asset.items() if len(values) >= 3
    }
    shared_opinion_assets = {
        asset_id for asset_id, values in opinions_by_asset.items() if len(values) >= 2
    }
    shared_opinion_3_assets = {
        asset_id for asset_id, values in opinions_by_asset.items() if len(values) >= 3
    }
    near_shared: dict[tuple[str, str | None, str | None], bool] = {}
    for aggregate in aggregates:
        near_shared[aggregate.key] = any(
            any(
                len(attention_by_asset.get(ident(opinion.get("asset_id")), set())) >= 2
                for opinion in opinions_by_event.get(row.event_id, [])
            )
            for row in aggregate.rows
        )

    impacts: dict[str, Impact] = {}
    for target_key in sorted(
        {aggregate.target_key for aggregate in aggregates if aggregate.target_key}
    ):
        impacts[target_key] = impact_for_target(
            aggregates,
            target_key,
            assets_by_id,
            opinions_by_asset,
            attention_by_asset,
            opinion_pair_counts,
            opinion_event_assets,
            attention_event_assets,
        )
    candidate_rows: list[tuple[Aggregate, Impact, str, int, bool]] = []
    for aggregate in aggregates:
        impact = impacts.get(
            aggregate.target_key or "",
            unknown_impact(
                None, "unknown identity", "No deterministic single Asset identity is available."
            ),
        )
        near = near_shared.get(aggregate.key, False)
        tier = tier_for(aggregate, impact, near)
        candidate_rows.append(
            (aggregate, impact, tier, priority_score(aggregate, impact, near), near)
        )
    candidate_rows.sort(
        key=lambda value: (-value[3], value[0].name, value[0].symbol or "", value[0].market or "")
    )

    category_occurrences = Counter(row.category for row in occurrences)
    category_references = Counter(aggregate.category for aggregate in aggregates)
    non_security_categories = {
        Category.INDEX_OR_ETF,
        Category.CONCEPT_INDUSTRY_NON_SECURITY,
        Category.COMMODITY_MACRO_REFERENCE,
        Category.EXTRACTION_NOISE,
    }
    non_security_occurrences = sum(
        category_occurrences.get(category, 0) for category in non_security_categories
    )
    unknown_occurrences = category_occurrences.get(Category.UNKNOWN, 0)
    tier_a_b_occurrences = sum(
        aggregate.rows.__len__()
        for aggregate, _impact, tier, _score_value, _near in candidate_rows
        if tier in {"A", "B"}
    )

    report: list[str] = [
        "# Asset Resolution Audit v2 Report",
        "",
        f"Audit time: **{fmt_dt(audit_time)}**; database: **{database_name}**; backend: **PostgreSQL**; transaction: **REPEATABLE READ + READ ONLY**; dates use **Asia/Hong_Kong**.",
        "",
        "## 1. Preflight",
        "",
        f"Current production Analysis identity: `{analysis_version}`. Investors: **{len(investors)}**; RawEvents: **{len(raw_by_id)}**; Canonical Assets: **{len(assets_by_id)}**; AssetAlias rows: **{len(aliases)}**.",
        "",
        "No collection, Opinion LLM, Intelligence rebuild, Asset Master write, migration, commit, or push was performed. Existing git changes were preserved.",
        "",
        "## 2. Unresolved Reference Inventory",
        "",
        f"Current active unresolved occurrences: **{len(occurrences):,}**; distinct reference identities: **{len(aggregates):,}**; distinct unresolved names: **{len({name_key(value.name) for value in aggregates}):,}**; structured parse failures: **{parse_failures}**.",
        "",
        "Each row is a distinct normalized `(reference name, symbol hint, market hint)` identity. Status, direction and other-resolved-Opinion fields come from current database evidence.",
        "",
        render_references(aggregates, investor_names),
        "",
        "## 3. Deterministic Taxonomy",
        "",
        "Classification is conservative and audit-only. Precedence is unsupported market, existing/ambiguous deterministic identity, explicit market+symbol, symbol-only, index/ETF, concept/industry, commodity/macro, extraction noise, nickname, canonical-looking name, then UNKNOWN.",
        "",
        table(
            ("Taxonomy", "Occurrences", "Share", "Distinct references"),
            (
                (
                    category,
                    category_occurrences.get(category, 0),
                    pct(category_occurrences.get(category, 0), len(occurrences)),
                    category_references.get(category, 0),
                )
                for category in CATEGORIES
            ),
        ),
        "",
        "No category is an automatic resolution decision. Unsupported markets, cross-listing ambiguity and UNKNOWN remain review queues.",
        "",
        "## 4. Intelligence-Value Prioritization",
        "",
        "Priority uses multi-Investor evidence, repeated cross-day evidence, exact proximity to current shared Assets and potential 3+ transitions before occurrence frequency. `Near shared Asset` means the same RawEvent has an effective Opinion on a current 2+ Attention-Investor Asset.",
        "",
        table(
            ("Signal", "Count", "Definition"),
            (
                (
                    "Multi-Investor unresolved references",
                    sum(value.multi_investor for value in aggregates),
                    "distinct Investors >=2",
                ),
                (
                    "Repeated cross-day unresolved references",
                    sum(value.repeated_cross_day for value in aggregates),
                    "occurrences >=2 and active days >=2",
                ),
                (
                    "Near shared Asset",
                    sum(near_shared.get(value.key, False) for value in aggregates),
                    "same RawEvent has another Opinion on a shared Asset",
                ),
                (
                    "Potential deterministic 3+ Opinion overlap",
                    sum(bool(value.delta_3_opinion) for value in impacts.values()),
                    "safe simulation crosses current 2 Opinion-Investor boundary",
                ),
                (
                    "Single-Investor high-frequency",
                    sum(
                        value.occurrence_count >= 3 and not value.multi_investor
                        for value in aggregates
                    ),
                    "occurrences >=3 and one Investor",
                ),
                (
                    "Non-security/noise",
                    non_security_occurrences,
                    "index/ETF + concept/industry + commodity/macro + extraction noise",
                ),
                ("UNKNOWN", unknown_occurrences, "no conservative deterministic category"),
            ),
        ),
        "",
        f"Audit-qualified Tier A/B occurrences: **{tier_a_b_occurrences:,} / {len(occurrences):,} ({pct(tier_a_b_occurrences, len(occurrences))})**. This is a review queue, not a seed command.",
        "",
        "## 5. Dry-run Resolution Impact",
        "",
        "Existing canonical/alias targets are `EXACT_EXISTING_ASSET`; unique explicit market+symbol identities absent from the catalog are `SIMULATED_SAFE_SEED`; other candidates are `UNKNOWN`. Counts are in-memory only and not additive across references sharing one target.",
        "",
        render_candidates(candidate_rows[:100], investor_names),
        "",
        "## 6. Existing Asset Fragmentation Audit",
        "",
        "Only exact deterministic relationships are reported. No fuzzy name similarity, suffix/prefix resemblance or A/H naming is used to merge Assets.",
        "",
        render_fragmentation(aggregates, aliases, assets_by_id),
        "",
        "## 7. High-value Candidate Report",
        "",
    ]
    for tier, description, limit in (
        ("A", "safe deterministic identity and high Intelligence impact", None),
        ("B", "safe deterministic identity and lower direct impact", None),
        ("C", "identity may be correct but evidence is insufficient/ambiguous", 80),
        ("D", "index/ETF, concept/industry, commodity/macro or extraction noise", 80),
        ("E", "UNKNOWN identity", 80),
    ):
        tier_rows = [row for row in candidate_rows if row[2] == tier]
        report.extend(
            [
                f"### Tier {tier} — {description}",
                "",
                f"Candidates: **{len(tier_rows)}**; occurrences: **{sum(len(row[0].rows) for row in tier_rows):,}**.",
                "",
            ]
        )
        report.append(
            render_candidates(tier_rows if limit is None else tier_rows[:limit], investor_names)
            if tier_rows
            else "None."
        )
        if limit is not None and len(tier_rows) > limit:
            report.append(
                f"Only the top {limit} are shown here; the complete {len(aggregates)}-row inventory is in Section 2."
            )
        report.append("")

    report.extend(
        [
            "## 8. Special Cross-Investor Audit",
            "",
            table(
                ("Current evidence", "Asset count"),
                (
                    ("2+ Attention Investor Assets", len(shared_attention_assets)),
                    ("3+ Attention Investor Assets", len(shared_attention_3_assets)),
                    ("2+ Opinion Investor Assets", len(shared_opinion_assets)),
                    ("3+ Opinion Investor Assets", len(shared_opinion_3_assets)),
                ),
            ),
            "",
            "Deterministic unresolved references that may complete an existing 2+ Attention Asset:",
            "",
            render_overlap(
                aggregates,
                impacts,
                assets_by_id,
                investor_names,
                attention_by_asset,
                opinions_by_asset,
            ),
            "",
            "Focus Assets — 招商轮船, 紫金矿业, 盐湖股份, 龙源电力 — were checked by exact existing identity only; no fuzzy candidate was promoted.",
            "",
            "## 9. Multi-Investor Unresolved References",
            "",
        ]
    )
    multi = [value for value in aggregates if value.multi_investor]
    if multi:
        report.append(
            table(
                (
                    "Reference",
                    "Taxonomy",
                    "Occurrences",
                    "RawEvents",
                    "Investors",
                    "Investor names",
                    "Active days",
                    "Earliest",
                    "Latest",
                ),
                (
                    (
                        value.name,
                        value.category,
                        len(value.rows),
                        len(value.events),
                        len(value.investors),
                        ", ".join(
                            sorted(investor_names.get(item, item) for item in value.investors)
                        ),
                        len(value.dates),
                        fmt_dt(min(row.published_time for row in value.rows)),
                        fmt_dt(max(row.published_time for row in value.rows)),
                    )
                    for value in sorted(
                        multi, key=lambda item: (-len(item.investors), -len(item.rows), item.name)
                    )
                ),
            )
        )
    else:
        report.append("None.")
    report.extend(["", "## 10. Cross-day Unresolved References", ""])
    cross_day = [value for value in aggregates if value.repeated_cross_day]
    if cross_day:
        report.append(
            table(
                (
                    "Reference",
                    "Taxonomy",
                    "Occurrences",
                    "Investors",
                    "Active days",
                    "Earliest",
                    "Latest",
                    "Source Investors",
                ),
                (
                    (
                        value.name,
                        value.category,
                        len(value.rows),
                        len(value.investors),
                        len(value.dates),
                        fmt_dt(min(row.published_time for row in value.rows)),
                        fmt_dt(max(row.published_time for row in value.rows)),
                        ", ".join(
                            sorted(investor_names.get(item, item) for item in value.investors)
                        ),
                    )
                    for value in sorted(
                        cross_day, key=lambda item: (-len(item.dates), -len(item.rows), item.name)
                    )
                ),
            )
        )
    else:
        report.append("None.")
    report.extend(["", "## 11. Non-security / Noise and UNKNOWN Proportion", ""])
    report.append(
        table(
            ("Bucket", "Occurrences", "Share", "References"),
            (
                (
                    "Non-security/noise",
                    non_security_occurrences,
                    pct(non_security_occurrences, len(occurrences)),
                    sum(
                        category_references.get(category, 0) for category in non_security_categories
                    ),
                ),
                (
                    "UNKNOWN",
                    unknown_occurrences,
                    pct(unknown_occurrences, len(occurrences)),
                    category_references.get(Category.UNKNOWN, 0),
                ),
                (
                    "Other review/resolution candidates",
                    len(occurrences) - non_security_occurrences - unknown_occurrences,
                    pct(
                        len(occurrences) - non_security_occurrences - unknown_occurrences,
                        len(occurrences),
                    ),
                    len(aggregates)
                    - sum(
                        category_references.get(category, 0) for category in non_security_categories
                    )
                    - category_references.get(Category.UNKNOWN, 0),
                ),
            ),
        )
    )
    report.extend(
        [
            "",
            "These are taxonomy proportions, not claims about economic meaning. No unresolved identity was auto-bound.",
        ]
    )
    report.extend(["", "## 12. Remaining FAILED Analysis", ""])
    report.append(
        table(
            ("Investor", "RawEvent id", "published_time", "Status", "Sanitized failure category"),
            (
                (
                    item["investor_name"],
                    item["event_id"],
                    fmt_dt(item["published_time"]),
                    "FAILED",
                    item["category"],
                )
                for item in failures
            ),
        )
        if failures
        else "None."
    )
    report.extend(
        [
            "",
            "No retry was performed for the remaining FAILED Analysis.",
            "",
            "## 13. Recommended Next Seed Asset/Alias Manifest",
            "",
        ]
    )
    target_groups: dict[str, list[tuple[Aggregate, Impact, str, int, bool]]] = defaultdict(list)
    for row in candidate_rows:
        if row[2] in {"A", "B"} and row[0].target_key:
            target_groups[row[0].target_key].append(row)
    manifest = []
    for _target_key, rows_for_target in sorted(
        target_groups.items(), key=lambda item: -max(row[3] for row in item[1])
    ):
        representative = max(rows_for_target, key=lambda row: row[3])
        aggregate, impact, tier, score, _near = representative
        all_rows = [row[0] for row in rows_for_target]
        all_investors = {investor_id for row in all_rows for investor_id in row.investors}
        manifest.append(
            (
                tier,
                score,
                impact.label,
                "; ".join(sorted({row.name for row in all_rows})),
                sum(len(row.rows) for row in all_rows),
                len({event_id for row in all_rows for event_id in row.events}),
                ", ".join(sorted(investor_names.get(value, value) for value in all_investors)),
                impact.mode,
                impact.new_opinions,
                impact.new_pairs,
                impact.new_attention,
                impact.delta_2_attention,
                impact.delta_3_attention,
                impact.delta_2_opinion,
                impact.delta_3_opinion,
            )
        )
    report.append(
        table(
            (
                "Tier",
                "Priority",
                "Proposed/target identity",
                "Reference names",
                "Occurrences",
                "RawEvents",
                "Affected Investors",
                "Impact mode",
                "New Opinions",
                "New Investor×Asset pairs",
                "New Attention",
                "Δ 2+ Attention",
                "Δ 3+ Attention",
                "Δ 2+ Opinion",
                "Δ 3+ Opinion",
            ),
            manifest,
        )
        if manifest
        else "None."
    )
    report.extend(
        [
            "",
            "This manifest is a human review queue only. Do not apply it automatically. External identity confirmation is required before any future Asset/Alias seed.",
            "",
            "## 14. Final Answers",
            "",
        ]
    )
    report.append(
        table(
            ("Question", "Answer"),
            (
                (
                    f"{len(occurrences):,} unresolved: truly worth resolving?",
                    f"The audit finds approximately {tier_a_b_occurrences:,} occurrences ({pct(tier_a_b_occurrences, len(occurrences))}) in Tier A/B deterministic targets; the rest require review, are non-security/noise, or remain UNKNOWN.",
                ),
                (
                    "Primary bottleneck?",
                    "Asset Master coverage is primary for explicit identities/aliases; extraction fidelity is secondary in UNKNOWN, unsupported-market and noise categories.",
                ),
                (
                    "Expected release if highest-value candidates are solved?",
                    f"Unique-target dry-run counts indicate {sum((impact.new_opinions or 0) for impact in impacts.values())} potential new Opinion projections; use per-target manifest counts and do not sum duplicate reference rows.",
                ),
                (
                    "Safe Asset Expansion worthwhile?",
                    "Potentially yes, but only after human review and external confirmation of the Tier A/B manifest.",
                ),
                ("Asset Master writes in this audit", "0 Assets and 0 Aliases added."),
                ("Remaining FAILED Analysis", f"{len(failures)}; reported only; not retried."),
            ),
        )
    )
    report.extend(
        [
            "",
            "## 15. Read-only Boundary",
            "",
            "No data was collected; no LLM was called; no Analysis was retried; no Asset/Alias/Opinion/Attention/Thesis/Cross-Investor row was written; no Intelligence rebuild, migration, commit, or push was performed.",
            "",
            f"Current production identity: `{analysis_version}`. Unresolved occurrences/names: **{len(occurrences):,} / {len({name_key(value.name) for value in aggregates}):,}**.",
        ]
    )
    return "\n".join(report) + "\n"


def load_data(cursor: psycopg.Cursor[Any]) -> dict[str, Any]:
    analysis_version = get_production_analysis_policy().active_analysis_version
    attention_version = get_production_attention_policy_version()
    investor_rows = fetch(
        cursor, "SELECT id, name, platform, platform_user_id FROM investors ORDER BY name, id"
    )
    asset_rows = fetch(
        cursor, "SELECT id, name, market, symbol FROM assets ORDER BY market, symbol, id"
    )
    alias_rows = fetch(
        cursor,
        "SELECT id, asset_id, alias, normalized_alias, alias_type, market FROM asset_aliases ORDER BY asset_id, normalized_alias, id",
    )
    raw_rows = fetch(
        cursor, "SELECT id, investor_id, published_time FROM raw_events ORDER BY published_time, id"
    )
    analysis_rows = fetch(
        cursor,
        "SELECT id, event_id, analysis_version, status, structured_output, calculated_at FROM event_analyses WHERE analysis_version = %s ORDER BY event_id, calculated_at, id",
        (analysis_version,),
    )
    opinion_rows = fetch(
        cursor,
        "SELECT o.id, o.event_id, o.analysis_id, o.investor_id, o.asset_id, o.direction FROM opinions o JOIN event_analyses ea ON ea.id = o.analysis_id WHERE ea.analysis_version = %s AND ea.status IN ('SUCCESS','PARTIALLY_RESOLVED')",
        (analysis_version,),
    )
    attention_rows = fetch(
        cursor,
        "SELECT ao.id, ao.event_id, ao.investor_id, ao.asset_id, ao.analysis_id, ao.attention_policy_version FROM attention_occurrences ao LEFT JOIN event_analyses ea ON ea.id = ao.analysis_id WHERE ao.attention_policy_version = %s AND (ao.analysis_id IS NULL OR (ea.analysis_version = %s AND ea.status IN ('SUCCESS','PARTIALLY_RESOLVED')))",
        (attention_version, analysis_version),
    )
    failure_rows = fetch(
        cursor,
        "SELECT r.id AS event_id, r.investor_id, r.published_time, ea.error_code, ea.provider_metadata FROM raw_events r JOIN event_analyses ea ON ea.event_id = r.id WHERE ea.analysis_version = %s AND ea.status = 'FAILED' ORDER BY r.published_time, r.id",
        (analysis_version,),
    )
    investors = {ident(row["id"]): row for row in investor_rows}
    assets = {ident(row["id"]): row for row in asset_rows}
    raw_events = {ident(row["id"]): row for row in raw_rows}
    failures = []
    for row in failure_rows:
        metadata = (
            row.get("provider_metadata") if isinstance(row.get("provider_metadata"), dict) else {}
        )
        category = str(row.get("error_code") or metadata.get("error_code") or "FAILED").split(
            ":", 1
        )[0][:128]
        failures.append(
            {
                "event_id": ident(row["event_id"]),
                "investor_name": str(
                    investors.get(ident(row["investor_id"]), {}).get("name") or row["investor_id"]
                ),
                "published_time": row["published_time"],
                "category": category,
            }
        )
    return {
        "analysis_version": analysis_version,
        "attention_version": attention_version,
        "investors": investors,
        "assets": assets,
        "aliases": alias_rows,
        "raw_events": raw_events,
        "analyses": analysis_rows,
        "opinions": opinion_rows,
        "attention": attention_rows,
        "failures": failures,
        "lookup": CatalogLookup(asset_rows, alias_rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        help="optional local Markdown output path; PostgreSQL remains read-only",
    )
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    connection, url = connect_read_only()
    try:
        with connection.cursor() as cursor:
            database_name = str(
                scalar(cursor, "SELECT current_database()") or url.database or "<unknown>"
            )
            report = build_report(load_data(cursor), database_name, datetime.now(HK))
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
