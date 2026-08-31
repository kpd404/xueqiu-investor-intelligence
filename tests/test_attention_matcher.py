from uuid import uuid4

from contracts import AssetMentionAlias, AssetMentionCandidate
from intelligence.policies import match_asset_mentions


def test_exact_name_and_symbol_alias_matching_are_deterministic() -> None:
    asset_id = uuid4()
    candidate = AssetMentionCandidate(
        asset_id=asset_id,
        canonical_name="Tencent Holdings",
        aliases=(
            AssetMentionAlias(text="腾讯", alias_type="NAME"),
            AssetMentionAlias(text="00700", alias_type="SYMBOL"),
        ),
    )

    matches = match_asset_mentions("腾讯与00700都被提到，腾讯再次出现。", (candidate,))

    assert len(matches) == 1
    assert matches[0].asset_id == asset_id
    assert {item.matched_by for item in matches[0].matches} == {
        "NAME_ALIAS",
        "SYMBOL_ALIAS",
    }


def test_ambiguous_alias_is_ignored() -> None:
    candidates = (
        AssetMentionCandidate(
            asset_id=uuid4(),
            canonical_name="First",
            aliases=(AssetMentionAlias(text="同名", alias_type="NAME"),),
        ),
        AssetMentionCandidate(
            asset_id=uuid4(),
            canonical_name="Second",
            aliases=(AssetMentionAlias(text="同名", alias_type="NAME"),),
        ),
    )

    assert match_asset_mentions("今天讨论同名。", candidates) == ()


def test_symbol_alias_requires_ascii_boundaries() -> None:
    candidate = AssetMentionCandidate(
        asset_id=uuid4(),
        canonical_name="Example",
        aliases=(AssetMentionAlias(text="700", alias_type="SYMBOL"),),
    )

    assert match_asset_mentions("17001", (candidate,)) == ()
