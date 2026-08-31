from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
        if market is not None:
            statement = statement.where(
                AssetAlias.market.is_(None)
                | (func.upper(AssetAlias.market) == market.strip().upper())
            )
        statement = statement.order_by(AssetAlias.asset_id)
        return tuple(sorted(set(self._session.scalars(statement)), key=lambda value: value.int))

    def list_ids_by_normalized_name(
        self, normalized_name: str, market: str | None = None
    ) -> tuple[UUID, ...]:
        statement = select(Asset.id).where(
            func.upper(Asset.name) == normalized_name.strip().upper()
        )
        if market is not None:
            statement = statement.where(func.upper(Asset.market) == market.strip().upper())
        statement = statement.order_by(Asset.id)
        return tuple(self._session.scalars(statement))
