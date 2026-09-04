from collections.abc import Callable
from types import TracebackType

from sqlalchemy.orm import Session

from database.repositories import (
    AssetRepository,
    AttentionOccurrenceRepository,
    CrossInvestorAssetAlignmentRepository,
    CrossInvestorAssetSnapshotRepository,
    EventAnalysisRepository,
    InvestorActionClaimRepository,
    InvestorActionConsistencyRepository,
    InvestorAssetStateChangeRepository,
    InvestorAssetStateRepository,
    InvestorBehaviorSnapshotRepository,
    InvestorRepository,
    OpinionRepository,
    PortfolioActionRepository,
    PortfolioRepository,
    PortfolioSnapshotBatchRepository,
    PositionSnapshotRepository,
    RawEventRepository,
    ThesisChangeRepository,
)
from resolution import AssetResolver


class SqlAlchemyOpinionUnitOfWork:
    """Short-lived repository scope used before and after extractor calls."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyOpinionUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.raw_events = RawEventRepository(self._session)
        self.assets = AssetRepository(self._session)
        self.asset_resolver = AssetResolver(self.assets)
        self.analyses = EventAnalysisRepository(self._session)
        self.opinions = OpinionRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()


class SqlAlchemyThesisChangeUnitOfWork:
    """Short-lived repository scope for Thesis Change comparison artifacts."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyThesisChangeUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.raw_events = RawEventRepository(self._session)
        self.opinions = OpinionRepository(self._session)
        self.thesis_changes = ThesisChangeRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


class SqlAlchemyPortfolioUnitOfWork:
    """Transactional scope for the independent Portfolio Fact repositories."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyPortfolioUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.portfolios = PortfolioRepository(self._session)
        self.assets = AssetRepository(self._session)
        self.asset_resolver = AssetResolver(self.assets)
        self.portfolio_snapshot_batches = PortfolioSnapshotBatchRepository(self._session)
        self.position_snapshots = PositionSnapshotRepository(self._session)
        self.portfolio_actions = PortfolioActionRepository(self._session)
        self.investor_action_claims = InvestorActionClaimRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


class SqlAlchemyConsistencyUnitOfWork:
    """Transactional scope for Opinion × PortfolioAction consistency analysis."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyConsistencyUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.opinions = OpinionRepository(self._session)
        self.portfolio_actions = PortfolioActionRepository(self._session)
        self.consistencies = InvestorActionConsistencyRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


class SqlAlchemyBehaviorSnapshotUnitOfWork:
    """Transactional scope for Behavior Snapshot aggregation inputs and output."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyBehaviorSnapshotUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.opinions = OpinionRepository(self._session)
        self.attention_occurrences = AttentionOccurrenceRepository(self._session)
        self.thesis_changes = ThesisChangeRepository(self._session)
        self.portfolio_actions = PortfolioActionRepository(self._session)
        self.consistencies = InvestorActionConsistencyRepository(self._session)
        self.behavior_snapshots = InvestorBehaviorSnapshotRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


# Keep the shorter name available for application callers following the
# existing domain UoW naming convention.
SqlAlchemyBehaviorUnitOfWork = SqlAlchemyBehaviorSnapshotUnitOfWork


class SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork:
    """Read/write scope for asset-centric cross-investor snapshots."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.attention_occurrences = AttentionOccurrenceRepository(self._session)
        self.opinions = OpinionRepository(self._session)
        self.thesis_changes = ThesisChangeRepository(self._session)
        self.portfolio_actions = PortfolioActionRepository(self._session)
        self.portfolios = PortfolioRepository(self._session)
        self.consistencies = InvestorActionConsistencyRepository(self._session)
        self.cross_investor_asset_snapshots = CrossInvestorAssetSnapshotRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


class SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork:
    """Read/write scope for alignment artifacts derived from snapshots."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.cross_investor_asset_snapshots = CrossInvestorAssetSnapshotRepository(self._session)
        self.cross_investor_asset_alignments = CrossInvestorAssetAlignmentRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


# Keep the shorter name available for application callers using the
# cross-investor domain naming convention.
SqlAlchemyCrossInvestorAlignmentUnitOfWork = SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork


class SqlAlchemyAttentionUnitOfWork:
    """Transactional scope for rebuilding derived AttentionOccurrence rows."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyAttentionUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.raw_events = RawEventRepository(self._session)
        self.assets = AssetRepository(self._session)
        self.asset_resolver = AssetResolver(self.assets)
        self.opinions = OpinionRepository(self._session)
        self.attention_occurrences = AttentionOccurrenceRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True


class SqlAlchemyStateUnitOfWork:
    """Transactional repository scope for deterministic state rebuilding."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None
        self._committed = False

    def __enter__(self) -> "SqlAlchemyStateUnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        self.opinions = OpinionRepository(self._session)
        self.states = InvestorAssetStateRepository(self._session)
        self.state_changes = InvestorAssetStateChangeRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        if exc_type is not None or not self._committed:
            self._session.rollback()
        self._session.close()
        self._session = None

    def commit(self) -> None:
        if self._session is None:
            raise RuntimeError("unit of work is not active")
        self._session.commit()
        self._committed = True

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()


class SqlAlchemyIntelligenceUnitOfWork:
    """Read-only repository scope for an asset intelligence calculation."""

    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> "SqlAlchemyIntelligenceUnitOfWork":
        self._session = self._session_factory()
        self.assets = AssetRepository(self._session)
        self.investors = InvestorRepository(self._session)
        self.opinions = OpinionRepository(self._session)
        self.states = InvestorAssetStateRepository(self._session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._session is None:
            return
        self._session.rollback()
        self._session.close()
        self._session = None
