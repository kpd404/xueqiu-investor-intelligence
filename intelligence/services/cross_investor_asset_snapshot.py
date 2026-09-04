"""Build asset-centric, cross-investor evidence snapshots."""

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    CONSISTENCY_POLICY_VERSION,
    PRODUCTION_ATTENTION_POLICY_VERSION,
    PRODUCTION_THESIS_COMPARISON_VERSION,
    AttentionOccurrenceView,
    ConsistencyType,
    CrossInvestorAssetSnapshotCreate,
    CrossInvestorAssetSnapshotView,
    CrossInvestorContribution,
    EffectiveAnalysisPolicy,
    OpinionActionConsistencyView,
    OpinionDirection,
    OpinionTimelineEntry,
    PortfolioActionType,
    PortfolioActionView,
    PortfolioView,
    ThesisChangeType,
    ThesisChangeView,
    build_cross_investor_input_identity,
)
from contracts.cross_investor import CROSS_INVESTOR_POLICY_VERSION


class AttentionReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]: ...


class OpinionReader(Protocol):
    def list_effective_timeline_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> list[OpinionTimelineEntry]: ...


class ThesisChangeReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...


class PortfolioActionReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> list[PortfolioActionView]: ...


class PortfolioReader(Protocol):
    def list(self) -> list[PortfolioView]: ...


class ConsistencyReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        consistency_policy_version: str,
        as_of: datetime | None = None,
    ) -> list[OpinionActionConsistencyView]: ...


class SnapshotWriter(Protocol):
    def add_if_absent(
        self,
        snapshot: CrossInvestorAssetSnapshotCreate,
    ) -> tuple[CrossInvestorAssetSnapshotView, bool]: ...


class CrossInvestorAssetSnapshotUnitOfWork(Protocol):
    attention_occurrences: AttentionReader
    opinions: OpinionReader
    thesis_changes: ThesisChangeReader
    portfolio_actions: PortfolioActionReader
    portfolios: PortfolioReader
    consistencies: ConsistencyReader
    cross_investor_asset_snapshots: SnapshotWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


CrossInvestorAssetSnapshotUnitOfWorkFactory = Callable[[], CrossInvestorAssetSnapshotUnitOfWork]


