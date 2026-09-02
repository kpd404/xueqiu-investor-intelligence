"""Seed a small, evidence-backed Asset master set.

This module intentionally contains no discovery logic. Every entry must be
backed by an explicit source observation documented in the manifest below.
The seed is separate from Alembic migrations and is safe to run repeatedly:
existing canonical identities and aliases are reused without mutation.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from config import get_settings
from contracts import normalize_market_hint, normalize_name_hint, normalize_symbol_hint
from database.models import Asset, AssetAlias


@dataclass(frozen=True)
class AliasSeed:
    alias: str
    alias_type: str
    market: str | None = None


@dataclass(frozen=True)
class AssetSeed:
    name: str
    market: str
    symbol: str
    aliases: tuple[AliasSeed, ...]
    evidence: str


@dataclass(frozen=True)
class SeedSummary:
    assets_created: int
    assets_reused: int
    aliases_created: int
    aliases_reused: int
    asset_ids: tuple[UUID, ...]


# These are the only current entries with both an issuer name and a market /
# symbol identity in the real PostgreSQL Xueqiu payloads. The names come from
# retweeted_status.user.screen_name and the codes from retweeted_status.symbol_id.
# Source event IDs are retained here as an audit note; no RawEvent is mutated.
SEED_ASSETS: tuple[AssetSeed, ...] = (
    AssetSeed(
        name="山西焦煤",
        market="SZ",
        symbol="000983",
        aliases=(
            AliasSeed("山西焦煤", "NAME", "SZ"),
            AliasSeed("SZ000983", "SYMBOL", "SZ"),
        ),
        evidence=(
            "RawEvent source_event_id=406988361; "
            "retweeted_status.user.screen_name=山西焦煤(SZ000983); "
            "retweeted_status.symbol_id=SZ000983"
        ),
    ),
    AssetSeed(
        name="比音勒芬",
        market="SZ",
        symbol="002832",
        aliases=(
            AliasSeed("比音勒芬", "NAME", "SZ"),
            AliasSeed("SZ002832", "SYMBOL", "SZ"),
        ),
        evidence=(
            "RawEvent source_event_id=406986078; "
            "retweeted_status.user.screen_name=比音勒芬(SZ002832); "
            "retweeted_status.symbol_id=SZ002832"
        ),
    ),
    AssetSeed(
        name="特变电工",
        market="SH",
        symbol="600089",
        aliases=(
            AliasSeed("特变电工", "NAME"),
            AliasSeed("SH600089", "SYMBOL", "SH"),
        ),
        evidence=(
            "RawEvent event_id=2748576f-1e25-46eb-b96d-d614b29f55fa; "
            "content contains 特变电工(SH600089)"
        ),
    ),
    AssetSeed(
        name="紫金矿业",
        market="SH",
        symbol="601899",
        aliases=(
            AliasSeed("紫金矿业", "NAME"),
            AliasSeed("SH601899", "SYMBOL", "SH"),
        ),
        evidence=(
            "RawEvent event_id=0176863d-f0b4-4042-a3a6-c5fc93044220; "
            "content contains 紫金矿业(SH601899)"
        ),
    ),
    AssetSeed(
        name="中国神华",
        market="SH",
        symbol="601088",
        aliases=(
            AliasSeed("中国神华", "NAME", "SH"),
            AliasSeed("SH601088", "SYMBOL", "SH"),
        ),
        evidence=(
            "RawEvent event_id=77e19211-c9a1-4ce6-b3d2-36e7c7a7b991; "
            "quoted content contains 中国神华(SH601088); "
            "separate 01088 evidence is retained as a cross-listing caution"
        ),
    ),
    AssetSeed(
        name="中远海能",
        market="SH",
        symbol="600026",
        aliases=(
            AliasSeed("中远海能", "NAME", "SH"),
            AliasSeed("SH600026", "SYMBOL", "SH"),
        ),
        evidence=(
            "RawEvent event_id=c0b8c3f9-f2a4-4163-b49c-bddd0b7fef53; "
            "content contains 中远海能(SH600026)"
        ),
    ),
    AssetSeed(
        name="招商轮船",
        market="SH",
        symbol="601872",
        aliases=(
            AliasSeed("招商轮船", "NAME"),
            AliasSeed("SH601872", "SYMBOL", "SH"),
        ),
        evidence=(
            "RawEvent event_id=c0b8c3f9-f2a4-4163-b49c-bddd0b7fef53; "
            "content contains 招商轮船(SH601872)"
        ),
    ),
)


def _canonical_asset(session: Session, seed: AssetSeed) -> tuple[Asset, bool]:
    market = normalize_market_hint(seed.market)
    symbol = normalize_symbol_hint(seed.symbol)
    if market is None or symbol is None:
        raise ValueError(f"invalid canonical identity in seed: {seed.name}")

    asset = session.scalar(
        select(Asset).where(
            func.upper(Asset.market) == market,
            func.upper(Asset.symbol) == symbol,
        )
    )
    if asset is not None:
        return asset, False

    asset = Asset(name=seed.name.strip(), market=market, symbol=symbol)
    session.add(asset)
    session.flush()
    return asset, True


def _normalized_alias(alias: AliasSeed) -> tuple[str, str | None]:
    alias_type = alias.alias_type.strip().upper()
    if alias_type == "SYMBOL":
        normalized = normalize_symbol_hint(alias.alias)
    else:
        normalized = normalize_name_hint(alias.alias)
    market = normalize_market_hint(alias.market)
    if not normalized:
        raise ValueError(f"blank alias in seed: {alias.alias!r}")
    return normalized, market


def seed_assets(session: Session, seeds: tuple[AssetSeed, ...] = SEED_ASSETS) -> SeedSummary:
    """Insert or reuse explicit canonical Assets and their aliases.

    The caller owns the transaction and should commit only after this function
    returns successfully. Existing rows are never updated.
    """

    assets_created = 0
    assets_reused = 0
    aliases_created = 0
    aliases_reused = 0
    asset_ids: list[UUID] = []

    for seed in seeds:
        asset, created = _canonical_asset(session, seed)
        if created:
            assets_created += 1
        else:
            assets_reused += 1
        asset_ids.append(asset.id)

        for alias in seed.aliases:
            normalized_alias, market = _normalized_alias(alias)
            existing = session.scalar(
                select(AssetAlias).where(
                    AssetAlias.asset_id == asset.id,
                    func.upper(AssetAlias.normalized_alias) == normalized_alias.upper(),
                )
            )
            if existing is not None:
                aliases_reused += 1
                continue

            session.add(
                AssetAlias(
                    asset_id=asset.id,
                    alias=alias.alias.strip(),
                    normalized_alias=normalized_alias,
                    alias_type=alias.alias_type.strip().upper(),
                    market=market,
                )
            )
            session.flush()
            aliases_created += 1

    return SeedSummary(
        assets_created=assets_created,
        assets_reused=assets_reused,
        aliases_created=aliases_created,
        aliases_reused=aliases_reused,
        asset_ids=tuple(asset_ids),
    )


def _print_summary(summary: SeedSummary, seeds: tuple[AssetSeed, ...]) -> None:
    print(
        "Assets: "
        f"created={summary.assets_created} reused={summary.assets_reused}; "
        "Aliases: "
        f"created={summary.aliases_created} reused={summary.aliases_reused}"
    )
    for seed, asset_id in zip(seeds, summary.asset_ids, strict=True):
        print(f"Asset: {seed.name} / {seed.market}:{seed.symbol} / {asset_id}")
        print(f"Evidence: {seed.evidence}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed explicit Asset master data")
    parser.add_argument(
        "--database-url",
        default=None,
        help="optional database URL override (otherwise the neutral project config is used)",
    )
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(args.database_url or settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            summary = seed_assets(session)
            session.commit()
            _print_summary(summary, SEED_ASSETS)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
