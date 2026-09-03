from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from contracts import PortfolioDTO, PortfolioStatus, PortfolioView
from database.models.portfolio import Portfolio


class PortfolioRepository:
    """Persistence adapter for independently identified portfolios."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, portfolio: PortfolioDTO) -> PortfolioView:
        entity = Portfolio(
            investor_id=portfolio.investor_id,
            source=portfolio.source,
            external_id=portfolio.external_id,
            name=portfolio.name,
            status=portfolio.status,
            created_at=portfolio.created_at,
            updated_at=portfolio.updated_at,
        )
        self._session.add(entity)
        self._session.flush()
        return self._to_view(entity)

    def get(self, portfolio_id: UUID) -> PortfolioView | None:
        entity = self._session.get(Portfolio, portfolio_id)
        return self._to_view(entity) if entity is not None else None

    def get_by_identity(self, source: str, external_id: str) -> PortfolioView | None:
        statement = select(Portfolio).where(
            Portfolio.source == source.strip().lower(),
            Portfolio.external_id == external_id.strip(),
        )
        entity = self._session.scalar(statement)
        return self._to_view(entity) if entity is not None else None

    def list(
        self,
        *,
        investor_id: UUID | None = None,
        status: PortfolioStatus | None = None,
    ) -> list[PortfolioView]:
        statement = select(Portfolio)
        if investor_id is not None:
            statement = statement.where(Portfolio.investor_id == investor_id)
        if status is not None:
            statement = statement.where(Portfolio.status == status)
        statement = statement.order_by(Portfolio.id)
        return [self._to_view(entity) for entity in self._session.scalars(statement)]

    def upsert(self, portfolio: PortfolioDTO) -> PortfolioView:
        statement = select(Portfolio).where(
            Portfolio.source == portfolio.source,
            Portfolio.external_id == portfolio.external_id,
        )
        entity = self._session.scalar(statement)
        if entity is None:
            return self.create(portfolio)

        if entity.investor_id != portfolio.investor_id:
            raise ValueError("portfolio identity cannot move between investors")
        entity.name = portfolio.name
        entity.status = portfolio.status
        entity.updated_at = portfolio.updated_at
        self._session.flush()
        return self._to_view(entity)

    @classmethod
    def _to_view(cls, entity: Portfolio) -> PortfolioView:
        return PortfolioView(
            id=entity.id,
            investor_id=entity.investor_id,
            source=entity.source,
            external_id=entity.external_id,
            name=entity.name,
            status=entity.status,
            created_at=cls._as_utc(entity.created_at),
            updated_at=cls._as_utc(entity.updated_at),
        )

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
