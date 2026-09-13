"""FastAPI dependencies for read-only intelligence services."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.session import SessionFactory
from database.unit_of_work import SqlAlchemyObservedAttentionUnitOfWork
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
)


def _read_only_session() -> Session:
    """Open a request UoW session with a PostgreSQL read-only transaction."""

    session = SessionFactory()
    try:
        if session.get_bind().dialect.name == "postgresql":
            session.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY"))
            session.execute(text("SET LOCAL TIME ZONE 'Asia/Hong_Kong'"))
            session.execute(text("SET LOCAL statement_timeout = '60000'"))
    except Exception:
        session.close()
        raise
    return session


def get_combined_asset_intelligence_service() -> CombinedAssetIntelligenceService:
    """Compose the Combined View with a rollback-only UoW factory."""

    def unit_of_work_factory() -> SqlAlchemyObservedAttentionUnitOfWork:
        return SqlAlchemyObservedAttentionUnitOfWork(_read_only_session)

    return CombinedAssetIntelligenceService.from_production(unit_of_work_factory)
