"""Deterministic taxonomy and prioritization for unresolved Asset references."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from contracts import AssetReference, normalize_asset_reference, normalize_market_hint


class UnresolvedReferenceCategory(StrEnum):
    EXPLICIT_MARKET_SYMBOL = "EXPLICIT_MARKET_SYMBOL"
    SYMBOL_MISSING_MARKET = "SYMBOL_MISSING_MARKET"
    CANONICAL_LOOKING_NAME_ONLY = "CANONICAL_LOOKING_NAME_ONLY"
    NICKNAME_ABBREVIATION = "NICKNAME_ABBREVIATION"
    CROSS_LISTING_AMBIGUITY = "CROSS_LISTING_AMBIGUITY"
    CONCEPT_INDUSTRY_NON_SECURITY = "CONCEPT_INDUSTRY_NON_SECURITY"
    EXTRACTION_NOISE = "EXTRACTION_NOISE"
    UNKNOWN = "UNKNOWN"


class UnresolvedReferenceBlocker(StrEnum):
    SAFE_ASSET_MASTER_MISSING = "SAFE_ASSET_MASTER_MISSING"
    SAFE_EMBEDDED_MARKET_SYMBOL = "SAFE_EMBEDDED_MARKET_SYMBOL"
    UNSUPPORTED_MARKET_HINT = "UNSUPPORTED_MARKET_HINT"
    CROSS_LISTING_REVIEW = "CROSS_LISTING_REVIEW"
    MISSING_EXPLICIT_IDENTITY = "MISSING_EXPLICIT_IDENTITY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class AssetCatalogIdentity:
    name: str
    market: str
    symbol: str


@dataclass(frozen=True, slots=True)
class UnresolvedReference:
    name: str
    symbol: str | None
    market: str | None
    investor_id: UUID
    event_id: UUID
    published_time: datetime
    candidate_asset_ids: tuple[UUID, ...] = ()


@dataclass(frozen=True, slots=True)
class UnresolvedReferenceAggregate:
    name: str
    symbol: str | None
    market: str | None
    category: UnresolvedReferenceCategory
    blocker: UnresolvedReferenceBlocker
    occurrence_count: int
    investor_ids: tuple[UUID, ...]
    event_ids: tuple[UUID, ...]
    published_dates: tuple[date, ...]
    first_published_time: datetime
    latest_published_time: datetime

    @property
    def distinct_investor_count(self) -> int:
        return len(self.investor_ids)

    @property
    def distinct_event_count(self) -> int:
        return len(self.event_ids)

    @property
    def active_day_count(self) -> int:
        return len(self.published_dates)

    @property
    def repeated_cross_day(self) -> bool:
        return self.occurrence_count >= 2 and self.active_day_count >= 2

    @property
    def cross_investor_relevance(self) -> bool:
        return self.distinct_investor_count >= 2

    @property
    def safe_to_seed(self) -> bool:
        return self.blocker in {
            UnresolvedReferenceBlocker.SAFE_ASSET_MASTER_MISSING,
            UnresolvedReferenceBlocker.SAFE_EMBEDDED_MARKET_SYMBOL,
        }

    def priority_key(self) -> tuple[object, ...]:
        """Rank overlap impact before raw frequency."""

        return (
            int(self.cross_investor_relevance),
            self.distinct_investor_count,
            int(self.repeated_cross_day),
            int(self.safe_to_seed),
            self.occurrence_count,
            self.distinct_event_count,
            self.name,
            self.symbol or "",
            self.market or "",
        )


_SUPPORTED_MARKETS = {"HK", "SH", "SZ"}
_CANONICAL_SUFFIXES = (
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
    "指数",
)
_CONCEPT_TERMS = (
    "行业",
    "板块",
    "煤炭股",
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
    "油运",
    "煤价",
    "煤",
    "油",
    "黄金",
    "银行",
    "低估值",
    "高分红",
    "质优股",
    "大盘",
)
_NOISE_TERMS = (
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
_NICKNAME_TERMS = (
    "海控",
    "海能",
    "山金",
    "紫金",
    "五矿",
    "招行",
    "老窖",
    "康臣",
    "lc",
)


def build_unresolved_inventory(
    references: Iterable[UnresolvedReference],
    *,
    catalog: Iterable[AssetCatalogIdentity] = (),
) -> tuple[UnresolvedReferenceAggregate, ...]:
    """Aggregate and classify references using only explicit local evidence."""

    values = tuple(references)
    explicit_by_name: dict[str, set[tuple[str, str]]] = defaultdict(set)
    catalog_by_name: dict[str, set[tuple[str, str]]] = defaultdict(set)
    existing_identities: set[tuple[str, str]] = set()
    for reference in values:
        if reference.name and reference.symbol and reference.market:
            identity = _identity(reference.market, reference.symbol)
            if identity is not None:
                explicit_by_name[_name_key(reference.name)].add(identity)
    for asset in catalog:
        identity = _identity(asset.market, asset.symbol)
        if identity is not None:
            catalog_by_name[_name_key(asset.name)].add(identity)
            existing_identities.add(identity)

    grouped: dict[tuple[str, str | None, str | None], list[UnresolvedReference]] = defaultdict(list)
    for reference in values:
        key = (
            _name_key(reference.name),
            _symbol_key(reference.symbol),
            _market_key(reference.market),
        )
        grouped[key].append(reference)

    aggregates: list[UnresolvedReferenceAggregate] = []
    for group in grouped.values():
        first = group[0]
        identity_count = len(explicit_by_name.get(_name_key(first.name), set()))
        existing_name_count = len(catalog_by_name.get(_name_key(first.name), set()))
        category = classify_reference(
            first,
            explicit_identity_count=identity_count,
            existing_name_identity_count=existing_name_count,
        )
        blocker = _blocker(
            first,
            category=category,
            existing_identities=existing_identities,
        )
        aggregates.append(
            UnresolvedReferenceAggregate(
                name=first.name,
                symbol=first.symbol,
                market=first.market,
                category=category,
                blocker=blocker,
                occurrence_count=len(group),
                investor_ids=tuple(
                    sorted({item.investor_id for item in group}, key=lambda value: value.int)
                ),
                event_ids=tuple(
                    sorted({item.event_id for item in group}, key=lambda value: value.int)
                ),
                published_dates=tuple(sorted({item.published_time.date() for item in group})),
                first_published_time=min(item.published_time for item in group),
                latest_published_time=max(item.published_time for item in group),
            )
        )
    return tuple(aggregates)


def classify_reference(
    reference: UnresolvedReference,
    *,
    explicit_identity_count: int = 0,
    existing_name_identity_count: int = 0,
) -> UnresolvedReferenceCategory:
    """Classify one reference without external knowledge or fuzzy matching."""

    if len(reference.candidate_asset_ids) >= 2:
        return UnresolvedReferenceCategory.CROSS_LISTING_AMBIGUITY
    if reference.name and reference.symbol and reference.market:
        if explicit_identity_count > 1 or existing_name_identity_count > 1:
            return UnresolvedReferenceCategory.CROSS_LISTING_AMBIGUITY
        return UnresolvedReferenceCategory.EXPLICIT_MARKET_SYMBOL
    if reference.symbol:
        return UnresolvedReferenceCategory.SYMBOL_MISSING_MARKET
    name = reference.name.strip()
    if any(term in name for term in _NOISE_TERMS):
        return UnresolvedReferenceCategory.EXTRACTION_NOISE
    if name in _CONCEPT_TERMS:
        return UnresolvedReferenceCategory.CONCEPT_INDUSTRY_NON_SECURITY
    if name in _NICKNAME_TERMS:
        return UnresolvedReferenceCategory.NICKNAME_ABBREVIATION
    if name.endswith(_CANONICAL_SUFFIXES):
        return UnresolvedReferenceCategory.CANONICAL_LOOKING_NAME_ONLY
    return UnresolvedReferenceCategory.UNKNOWN


def _blocker(
    reference: UnresolvedReference,
    *,
    category: UnresolvedReferenceCategory,
    existing_identities: set[tuple[str, str]],
) -> UnresolvedReferenceBlocker:
    normalized = normalize_asset_reference(
        AssetReference(
            name_hint=reference.name or None,
            symbol_hint=reference.symbol,
            market_hint=reference.market,
        )
    )
    if reference.market and normalize_market_hint(reference.market) is None:
        return UnresolvedReferenceBlocker.UNSUPPORTED_MARKET_HINT
    if category is UnresolvedReferenceCategory.CROSS_LISTING_AMBIGUITY:
        if normalized.market in _SUPPORTED_MARKETS and normalized.symbol:
            identity = (normalized.market, normalized.symbol)
            if identity not in existing_identities:
                return UnresolvedReferenceBlocker.SAFE_ASSET_MASTER_MISSING
        return UnresolvedReferenceBlocker.CROSS_LISTING_REVIEW
    if reference.symbol and not reference.market and normalized.market and normalized.symbol:
        if normalized.market in _SUPPORTED_MARKETS:
            return UnresolvedReferenceBlocker.SAFE_EMBEDDED_MARKET_SYMBOL
    if normalized.market and normalized.symbol:
        identity = (normalized.market, normalized.symbol)
        if identity not in existing_identities and normalized.market in _SUPPORTED_MARKETS:
            return UnresolvedReferenceBlocker.SAFE_ASSET_MASTER_MISSING
        return UnresolvedReferenceBlocker.UNKNOWN
    if reference.symbol and not reference.market:
        return UnresolvedReferenceBlocker.MISSING_EXPLICIT_IDENTITY
    if category in {
        UnresolvedReferenceCategory.CANONICAL_LOOKING_NAME_ONLY,
        UnresolvedReferenceCategory.NICKNAME_ABBREVIATION,
        UnresolvedReferenceCategory.CONCEPT_INDUSTRY_NON_SECURITY,
        UnresolvedReferenceCategory.EXTRACTION_NOISE,
    }:
        return UnresolvedReferenceBlocker.MISSING_EXPLICIT_IDENTITY
    return UnresolvedReferenceBlocker.UNKNOWN


def _identity(market: str | None, symbol: str | None) -> tuple[str, str] | None:
    normalized_market = normalize_market_hint(market)
    normalized = normalize_asset_reference(AssetReference(symbol_hint=symbol, market_hint=market))
    if normalized_market is None or normalized.symbol is None:
        return None
    return normalized_market, normalized.symbol


def _name_key(value: str | None) -> str:
    return " ".join((value or "").split()).casefold()


def _symbol_key(value: str | None) -> str | None:
    return value.strip().upper() if value and value.strip() else None


def _market_key(value: str | None) -> str | None:
    return value.strip().upper() if value and value.strip() else None


__all__ = [
    "AssetCatalogIdentity",
    "UnresolvedReference",
    "UnresolvedReferenceAggregate",
    "UnresolvedReferenceBlocker",
    "UnresolvedReferenceCategory",
    "build_unresolved_inventory",
    "classify_reference",
]
