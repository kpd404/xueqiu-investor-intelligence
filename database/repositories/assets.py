from collections import defaultdict
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contracts import AssetMentionAlias, AssetMentionCandidate
from database.models.asset import Asset
from database.models.asset_alias import AssetAlias


class AssetRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, asset_id: UUID) -> Asset | None:
        return self._session.get(Asset, asset_id)

    def get_by_market_symbol(self, market: str, symbol: str) -> Asset | None:
        statement = select(Asset).where(
            func.upper(Asset.market) == market.strip().upper(),
            func.upper(Asset.symbol) == symbol.strip().upper(),
        )
        matches = list(self._session.scalars(statement))
        return matches[0] if len(matches) == 1 else None

    def list_ids_by_market_symbol(self, market: str, symbol: str) -> tuple[UUID, ...]:
        statement = (
            select(Asset.id)
            .where(
                func.upper(Asset.market) == market.strip().upper(),
                func.upper(Asset.symbol) == symbol.strip().upper(),
            )
            .order_by(Asset.id)
        )
        return tuple(self._session.scalars(statement))

    def list_ids_by_normalized_alias(
        self, normalized_alias: str, market: str | None = None
    ) -> tuple[UUID, ...]:
        statement = select(AssetAlias.asset_id).where(
            func.upper(AssetAlias.normalized_alias) == normalized_alias.strip().upper()
        )
        if market is None:
            statement = statement.where(AssetAlias.market.is_(None))
        else:
            statement = statement.where(
                AssetAlias.market.is_(None)
                | (func.upper(AssetAlias.market) == market.strip().upper())
            )
        statement = statement.order_by(AssetAlias.asset_id)
        return tuple(sorted(set(self._session.scalars(statement)), key=lambda value: value.int))

    def list_mention_candidates(self) -> tuple[AssetMentionCandidate, ...]:
        aliases_by_asset: dict[UUID, list[AssetMentionAlias]] = defaultdict(list)
        for alias in self._session.scalars(
            select(AssetAlias).order_by(AssetAlias.asset_id, AssetAlias.normalized_alias)
        ):
            aliases_by_asset[alias.asset_id].append(
                AssetMentionAlias(text=alias.alias, alias_type=alias.alias_type)
            )
        return tuple(
            AssetMentionCandidate(
                asset_id=asset.id,
                canonical_name=asset.name,
                aliases=tuple(aliases_by_asset[asset.id]),
            )
            for asset in self._session.scalars(select(Asset).order_by(Asset.id))
        )
