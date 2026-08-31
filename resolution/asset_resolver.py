from collections.abc import Iterable
from typing import Protocol
from uuid import UUID

from contracts import (
    AssetReference,
    AssetResolutionResult,
    AssetResolutionStatus,
    NormalizedAssetReference,
    normalize_asset_reference,
    normalize_market_hint,
)


class AssetLookup(Protocol):
    """Repository port returning identity candidates, never a best guess."""

    def list_ids_by_market_symbol(self, market: str, symbol: str) -> Iterable[UUID]: ...

    def list_ids_by_normalized_alias(
        self, normalized_alias: str, market: str | None = None
    ) -> Iterable[UUID]: ...

    def list_ids_by_normalized_name(
        self, normalized_name: str, market: str | None = None
    ) -> Iterable[UUID]: ...


class AssetResolver:
    """Resolve AssetReference hints deterministically without creating Assets."""

    def __init__(self, lookup: AssetLookup) -> None:
        self._lookup = lookup

    def resolve(self, reference: AssetReference) -> AssetResolutionResult:
        normalized = normalize_asset_reference(reference)
        invalid_reason = self._invalid_reason(reference)
        if invalid_reason is not None:
            return self._result(
                reference,
                normalized,
                AssetResolutionStatus.INVALID,
                reason=invalid_reason,
            )
        if not any((normalized.name, normalized.symbol, normalized.market)):
            return self._result(
                reference,
                normalized,
                AssetResolutionStatus.INVALID,
                reason="NO_USABLE_IDENTITY_HINTS",
            )

        if normalized.market and normalized.symbol:
            strong_candidates = self._sorted_ids(
                self._lookup.list_ids_by_market_symbol(
                    normalized.market,
                    normalized.symbol,
                )
            )
            if len(strong_candidates) > 1:
                return self._result(
                    reference,
                    normalized,
                    AssetResolutionStatus.AMBIGUOUS,
                    candidate_asset_ids=strong_candidates,
                    matched_by="MARKET_SYMBOL",
                    reason="MULTIPLE_MARKET_SYMBOL_MATCHES",
                )
            if len(strong_candidates) == 1:
                strong_id = strong_candidates[0]
                if normalized.name:
                    name_candidates = self._name_candidates(normalized.name, None)
                    conflicting = tuple(
                        candidate for candidate in name_candidates if candidate != strong_id
                    )
                    if conflicting:
                        return self._result(
                            reference,
                            normalized,
                            AssetResolutionStatus.AMBIGUOUS,
                            candidate_asset_ids=self._sorted_ids((strong_id, *conflicting)),
                            reason="CONFLICTING_IDENTITY_HINTS",
                        )
                return self._result(
                    reference,
                    normalized,
                    AssetResolutionStatus.RESOLVED,
                    asset_id=strong_id,
                    matched_by="MARKET_SYMBOL",
                )

        symbol_candidates = (
            set(
                self._lookup.list_ids_by_normalized_alias(
                    normalized.symbol,
                    normalized.market,
                )
            )
            if normalized.symbol
            else set()
        )
        name_candidates = (
            set(self._name_candidates(normalized.name, normalized.market))
            if normalized.name
            else set()
        )
        if symbol_candidates and name_candidates and symbol_candidates != name_candidates:
            return self._result(
                reference,
                normalized,
                AssetResolutionStatus.AMBIGUOUS,
                candidate_asset_ids=self._sorted_ids((*symbol_candidates, *name_candidates)),
                reason="CONFLICTING_IDENTITY_HINTS",
            )

        if symbol_candidates:
            candidates = self._sorted_ids(symbol_candidates)
            if len(candidates) == 1:
                return self._result(
                    reference,
                    normalized,
                    AssetResolutionStatus.RESOLVED,
                    asset_id=candidates[0],
                    matched_by="SYMBOL_ALIAS",
                )
            return self._result(
                reference,
                normalized,
                AssetResolutionStatus.AMBIGUOUS,
                candidate_asset_ids=candidates,
                matched_by="SYMBOL_ALIAS",
                reason="MULTIPLE_SYMBOL_ALIAS_MATCHES",
            )

        if name_candidates:
            candidates = self._sorted_ids(name_candidates)
            matched_by = "NAME_ALIAS_WITH_MARKET" if normalized.market else "NAME_ALIAS"
            if len(candidates) == 1:
                return self._result(
                    reference,
                    normalized,
                    AssetResolutionStatus.RESOLVED,
                    asset_id=candidates[0],
                    matched_by=matched_by,
                )
            return self._result(
                reference,
                normalized,
                AssetResolutionStatus.AMBIGUOUS,
                candidate_asset_ids=candidates,
                matched_by=matched_by,
                reason="MULTIPLE_NAME_ALIAS_MATCHES",
            )

        return self._result(
            reference,
            normalized,
            AssetResolutionStatus.UNRESOLVED,
            reason="NO_MATCHING_ASSET",
        )

    def _name_candidates(self, name: str, market: str | None) -> tuple[UUID, ...]:
        candidates = set(self._lookup.list_ids_by_normalized_name(name, market))
        candidates.update(self._lookup.list_ids_by_normalized_alias(name, market))
        return self._sorted_ids(candidates)

    @staticmethod
    def _invalid_reason(reference: AssetReference) -> str | None:
        if reference.market_hint and normalize_market_hint(reference.market_hint) is None:
            return "UNSUPPORTED_MARKET_HINT"
        if reference.symbol_hint and reference.market_hint:
            embedded = normalize_asset_reference(
                AssetReference(symbol_hint=reference.symbol_hint)
            ).market
            explicit = normalize_market_hint(reference.market_hint)
            if embedded is not None and explicit is not None and embedded != explicit:
                return "CONFLICTING_MARKET_HINTS"
        return None

    @staticmethod
    def _sorted_ids(values: Iterable[UUID]) -> tuple[UUID, ...]:
        return tuple(sorted(set(values), key=lambda value: value.int))

    @staticmethod
    def _result(
        reference: AssetReference,
        normalized: NormalizedAssetReference,
        status: AssetResolutionStatus,
        *,
        asset_id: UUID | None = None,
        candidate_asset_ids: Iterable[UUID] = (),
        matched_by: str | None = None,
        reason: str | None = None,
    ) -> AssetResolutionResult:
        return AssetResolutionResult(
            status=status,
            reference=reference,
            asset_id=asset_id,
            candidate_asset_ids=AssetResolver._sorted_ids(candidate_asset_ids),
            matched_by=matched_by,
            reason=reason,
            normalized_name=normalized.name,
            normalized_symbol=normalized.symbol,
            normalized_market=normalized.market,
        )
