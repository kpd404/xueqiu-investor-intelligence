"""Application service for deterministic Investor Behavior Snapshots."""

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from behavior.contracts import (
    BEHAVIOR_SNAPSHOT_POLICY_VERSION,
    InvestorBehaviorSnapshotCreate,
    InvestorBehaviorSnapshotView,
    build_behavior_snapshot_input_identity,
)
from contracts import (
    CONSISTENCY_POLICY_VERSION,
    PRODUCTION_ATTENTION_POLICY_VERSION,
    AttentionOccurrenceView,
    ConsistencyType,
    EffectiveAnalysisPolicy,
    OpinionActionConsistencyView,
    OpinionDirection,
    OpinionTimelineEntry,
    PortfolioActionType,
    PortfolioActionView,
    ThesisChangeType,
    ThesisChangeView,
)


class OpinionReader(Protocol):
    def list_effective_timeline_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
    ) -> list[OpinionTimelineEntry]: ...


class AttentionReader(Protocol):
    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]: ...


class ThesisChangeReader(Protocol):
    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...


class PortfolioActionReader(Protocol):
    def list_effective_by_investor(
        self,
        investor_id: UUID,
        *,
        as_of: datetime | None = None,
    ) -> list[PortfolioActionView]: ...


class ConsistencyReader(Protocol):
    def list_effective_by_investor(
        self,
        investor_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        consistency_policy_version: str | None = CONSISTENCY_POLICY_VERSION,
        as_of: datetime | None = None,
    ) -> list[OpinionActionConsistencyView]: ...


class SnapshotWriter(Protocol):
    def add_if_absent(
        self,
        snapshot: InvestorBehaviorSnapshotCreate,
    ) -> tuple[InvestorBehaviorSnapshotView, bool]: ...


class BehaviorSnapshotUnitOfWork(Protocol):
    opinions: OpinionReader
    attention_occurrences: AttentionReader
    thesis_changes: ThesisChangeReader
    portfolio_actions: PortfolioActionReader
    consistencies: ConsistencyReader
    behavior_snapshots: SnapshotWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


BehaviorSnapshotUnitOfWorkFactory = Callable[[], BehaviorSnapshotUnitOfWork]


