import re
from collections import defaultdict
from collections.abc import Iterable
from uuid import UUID

from contracts import (
    AssetMentionCandidate,
    AssetMentionMatch,
    AssetTextMatch,
)

_MATCH_PRIORITY = {
    "CANONICAL_NAME": 0,
    "NAME_ALIAS": 1,
    "SYMBOL_ALIAS": 2,
}


def match_asset_mentions(
    content: str,
    candidates: Iterable[AssetMentionCandidate],
) -> tuple[AssetMentionMatch, ...]:
    """Match unique canonical names and aliases without fuzzy inference."""

    normalized_content = _normalize_text(content)
    token_assets: dict[str, dict[UUID, list[AssetTextMatch]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for candidate in candidates:
        _register(
            token_assets,
            candidate.asset_id,
            candidate.canonical_name,
            "CANONICAL_NAME",
        )
        for alias in candidate.aliases:
            matched_by = (
                "SYMBOL_ALIAS" if alias.alias_type.strip().upper() == "SYMBOL" else "NAME_ALIAS"
            )
            _register(token_assets, candidate.asset_id, alias.text, matched_by)

    matches_by_asset: dict[UUID, dict[tuple[str, str], AssetTextMatch]] = defaultdict(dict)
    for normalized_token, asset_matches in token_assets.items():
        if len(asset_matches) != 1 or not _contains(normalized_content, normalized_token):
            continue
        asset_id, text_matches = next(iter(asset_matches.items()))
        best = min(text_matches, key=lambda value: _MATCH_PRIORITY[value.matched_by])
        matches_by_asset[asset_id][(best.matched_by, best.matched_text)] = best

    return tuple(
        AssetMentionMatch(
            asset_id=asset_id,
            matches=tuple(
                sorted(
                    matches.values(),
                    key=lambda value: (
                        _MATCH_PRIORITY[value.matched_by],
                        value.matched_text.casefold(),
                    ),
                )
            ),
        )
        for asset_id, matches in sorted(matches_by_asset.items(), key=lambda item: item[0].int)
    )


def _register(
    registry: dict[str, dict[UUID, list[AssetTextMatch]]],
    asset_id: UUID,
    text: str,
    matched_by: str,
) -> None:
    normalized = _normalize_text(text)
    if not normalized:
        return
    registry[normalized][asset_id].append(
        AssetTextMatch(matched_text=text.strip(), matched_by=matched_by)
    )


def _normalize_text(value: str) -> str:
    return " ".join(value.split()).casefold()


def _contains(content: str, token: str) -> bool:
    if token.isascii() and any(character.isalnum() for character in token):
        pattern = rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])"
        return re.search(pattern, content, flags=re.IGNORECASE) is not None
    return token in content
