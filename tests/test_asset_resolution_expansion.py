from contracts import normalize_market_hint, normalize_symbol_hint
from scripts.seed_asset_resolution_expansion import SAFE_ASSET_RESOLUTION_SEEDS


def test_expansion_manifest_contains_only_supported_explicit_identities() -> None:
    identities = {
        (
            normalize_market_hint(seed.market),
            normalize_symbol_hint(seed.symbol),
        )
        for seed in SAFE_ASSET_RESOLUTION_SEEDS
    }

    assert len(SAFE_ASSET_RESOLUTION_SEEDS) == 19
    assert len(identities) == len(SAFE_ASSET_RESOLUTION_SEEDS)
    assert all(market in {"HK", "SH", "SZ"} and symbol for market, symbol in identities)


def test_expansion_manifest_uses_market_scoped_symbol_aliases_only() -> None:
    assert all(len(seed.aliases) == 1 for seed in SAFE_ASSET_RESOLUTION_SEEDS)
    assert all(seed.aliases[0].alias_type == "SYMBOL" for seed in SAFE_ASSET_RESOLUTION_SEEDS)
    assert all(seed.aliases[0].market == seed.market for seed in SAFE_ASSET_RESOLUTION_SEEDS)
