from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from database.models.asset import Asset


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
