"""FastAPI dependencies for read-only intelligence services."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from database.session import SessionFactory
from database.unit_of_work import SqlAlchemyObservedAttentionUnitOfWork
from intelligence.context.service import IntelligenceContextService
from intelligence.discovery.service import IntelligenceDiscoveryService
from intelligence.evolution.service import IntelligenceEvolutionService
from intelligence.feed.query import IntelligenceFeedQueryService
from intelligence.narrative.service import IntelligenceNarrativeService
from intelligence.patterns.service import IntelligencePatternService
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
)
from intelligence.services.intelligence_service import IntelligenceQueryService
from intelligence.services.investor_intelligence import InvestorIntelligenceService


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


def get_investor_intelligence_service() -> InvestorIntelligenceService:
    """Compose Investor views from the same rollback-only production read scope."""

    def unit_of_work_factory() -> SqlAlchemyObservedAttentionUnitOfWork:
        return SqlAlchemyObservedAttentionUnitOfWork(_read_only_session)

    return InvestorIntelligenceService.from_production(unit_of_work_factory)


def get_intelligence_query_service() -> IntelligenceQueryService:
    # Compose the Query Layer with rollback-only read scopes.

    def unit_of_work_factory() -> SqlAlchemyObservedAttentionUnitOfWork:
        return SqlAlchemyObservedAttentionUnitOfWork(_read_only_session)

    return IntelligenceQueryService.from_production(
        unit_of_work_factory,
        _read_only_session,
    )


def get_intelligence_feed_query_service() -> IntelligenceFeedQueryService:
    """Compose the Feed Query Layer with a rollback-only read scope."""

    from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

    def unit_of_work_factory() -> SqlAlchemyIntelligenceFeedUnitOfWork:
        return SqlAlchemyIntelligenceFeedUnitOfWork(_read_only_session)

    return IntelligenceFeedQueryService(unit_of_work_factory)


def get_intelligence_discovery_service() -> IntelligenceDiscoveryService:
    """Compose Discovery from the same rollback-only production read scope."""

    from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

    def unit_of_work_factory() -> SqlAlchemyIntelligenceFeedUnitOfWork:
        return SqlAlchemyIntelligenceFeedUnitOfWork(_read_only_session)

    return IntelligenceDiscoveryService(unit_of_work_factory)


def get_intelligence_narrative_service() -> IntelligenceNarrativeService:
    """Compose Narratives over the existing read-only Discovery service."""

    return IntelligenceNarrativeService(get_intelligence_discovery_service())


def get_intelligence_context_service() -> IntelligenceContextService:
    """Compose Context over the existing read-only Discovery service."""

    return IntelligenceContextService.from_production(
        SessionFactory,
    )


def get_intelligence_pattern_service() -> IntelligencePatternService:
    """Compose Patterns over the existing read-only Context service."""

    return IntelligencePatternService.from_production(SessionFactory)


def get_intelligence_evolution_service() -> IntelligenceEvolutionService:
    """Compose Evolution over the existing read-only Intelligence layers."""

    return IntelligenceEvolutionService.from_production(SessionFactory)