class CrossInvestorAssetSnapshotService:
    """Aggregate only effective, versioned artifacts for one Asset window."""

    def __init__(
        self,
        unit_of_work_factory: CrossInvestorAssetSnapshotUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        *,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        thesis_comparison_version: str = PRODUCTION_THESIS_COMPARISON_VERSION,
        consistency_policy_version: str = CONSISTENCY_POLICY_VERSION,
        cross_investor_policy_version: str = CROSS_INVESTOR_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._attention_policy_version = attention_policy_version
        self._thesis_comparison_version = thesis_comparison_version
        self._consistency_policy_version = consistency_policy_version
        self._cross_investor_policy_version = cross_investor_policy_version

    @classmethod
    def from_production(
        cls,
        unit_of_work_factory: CrossInvestorAssetSnapshotUnitOfWorkFactory,
    ) -> "CrossInvestorAssetSnapshotService":
        """Compose the service from the application's explicit production policies."""

        from config import (
            get_production_analysis_policy,
            get_production_attention_policy_version,
            get_production_thesis_comparison_policy,
        )

        return cls(
            unit_of_work_factory,
            get_production_analysis_policy().as_effective_policy(),
            attention_policy_version=get_production_attention_policy_version(),
            thesis_comparison_version=get_production_thesis_comparison_policy().active_analysis_version,
            consistency_policy_version=CONSISTENCY_POLICY_VERSION,
        )

    def calculate(
        self,
        asset_id: UUID,
        window_start: datetime,
        window_end: datetime,
        *,
        as_of: datetime | None = None,
    ) -> CrossInvestorAssetSnapshotView:
        start = self._normalize_time(window_start, "window_start")
        end = self._normalize_time(window_end, "window_end")
        cutoff = self._normalize_time(as_of, "as_of") if as_of is not None else end
        if start > end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if cutoff < end:
            raise ValueError("as_of must be on or after window_end")

        # Data after window_end cannot affect a window aggregation. Limiting all
        # readers to this cutoff also prevents future leakage when as_of is later.
        reader_cutoff = end
        with self._unit_of_work_factory() as unit_of_work:
            attention_history = unit_of_work.attention_occurrences.list_effective_by_asset(
                asset_id,
                self._effective_analysis_policy,
                self._attention_policy_version,
                as_of=reader_cutoff,
            )
            attention = self._within(
                attention_history,
                start,
                end,
                lambda value: value.published_time,
            )
            opinions = self._within(
                unit_of_work.opinions.list_effective_timeline_by_asset(
                    asset_id,
                    self._effective_analysis_policy,
                    as_of=reader_cutoff,
                ),
                start,
                end,
                lambda value: value.published_time,
            )
            thesis_changes = self._within(
                unit_of_work.thesis_changes.list_effective_by_asset(
                    asset_id,
                    self._effective_analysis_policy,
                    self._thesis_comparison_version,
                    as_of=reader_cutoff,
                ),
                start,
                end,
                lambda value: value.effective_time,
            )
            portfolio_actions = self._within(
                unit_of_work.portfolio_actions.list_effective_by_asset(
                    asset_id,
                    as_of=reader_cutoff,
                ),
                start,
                end,
                lambda value: value.effective_time,
            )
            consistencies = self._within(
                unit_of_work.consistencies.list_effective_by_asset(
                    asset_id,
                    self._effective_analysis_policy,
                    consistency_policy_version=self._consistency_policy_version,
                    as_of=reader_cutoff,
                ),
                start,
                end,
                lambda value: value.effective_time,
            )
            portfolio_investors = {
                portfolio.id: portfolio.investor_id for portfolio in unit_of_work.portfolios.list()
            }

            contributions = self._build_contributions(
                attention=attention,
                attention_history=attention_history,
                opinions=opinions,
                thesis_changes=thesis_changes,
                portfolio_actions=portfolio_actions,
                portfolio_investors=portfolio_investors,
                consistencies=consistencies,
            )
            first_dependencies = self._first_attention_dependencies(
                attention_history,
                {item.investor_id for item in attention},
            )
            snapshot = CrossInvestorAssetSnapshotCreate(
                asset_id=asset_id,
                as_of=cutoff,
                window_start=start,
                window_end=end,
                attention_occurrence_count=len(attention),
                attention_investor_count=len({item.investor_id for item in attention}),
                new_attention_investor_count=sum(
                    dependency[2] >= start and dependency[2] <= end
                    for dependency in first_dependencies
                ),
                opinion_count=len(opinions),
                opinion_investor_count=len({item.investor_id for item in opinions}),
                bullish_investor_count=self._latest_direction_count(
                    opinions,
                    {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH},
                ),
                bearish_investor_count=self._latest_direction_count(
                    opinions,
                    {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH},
                ),
                neutral_investor_count=self._latest_direction_count(
                    opinions,
                    {OpinionDirection.NEUTRAL},
                ),
                thesis_change_count=len(thesis_changes),
                thesis_change_investor_count=len({item.investor_id for item in thesis_changes}),
                thesis_reinforced_investor_count=len(
                    {
                        item.investor_id
                        for item in thesis_changes
                        if item.change_type is ThesisChangeType.THESIS_REINFORCED
                    }
                ),
                thesis_changed_investor_count=len(
                    {
                        item.investor_id
                        for item in thesis_changes
                        if item.change_type is ThesisChangeType.THESIS_CHANGED
                    }
                ),
                portfolio_action_count=len(portfolio_actions),
                portfolio_action_investor_count=len(
                    {
                        portfolio_investors[action.portfolio_id]
                        for action in portfolio_actions
                        if action.portfolio_id in portfolio_investors
                    }
                ),
                position_increased_count=sum(
                    action.action_type is PortfolioActionType.POSITION_INCREASED
                    for action in portfolio_actions
                ),
                position_decreased_count=sum(
                    action.action_type is PortfolioActionType.POSITION_DECREASED
                    for action in portfolio_actions
                ),
                consistency_count=len(consistencies),
                consistency_investor_count=len({item.investor_id for item in consistencies}),
                positive_alignment_count=sum(
                    item.consistency_type is ConsistencyType.POSITIVE_ALIGNMENT
                    for item in consistencies
                ),
                negative_alignment_count=sum(
                    item.consistency_type is ConsistencyType.NEGATIVE_ALIGNMENT
                    for item in consistencies
                ),
                contributions=contributions,
                opinion_analysis_version=self._effective_analysis_policy.active_analysis_version,
                attention_policy_version=self._attention_policy_version,
                thesis_comparison_version=self._thesis_comparison_version,
                consistency_policy_version=self._consistency_policy_version,
                cross_investor_policy_version=self._cross_investor_policy_version,
                calculated_at=datetime.now(UTC),
                input_identity=build_cross_investor_input_identity(
                    asset_id=asset_id,
                    as_of=cutoff,
                    window_start=start,
                    window_end=end,
                    opinion_analysis_version=self._effective_analysis_policy.active_analysis_version,
                    attention_policy_version=self._attention_policy_version,
                    thesis_comparison_version=self._thesis_comparison_version,
                    consistency_policy_version=self._consistency_policy_version,
                    cross_investor_policy_version=self._cross_investor_policy_version,
                    attention_occurrence_ids=tuple(item.id for item in attention),
                    opinion_ids=tuple(item.opinion_id for item in opinions),
                    thesis_change_ids=tuple(item.id for item in thesis_changes),
                    portfolio_action_ids=tuple(item.id for item in portfolio_actions),
                    consistency_ids=tuple(item.id for item in consistencies),
                    first_attention_dependencies=first_dependencies,
                ),
            )
            persisted, _created = unit_of_work.cross_investor_asset_snapshots.add_if_absent(
                snapshot
            )
            unit_of_work.commit()
            return persisted

    def process(
        self,
        asset_id: UUID,
        window_start: datetime,
        window_end: datetime,
        *,
        as_of: datetime | None = None,
    ) -> CrossInvestorAssetSnapshotView:
        return self.calculate(asset_id, window_start, window_end, as_of=as_of)

    @staticmethod
    def _within(
        values: list[object],
        start: datetime,
        end: datetime,
        time_getter: Callable[[object], datetime],
    ) -> list[object]:
        return [
            value
            for value in values
            if start <= CrossInvestorAssetSnapshotService._utc(time_getter(value)) <= end
        ]

    @staticmethod
    def _latest_direction_count(
        opinions: list[OpinionTimelineEntry],
        directions: set[OpinionDirection],
    ) -> int:
        latest: dict[UUID, OpinionTimelineEntry] = {}
        for opinion in opinions:
            current = latest.get(opinion.investor_id)
            if current is None or CrossInvestorAssetSnapshotService._opinion_key(
                opinion
            ) > CrossInvestorAssetSnapshotService._opinion_key(current):
                latest[opinion.investor_id] = opinion
        return sum(opinion.direction in directions for opinion in latest.values())

    @staticmethod
    def _opinion_key(opinion: OpinionTimelineEntry) -> tuple[datetime, int, int]:
        return (
            CrossInvestorAssetSnapshotService._utc(opinion.published_time),
            opinion.event_id.int,
            opinion.opinion_id.int,
        )

    @classmethod
    def _first_attention_dependencies(
        cls,
        history: list[AttentionOccurrenceView],
        investor_ids: set[UUID],
    ) -> tuple[tuple[UUID, UUID, datetime], ...]:
        first_by_investor: dict[UUID, AttentionOccurrenceView] = {}
        for occurrence in history:
            if occurrence.investor_id not in investor_ids:
                continue
            current = first_by_investor.get(occurrence.investor_id)
            if current is None or (
                cls._utc(occurrence.published_time),
                occurrence.id.int,
            ) < (cls._utc(current.published_time), current.id.int):
                first_by_investor[occurrence.investor_id] = occurrence
        return tuple(
            (
                investor_id,
                occurrence.id,
                cls._utc(occurrence.published_time),
            )
            for investor_id, occurrence in sorted(
                first_by_investor.items(), key=lambda value: value[0].int
            )
        )

    @classmethod
    def _build_contributions(
        cls,
        *,
        attention: list[AttentionOccurrenceView],
        attention_history: list[AttentionOccurrenceView],
        opinions: list[OpinionTimelineEntry],
        thesis_changes: list[ThesisChangeView],
        portfolio_actions: list[PortfolioActionView],
        portfolio_investors: dict[UUID, UUID],
        consistencies: list[OpinionActionConsistencyView],
    ) -> tuple[CrossInvestorContribution, ...]:
        attention_by_investor: dict[UUID, list[AttentionOccurrenceView]] = defaultdict(list)
        for item in attention:
            attention_by_investor[item.investor_id].append(item)
        opinion_by_investor: dict[UUID, list[OpinionTimelineEntry]] = defaultdict(list)
        for item in opinions:
            opinion_by_investor[item.investor_id].append(item)
        thesis_by_investor: dict[UUID, list[ThesisChangeView]] = defaultdict(list)
        for item in thesis_changes:
            thesis_by_investor[item.investor_id].append(item)
        action_by_investor: dict[UUID, list[PortfolioActionView]] = defaultdict(list)
        for item in portfolio_actions:
            investor_id = portfolio_investors.get(item.portfolio_id)
            if investor_id is not None:
                action_by_investor[investor_id].append(item)
        consistency_by_investor: dict[UUID, list[OpinionActionConsistencyView]] = defaultdict(list)
        for item in consistencies:
            consistency_by_investor[item.investor_id].append(item)
        first_by_investor = cls._first_attention_dependencies(
            attention_history,
            set(attention_by_investor),
        )
        first_lookup = {item[0]: item for item in first_by_investor}
        investor_ids = (
            set(attention_by_investor)
            | set(opinion_by_investor)
            | set(thesis_by_investor)
            | set(action_by_investor)
            | set(consistency_by_investor)
        )
        contributions: list[CrossInvestorContribution] = []
        for investor_id in sorted(investor_ids, key=lambda value: value.int):
            attention_values = sorted(
                attention_by_investor.get(investor_id, []),
                key=lambda value: (cls._utc(value.published_time), value.id.int),
            )
            opinion_values = opinion_by_investor.get(investor_id, [])
            latest = max(opinion_values, key=cls._opinion_key) if opinion_values else None
            thesis_values = sorted(
                thesis_by_investor.get(investor_id, []),
                key=lambda value: (cls._utc(value.effective_time), value.id.int),
            )
            action_values = sorted(
                action_by_investor.get(investor_id, []),
                key=lambda value: (cls._utc(value.effective_time), value.id.int),
            )
            consistency_values = sorted(
                consistency_by_investor.get(investor_id, []),
                key=lambda value: (cls._utc(value.effective_time), value.id.int),
            )
            first = first_lookup.get(investor_id)
            contributions.append(
                CrossInvestorContribution(
                    investor_id=investor_id,
                    attention_occurrence_ids=tuple(item.id for item in attention_values),
                    attention_occurrence_count=len(attention_values),
                    first_attention_occurrence_id=first[1] if first else None,
                    first_attention_published_time=first[2] if first else None,
                    window_opinion_ids=tuple(
                        item.opinion_id for item in sorted(opinion_values, key=cls._opinion_key)
                    ),
                    window_opinion_count=len(opinion_values),
                    latest_window_opinion_id=latest.opinion_id if latest else None,
                    latest_window_opinion_direction=latest.direction if latest else None,
                    latest_window_opinion_time=(
                        cls._utc(latest.published_time) if latest else None
                    ),
                    thesis_change_ids=tuple(item.id for item in thesis_values),
                    thesis_change_types=tuple(item.change_type for item in thesis_values),
                    portfolio_action_ids=tuple(item.id for item in action_values),
                    portfolio_action_types=tuple(item.action_type for item in action_values),
                    consistency_ids=tuple(item.id for item in consistency_values),
                    consistency_types=tuple(item.consistency_type for item in consistency_values),
                )
            )
        return tuple(contributions)

    @staticmethod
    def _normalize_time(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["CrossInvestorAssetSnapshotService"]
