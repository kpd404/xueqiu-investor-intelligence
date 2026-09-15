from collections.abc import Collection
from uuid import UUID

from contracts import AssetRecoveryResult
from resolution.materialization import (
    AssetRecoveryNotFoundError,
    OpinionMaterializationService,
)


class AssetRecoveryService(OpinionMaterializationService):
    """Compatibility façade for callers migrating from mutable Asset recovery."""

    def recover(
        self,
        *,
        analysis_id: UUID | None = None,
        event_id: UUID | None = None,
        analysis_version: str | None = None,
        allowed_asset_ids: Collection[UUID] | None = None,
        allowed_market_symbols: Collection[tuple[str, str]] | None = None,
        dry_run: bool = False,
    ) -> AssetRecoveryResult:
        return self.materialize(
            analysis_id=analysis_id,
            event_id=event_id,
            analysis_version=analysis_version,
            allowed_asset_ids=allowed_asset_ids,
            allowed_market_symbols=allowed_market_symbols,
            dry_run=dry_run,
        )


__all__ = [
    "AssetRecoveryNotFoundError",
    "AssetRecoveryService",
    "OpinionMaterializationService",
]
