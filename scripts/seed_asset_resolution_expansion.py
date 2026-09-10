"""Seed a bounded set of explicit Asset identities from the unresolved audit."""

from __future__ import annotations

import argparse

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from config import get_settings
from scripts.seed_assets import AliasSeed, AssetSeed, SeedSummary, seed_assets

# Every entry below was observed in active RawEvent evidence with an explicit
# supported market and symbol. Symbol aliases are intentionally scoped to that
# market; no name-only alias is added because several names have cross-listing
# evidence and name-only matching would be less conservative.
SAFE_ASSET_RESOLUTION_SEEDS: tuple[AssetSeed, ...] = (
    AssetSeed(
        name="中远海能",
        market="HK",
        symbol="01138",
        aliases=(AliasSeed("01138", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=113ceecd-6dc9-4b54-b5f8-75af4b18c905; "
            "content contains 中远海能(01138); repeated across 7 events and 2 Investors"
        ),
    ),
    AssetSeed(
        name="招金矿业",
        market="HK",
        symbol="01818",
        aliases=(AliasSeed("01818", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=4fa7c13e-98f5-44fc-b7a0-7dd0b159bb48; "
            "content contains 招金矿业(01818); repeated across 5 events and 2 Investors"
        ),
    ),
    AssetSeed(
        name="山东黄金",
        market="HK",
        symbol="01787",
        aliases=(AliasSeed("01787", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=51b8d416-4275-41ab-8c95-841bac32585e; "
            "content contains 山东黄金(01787); cross-listing evidence retained for review"
        ),
    ),
    AssetSeed(
        name="龙源电力",
        market="HK",
        symbol="00916",
        aliases=(AliasSeed("00916", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=22f9bc0a-108e-4257-87bf-c97cf15462ed; "
            "content contains 龙源电力(00916); repeated across 2 events and 2 Investors"
        ),
    ),
    AssetSeed(
        name="西部矿业",
        market="SH",
        symbol="SH601168",
        aliases=(AliasSeed("SH601168", "SYMBOL", "SH"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=1617ed1c-c6ad-48dd-9fc6-6078ba2a75b2; "
            "content contains 西部矿业(SH601168); repeated across 2 events and 2 Investors"
        ),
    ),
    AssetSeed(
        name="联想控股",
        market="HK",
        symbol="03396",
        aliases=(AliasSeed("03396", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=3d5225e8-c437-4d3f-88d1-7364f0369987; "
            "content contains 联想控股(03396); repeated across 2 events and 2 Investors"
        ),
    ),
    AssetSeed(
        name="中远海控",
        market="SH",
        symbol="SH601919",
        aliases=(AliasSeed("SH601919", "SYMBOL", "SH"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=290342b3-42a1-4392-90f5-e68a82964998; "
            "content contains 中远海控(SH601919); repeated across 2 events and 2 Investors"
        ),
    ),
    AssetSeed(
        name="中国黄金国际",
        market="HK",
        symbol="02099",
        aliases=(AliasSeed("02099", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=0d725908-48bc-46ea-aa6d-9a63b3fda9ae; "
            "content contains 中国黄金国际(02099); repeated across 7 events"
        ),
    ),
    AssetSeed(
        name="建滔集团",
        market="HK",
        symbol="00148",
        aliases=(AliasSeed("00148", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=1c0dd01d-2d2c-4943-ad97-48e9b49503cf; "
            "content contains 建滔集团(00148); repeated across 4 events"
        ),
    ),
    AssetSeed(
        name="五矿资源",
        market="HK",
        symbol="01208",
        aliases=(AliasSeed("01208", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=42c50502-827d-4a2b-963e-31c51a435ecc; "
            "content contains 五矿资源(01208); repeated across 4 events"
        ),
    ),
    AssetSeed(
        name="神威药业",
        market="HK",
        symbol="02877",
        aliases=(AliasSeed("02877", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=1914fb51-460a-4b1f-97ab-2bb6ee7f27b4; "
            "content contains 神威药业(02877); repeated across 2 events"
        ),
    ),
    AssetSeed(
        name="彩客新能源",
        market="HK",
        symbol="01986",
        aliases=(AliasSeed("01986", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=a80d527c-5a76-49ef-ac48-0c471d9436e2; "
            "content contains 彩客新能源(01986); repeated across 2 events"
        ),
    ),
    AssetSeed(
        name="哈尔滨电气",
        market="HK",
        symbol="01133",
        aliases=(AliasSeed("01133", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=261c6aa3-404e-4c26-b486-7fb2af38ae06; "
            "content contains 哈尔滨电气(01133); repeated across 2 events"
        ),
    ),
    AssetSeed(
        name="南山铝业",
        market="SH",
        symbol="SH600219",
        aliases=(AliasSeed("SH600219", "SYMBOL", "SH"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=1f168f58-9205-4644-911b-6f939f56adfd; "
            "content contains 南山铝业(SH600219); repeated across 2 events"
        ),
    ),
    AssetSeed(
        name="云铝股份",
        market="SZ",
        symbol="SZ000807",
        aliases=(AliasSeed("SZ000807", "SYMBOL", "SZ"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=1f168f58-9205-4644-911b-6f939f56adfd; "
            "content contains 云铝股份(SZ000807); repeated across 2 events"
        ),
    ),
    AssetSeed(
        name="中广核新能源",
        market="HK",
        symbol="01811",
        aliases=(AliasSeed("01811", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=6674fc14-8d5d-4971-8cc7-c2d73ef6275e; "
            "content contains 中广核新能源(01811); repeated across 2 events"
        ),
    ),
    AssetSeed(
        name="中国建材",
        market="HK",
        symbol="03323",
        aliases=(AliasSeed("03323", "SYMBOL", "HK"),),
        evidence=(
            "Active unresolved evidence: RawEvent event_id=53adc903-262a-4f00-a0f2-f8065475467c; "
            "content contains 中国建材(03323); repeated across 2 events"
        ),
    ),
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    settings = get_settings()
    engine = create_engine(settings.database_url, pool_pre_ping=True)
    try:
        with Session(engine) as session:
            summary: SeedSummary = seed_assets(session, SAFE_ASSET_RESOLUTION_SEEDS)
            if args.dry_run:
                session.rollback()
            else:
                session.commit()
            print(
                f"Assets: created={summary.assets_created} reused={summary.assets_reused}; "
                f"Aliases: created={summary.aliases_created} reused={summary.aliases_reused}; "
                f"dry_run={args.dry_run}"
            )
            for seed, asset_id in zip(
                SAFE_ASSET_RESOLUTION_SEEDS,
                summary.asset_ids,
                strict=True,
            ):
                print(f"{seed.name} {seed.market}:{seed.symbol} asset_id={asset_id}")
                print(f"  evidence={seed.evidence}")
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
