"""Source-neutral deterministic identity resolution services."""

from resolution.asset_resolver import AssetLookup, AssetResolver
from resolution.recovery import AssetRecoveryNotFoundError, AssetRecoveryService
from resolution.unresolved_audit import (
    AssetCatalogIdentity,
    UnresolvedReference,
    UnresolvedReferenceAggregate,
    UnresolvedReferenceBlocker,
    UnresolvedReferenceCategory,
    build_unresolved_inventory,
    classify_reference,
)

__all__ = [
    "AssetLookup",
    "AssetResolver",
    "AssetRecoveryNotFoundError",
    "AssetRecoveryService",
    "AssetCatalogIdentity",
    "UnresolvedReference",
    "UnresolvedReferenceAggregate",
    "UnresolvedReferenceBlocker",
    "UnresolvedReferenceCategory",
    "build_unresolved_inventory",
    "classify_reference",
]
