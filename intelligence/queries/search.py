"""Batch, read-only search for Investors and listing-level Assets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from database.models.asset import Asset
from database.models.investor import Investor
from intelligence.schemas.intelligence import IntelligenceSearchEntity


class IntelligenceSearchReader(Protocol):
    def search(self, query: str) -> tuple[IntelligenceSearchEntity, ...]: ...


class SqlAlchemyIntelligenceSearchReader:
    """Execute two bounded identity queries, then merge deterministic results."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def search(self, query: str) -> tuple[IntelligenceSearchEntity, ...]:
        normalized = query.strip()
        if not normalized:
            raise ValueError("search query must not be blank")
        pattern = f"%{normalized}%"

        with self._session_factory() as session:
            assets = list(
                session.scalars(
                    select(Asset)
                    .where(
                        or_(
                            Asset.name.ilike(pattern),
                            Asset.market.ilike(pattern),
                            Asset.symbol.ilike(pattern),
                        )
                    )
                    .order_by(Asset.name, Asset.market, Asset.symbol, Asset.id)
                )
            )
            investors = list(
                session.scalars(
                    select(Investor)
                    .where(Investor.name.ilike(pattern))
                    .order_by(Investor.name, Investor.id)
                )
            )
            # Materialize immutable contracts before the read-only rollback
            # expires ORM instances.
            results = [
                IntelligenceSearchEntity(
                    entity_type="asset",
                    entity_id=asset.id,
                    name=asset.name,
                    market=asset.market,
                    symbol=asset.symbol,
                )
                for asset in assets
            ]
            results.extend(
                IntelligenceSearchEntity(
                    entity_type="investor",
                    entity_id=investor.id,
                    name=investor.name,
                )
                for investor in investors
            )
            session.rollback()
        return tuple(
            sorted(
                results,
                key=lambda item: (
                    item.name,
                    item.market or "",
                    item.symbol or "",
                    item.entity_type,
                    item.entity_id.int,
                ),
            )
        )


__all__ = ["IntelligenceSearchReader", "SqlAlchemyIntelligenceSearchReader"]
