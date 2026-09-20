from datetime import UTC, datetime, timedelta
from uuid import uuid4

from resolution import (
    AssetCatalogIdentity,
    UnresolvedReference,
    UnresolvedReferenceBlocker,
    UnresolvedReferenceCategory,
    build_unresolved_inventory,
)


def reference(
    *,
    name: str,
    symbol: str | None = None,
    market: str | None = None,
    investor_id=None,
    event_id=None,
    published_time=None,
) -> UnresolvedReference:
    return UnresolvedReference(
        name=name,
        symbol=symbol,
        market=market,
        investor_id=investor_id or uuid4(),
        event_id=event_id or uuid4(),
        published_time=published_time or datetime(2026, 9, 1, tzinfo=UTC),
    )


def test_supported_explicit_market_symbol_is_safe_when_asset_is_missing() -> None:
    item = build_unresolved_inventory(
        [reference(name="Example Holdings", symbol="SH600001", market="SH")]
    )[0]

    assert item.category is UnresolvedReferenceCategory.EXPLICIT_MARKET_SYMBOL
    assert item.blocker is UnresolvedReferenceBlocker.SAFE_ASSET_MASTER_MISSING
    assert item.safe_to_seed is True


def test_unknown_cn_symbol_prefix_is_not_safe_even_when_symbol_is_explicit() -> None:
    item = build_unresolved_inventory(
        [reference(name="Example Holdings", symbol="ABC123", market="CN")]
    )[0]

    assert item.blocker is UnresolvedReferenceBlocker.UNSUPPORTED_MARKET_HINT
    assert item.safe_to_seed is False


def test_cn_prefixed_listing_is_safe_when_asset_is_missing() -> None:
    item = build_unresolved_inventory(
        [reference(name="Example Holdings", symbol="SZ300308", market="CN")]
    )[0]

    assert item.category is UnresolvedReferenceCategory.EXPLICIT_MARKET_SYMBOL
    assert item.blocker is UnresolvedReferenceBlocker.SAFE_ASSET_MASTER_MISSING
    assert item.safe_to_seed is True


def test_existing_name_with_multiple_identities_is_cross_listing_review() -> None:
    item = build_unresolved_inventory(
        [
            reference(name="Example", symbol="01787", market="HK"),
            reference(name="Example", symbol="600547", market="SH"),
        ],
        catalog=[AssetCatalogIdentity(name="Example", market="SH", symbol="600547")],
    )[0]

    assert item.category is UnresolvedReferenceCategory.CROSS_LISTING_AMBIGUITY
    assert item.safe_to_seed is True


def test_short_unknown_name_is_not_inferred_as_nickname() -> None:
    item = build_unresolved_inventory([reference(name="中创智领")])[0]

    assert item.category is UnresolvedReferenceCategory.UNKNOWN


def test_priority_prefers_multi_investor_cross_day_evidence_over_frequency() -> None:
    investor_a = uuid4()
    investor_b = uuid4()
    noisy = [reference(name="Noisy", investor_id=investor_a) for _ in range(10)]
    strong = [
        reference(
            name="Strong",
            symbol="01138",
            market="HK",
            investor_id=investor_a,
            published_time=datetime(2026, 9, 1, tzinfo=UTC),
        ),
        reference(
            name="Strong",
            symbol="01138",
            market="HK",
            investor_id=investor_b,
            published_time=datetime(2026, 9, 2, tzinfo=UTC) + timedelta(hours=1),
        ),
    ]

    inventory = build_unresolved_inventory([*noisy, *strong])

    assert (
        sorted(inventory, key=lambda value: value.priority_key(), reverse=True)[0].name == "Strong"
    )
