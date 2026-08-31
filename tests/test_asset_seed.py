from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contracts import AssetReference
from database.models import Asset, AssetAlias
from database.repositories import AssetRepository
from resolution import AssetResolver
from scripts.seed_assets import AliasSeed, AssetSeed, seed_assets


def test_seed_is_idempotent_and_prevents_duplicates(db_session: Session) -> None:
    seeds = (
        AssetSeed(
            name="Seeded Asset",
            market="SH",
            symbol="SH600585",
            aliases=(
                AliasSeed("Seeded Asset", "NAME", "SH"),
                AliasSeed("SH600585", "SYMBOL", "SH"),
            ),
            evidence="test fixture",
        ),
    )

    first = seed_assets(db_session, seeds)
    db_session.commit()
    second = seed_assets(db_session, seeds)
    db_session.commit()

    assert first.assets_created == 1
    assert first.assets_reused == 0
    assert first.aliases_created == 2
    assert first.aliases_reused == 0
    assert second.assets_created == 0
    assert second.assets_reused == 1
    assert second.aliases_created == 0
    assert second.aliases_reused == 2
    assert db_session.scalar(select(func.count()).select_from(Asset)) == 1
    assert db_session.scalar(select(func.count()).select_from(AssetAlias)) == 2


def test_seeded_canonical_and_alias_identity_resolve(db_session: Session) -> None:
    seeds = (
        AssetSeed(
            name="海螺水泥",
            market="SH",
            symbol="600585",
            aliases=(AliasSeed("海螺水泥", "NAME", "SH"),),
            evidence="test fixture",
        ),
    )
    seed_assets(db_session, seeds)
    db_session.commit()

    asset = db_session.scalar(select(Asset).where(Asset.symbol == "600585"))
    assert asset is not None

    result = AssetResolver(AssetRepository(db_session)).resolve(
        AssetReference(name_hint="海螺水泥", symbol_hint="SH600585", market_hint="SH")
    )
    assert result.asset_id == asset.id