class InvestorBehaviorSnapshotService:
    """Aggregate active, fact-time artifacts into one immutable window snapshot."""

    def __init__(
        self,
        unit_of_work_factory: BehaviorSnapshotUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        *,
        behavior_policy_version: str = BEHAVIOR_SNAPSHOT_POLICY_VERSION,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        thesis_comparison_version: str | None = None,
        consistency_policy_version: str | None = CONSISTENCY_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._behavior_policy_version = behavior_policy_version
        self._attention_policy_version = attention_policy_version
        self._thesis_comparison_version = thesis_comparison_version
        self._consistency_policy_version = consistency_policy_version

    def calculate(
        self,
        investor_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> InvestorBehaviorSnapshotView:
        normalized_start = self._normalize_time(window_start, field_name="window_start")
        normalized_end = self._normalize_time(window_end, field_name="window_end")
        if normalized_start > normalized_end:
            raise ValueError("window_start must be earlier than or equal to window_end")

        with self._unit_of_work_factory() as unit_of_work:
            attention_history = [
                occurrence
                for occurrence in unit_of_work.attention_occurrences.list_effective_by_investor(
                    investor_id,
                    self._effective_analysis_policy,
                    self._attention_policy_version,
                    as_of=normalized_end,
                )
                if occurrence.published_time.astimezone(UTC) <= normalized_end
            ]
            attention = self._within(
                attention_history,
                normalized_start,
                normalized_end,
                time_getter=lambda item: item.published_time,
            )
            window_asset_ids = {item.asset_id for item in attention}
            relevant_attention_history = [
                occurrence
                for occurrence in attention_history
                if occurrence.asset_id in window_asset_ids
            ]
            opinions = self._within(
                unit_of_work.opinions.list_effective_timeline_by_investor(
                    investor_id,
                    self._effective_analysis_policy,
                ),
                normalized_start,
                normalized_end,
                time_getter=lambda item: item.published_time,
            )
            thesis_changes = self._within(
                unit_of_work.thesis_changes.list_effective_by_investor(
                    investor_id,
                    self._effective_analysis_policy,
                    self._thesis_comparison_version,
                ),
                normalized_start,
                normalized_end,
                time_getter=lambda item: item.effective_time,
            )
            portfolio_actions = self._within(
                unit_of_work.portfolio_actions.list_effective_by_investor(
                    investor_id,
                    as_of=normalized_end,
                ),
                normalized_start,
                normalized_end,
                time_getter=lambda item: item.effective_time,
            )
            consistencies = self._within(
                unit_of_work.consistencies.list_effective_by_investor(
                    investor_id,
                    self._effective_analysis_policy,
                    consistency_policy_version=self._consistency_policy_version,
                    as_of=normalized_end,
                ),
                normalized_start,
                normalized_end,
                time_getter=lambda item: item.effective_time,
            )

            snapshot = InvestorBehaviorSnapshotCreate(
                investor_id=investor_id,
                as_of=normalized_end,
                window_start=normalized_start,
                window_end=normalized_end,
                attention_asset_count=len({item.asset_id for item in attention}),
                attention_occurrence_count=len(attention),
                new_attention_count=self._new_attention_count(
                    relevant_attention_history,
                    attention,
                ),
                opinion_count=len(opinions),
                bullish_count=sum(
                    item.direction in {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}
                    for item in opinions
                ),
                bearish_count=sum(
                    item.direction in {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}
                    for item in opinions
                ),
                thesis_change_count=len(thesis_changes),
                thesis_reinforced_count=sum(
                    item.change_type is ThesisChangeType.THESIS_REINFORCED
                    for item in thesis_changes
                ),
                thesis_changed_count=sum(
                    item.change_type is ThesisChangeType.THESIS_CHANGED for item in thesis_changes
                ),
                portfolio_action_count=len(portfolio_actions),
                position_increased_count=sum(
                    item.action_type is PortfolioActionType.POSITION_INCREASED
                    for item in portfolio_actions
                ),
                position_decreased_count=sum(
                    item.action_type is PortfolioActionType.POSITION_DECREASED
                    for item in portfolio_actions
                ),
                positive_alignment_count=sum(
                    item.consistency_type is ConsistencyType.POSITIVE_ALIGNMENT
                    for item in consistencies
                ),
                negative_alignment_count=sum(
                    item.consistency_type is ConsistencyType.NEGATIVE_ALIGNMENT
                    for item in consistencies
                ),
                active_analysis_version=self._effective_analysis_policy.active_analysis_version,
                thesis_comparison_version=self._thesis_comparison_version,
                consistency_policy_version=self._consistency_policy_version,
                attention_policy_version=self._attention_policy_version,
                behavior_policy_version=self._behavior_policy_version,
                calculated_at=datetime.now(UTC),
                input_identity=self._input_identity(
                    investor_id,
                    normalized_start,
                    normalized_end,
                    # Window occurrences are direct inputs. Facts before the
                    # window are represented only by the first-attention
                    # dependency below, avoiding unrelated history churn.
                    attention_ids=tuple(item.id for item in attention),
                    attention_first_dependencies=self._first_attention_dependencies(
                        relevant_attention_history
                    ),
                    opinion_ids=tuple(item.opinion_id for item in opinions),
                    thesis_change_ids=tuple(item.id for item in thesis_changes),
                    portfolio_action_ids=tuple(item.id for item in portfolio_actions),
                    consistency_ids=tuple(item.id for item in consistencies),
                ),
            )
            persisted, _created = unit_of_work.behavior_snapshots.add_if_absent(snapshot)
            unit_of_work.commit()
            return persisted

    def process(
        self,
        investor_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> InvestorBehaviorSnapshotView:
        """Compatibility alias for application callers using process terminology."""

        return self.calculate(investor_id, window_start, window_end)

    def build(
        self,
        investor_id: UUID,
        window_start: datetime,
        window_end: datetime,
    ) -> InvestorBehaviorSnapshotView:
        """Compatibility alias for other derived-artifact services."""

        return self.calculate(investor_id, window_start, window_end)

    @staticmethod
    def _within(
        values: list[object],
        start: datetime,
        end: datetime,
        *,
        time_getter: Callable[[object], datetime],
    ) -> list[object]:
        return [value for value in values if start <= time_getter(value).astimezone(UTC) <= end]

    @staticmethod
    def _new_attention_count(
        all_history: list[AttentionOccurrenceView],
        window_values: list[AttentionOccurrenceView],
    ) -> int:
        if not window_values:
            return 0
        first_by_asset: dict[UUID, datetime] = {}
        for occurrence in all_history:
            published_time = occurrence.published_time.astimezone(UTC)
            first_by_asset[occurrence.asset_id] = min(
                first_by_asset.get(occurrence.asset_id, published_time),
                published_time,
            )
        window_assets = {item.asset_id for item in window_values}
        return sum(
            any(
                occurrence.asset_id == asset_id
                and occurrence.published_time.astimezone(UTC) == first_by_asset[asset_id]
                for occurrence in window_values
            )
            for asset_id in window_assets
        )

    def _input_identity(
        self,
        investor_id: UUID,
        window_start: datetime,
        window_end: datetime,
        *,
        attention_ids: tuple[UUID, ...],
        attention_first_dependencies: tuple[tuple[UUID, UUID, datetime], ...],
        opinion_ids: tuple[UUID, ...],
        thesis_change_ids: tuple[UUID, ...],
        portfolio_action_ids: tuple[UUID, ...],
        consistency_ids: tuple[UUID, ...],
    ) -> str:
        return build_behavior_snapshot_input_identity(
            investor_id=investor_id,
            window_start=window_start,
            window_end=window_end,
            behavior_policy_version=self._behavior_policy_version,
            active_analysis_version=self._effective_analysis_policy.active_analysis_version,
            thesis_comparison_version=self._thesis_comparison_version,
            consistency_policy_version=self._consistency_policy_version,
            attention_policy_version=self._attention_policy_version,
            attention_occurrence_ids=attention_ids,
            attention_first_dependencies=attention_first_dependencies,
            opinion_ids=opinion_ids,
            thesis_change_ids=thesis_change_ids,
            portfolio_action_ids=portfolio_action_ids,
            consistency_ids=consistency_ids,
        )

    @staticmethod
    def _normalize_time(value: datetime, *, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _first_attention_dependencies(
        history: list[AttentionOccurrenceView],
    ) -> tuple[tuple[UUID, UUID, datetime], ...]:
        first_by_asset: dict[UUID, AttentionOccurrenceView] = {}
        for occurrence in history:
            current = first_by_asset.get(occurrence.asset_id)
            if current is None or (
                occurrence.published_time,
                occurrence.id.int,
            ) < (current.published_time, current.id.int):
                first_by_asset[occurrence.asset_id] = occurrence
        return tuple(
            (
                asset_id,
                occurrence.id,
                occurrence.published_time,
            )
            for asset_id, occurrence in sorted(
                first_by_asset.items(), key=lambda value: value[0].int
            )
        )


__all__ = ["InvestorBehaviorSnapshotService"]
