"""Deterministic, query-time Investor × Asset Thesis Evolution timelines.

The service keeps Opinion direction and ThesisChange semantics as independent
observations. It describes the currently observed effective sequence only and
never infers long-term belief, absence, conviction, quality, performance, or
investment action.
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    PRODUCTION_ATTENTION_POLICY_VERSION,
    PRODUCTION_THESIS_COMPARISON_VERSION,
    AttentionOccurrenceView,
    EffectiveAnalysisPolicy,
    OpinionDirection,
    ThesisChangeType,
    ThesisChangeView,
    ThesisComparisonStatus,
    ThesisEvolutionCompleteness,
    ThesisEvolutionDirectionTransition,
    ThesisEvolutionEntry,
    ThesisEvolutionOpinionView,
    ThesisEvolutionTimeline,
)


class ThesisEvolutionAssetView(Protocol):
    id: UUID
    name: str
    market: str
    symbol: str


class ThesisEvolutionInvestorView(Protocol):
    id: UUID
    name: str


class ThesisEvolutionAssetReader(Protocol):
    def get(self, asset_id: UUID) -> ThesisEvolutionAssetView | None: ...


class ThesisEvolutionInvestorReader(Protocol):
    def get(self, investor_id: UUID) -> ThesisEvolutionInvestorView | None: ...


class ThesisEvolutionOpinionReader(Protocol):
    def list_effective_evolution_timeline(
        self,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisEvolutionOpinionView]: ...

    def list_effective_evolution_timeline_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisEvolutionOpinionView]: ...


class ThesisEvolutionChangeReader(Protocol):
    def list_effective(
        self,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...

    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str | None = None,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...


class ThesisEvolutionAttentionReader(Protocol):
    def list_effective(
        self,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]: ...

    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        attention_policy_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[AttentionOccurrenceView]: ...


class ThesisEvolutionUnitOfWork(Protocol):
    assets: ThesisEvolutionAssetReader
    investors: ThesisEvolutionInvestorReader
    opinions: ThesisEvolutionOpinionReader
    thesis_changes: ThesisEvolutionChangeReader
    attention_occurrences: ThesisEvolutionAttentionReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


ThesisEvolutionUnitOfWorkFactory = Callable[[], ThesisEvolutionUnitOfWork]


class ThesisEvolutionAssetNotFoundError(LookupError):
    """Raised when a requested Asset cannot be found."""


class ThesisEvolutionInvestorNotFoundError(LookupError):
    """Raised when an effective Opinion references a missing Investor."""


class ThesisEvolutionService:
    """Build observed Opinion/Thesis timelines without persistence."""

    def __init__(
        self,
        unit_of_work_factory: ThesisEvolutionUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        *,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        thesis_comparison_version: str = PRODUCTION_THESIS_COMPARISON_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._attention_policy_version = attention_policy_version
        self._thesis_comparison_version = thesis_comparison_version

    @classmethod
    def from_production(
        cls,
        unit_of_work_factory: ThesisEvolutionUnitOfWorkFactory,
    ) -> "ThesisEvolutionService":
        """Compose the service from the explicit production policy source."""

        from config import (
            get_production_analysis_policy,
            get_production_attention_policy_version,
            get_production_thesis_comparison_policy,
        )

        return cls(
            unit_of_work_factory,
            get_production_analysis_policy().as_effective_policy(),
            attention_policy_version=get_production_attention_policy_version(),
            thesis_comparison_version=(
                get_production_thesis_comparison_policy().active_analysis_version
            ),
        )

    def get_thesis_timeline(
        self,
        investor_id: UUID,
        asset_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        *,
        include_attention_context: bool = False,
    ) -> ThesisEvolutionTimeline | None:
        """Return one Investor × Asset timeline, or None when no Opinion is observed."""

        start = self._normalize_optional_time(window_start, "window_start")
        end = self._normalize_optional_time(window_end, "window_end")
        self._validate_window(start, end)
        timelines = self._query_timelines(
            start=start,
            end=end,
            investor_id=investor_id,
            asset_id=asset_id,
            include_attention_context=include_attention_context,
        )
        return timelines[0] if timelines else None

    def list_thesis_timelines(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        min_opinions: int = 2,
        investor_id: UUID | None = None,
        asset_id: UUID | None = None,
        include_attention_context: bool = False,
    ) -> tuple[ThesisEvolutionTimeline, ...]:
        """Return observed timelines filtered by query-time Opinion count."""

        start = self._normalize_optional_time(window_start, "window_start")
        end = self._normalize_optional_time(window_end, "window_end")
        self._validate_window(start, end)
        if min_opinions < 1:
            raise ValueError("min_opinions must be at least 1")
        return tuple(
            timeline
            for timeline in self._query_timelines(
                start=start,
                end=end,
                investor_id=investor_id,
                asset_id=asset_id,
                include_attention_context=include_attention_context,
            )
            if timeline.opinion_count >= min_opinions
        )

    def _query_timelines(
        self,
        *,
        start: datetime | None,
        end: datetime | None,
        investor_id: UUID | None,
        asset_id: UUID | None,
        include_attention_context: bool,
    ) -> list[ThesisEvolutionTimeline]:
        with self._unit_of_work_factory() as unit_of_work:
            opinions = self._load_opinions(unit_of_work, asset_id, end)
            changes = self._load_changes(unit_of_work, asset_id, end)
            attention = (
                self._load_attention(unit_of_work, asset_id, end)
                if include_attention_context
                else []
            )
            return self._build_timelines(
                unit_of_work,
                opinions,
                changes,
                attention,
                start=start,
                end=end,
                investor_id=investor_id,
                asset_id=asset_id,
                include_attention_context=include_attention_context,
            )

    def _load_opinions(
        self,
        unit_of_work: ThesisEvolutionUnitOfWork,
        asset_id: UUID | None,
        end: datetime | None,
    ) -> list[ThesisEvolutionOpinionView]:
        if asset_id is None:
            return unit_of_work.opinions.list_effective_evolution_timeline(
                self._effective_analysis_policy,
                as_of=end,
            )
        return unit_of_work.opinions.list_effective_evolution_timeline_by_asset(
            asset_id,
            self._effective_analysis_policy,
            as_of=end,
        )

    def _load_changes(
        self,
        unit_of_work: ThesisEvolutionUnitOfWork,
        asset_id: UUID | None,
        end: datetime | None,
    ) -> list[ThesisChangeView]:
        if asset_id is None:
            return unit_of_work.thesis_changes.list_effective(
                self._effective_analysis_policy,
                self._thesis_comparison_version,
                as_of=end,
            )
        return unit_of_work.thesis_changes.list_effective_by_asset(
            asset_id,
            self._effective_analysis_policy,
            self._thesis_comparison_version,
            as_of=end,
        )

    def _load_attention(
        self,
        unit_of_work: ThesisEvolutionUnitOfWork,
        asset_id: UUID | None,
        end: datetime | None,
    ) -> list[AttentionOccurrenceView]:
        if asset_id is None:
            return unit_of_work.attention_occurrences.list_effective(
                self._effective_analysis_policy,
                self._attention_policy_version,
                as_of=end,
            )
        return unit_of_work.attention_occurrences.list_effective_by_asset(
            asset_id,
            self._effective_analysis_policy,
            self._attention_policy_version,
            as_of=end,
        )

    def _build_timelines(
        self,
        unit_of_work: ThesisEvolutionUnitOfWork,
        opinions: list[ThesisEvolutionOpinionView],
        changes: list[ThesisChangeView],
        attention: list[AttentionOccurrenceView],
        *,
        start: datetime | None,
        end: datetime | None,
        investor_id: UUID | None,
        asset_id: UUID | None,
        include_attention_context: bool,
    ) -> list[ThesisEvolutionTimeline]:
        all_by_pair: dict[tuple[UUID, UUID], list[ThesisEvolutionOpinionView]] = defaultdict(list)
        for opinion in opinions:
            if investor_id is not None and opinion.investor_id != investor_id:
                continue
            if asset_id is not None and opinion.asset_id != asset_id:
                continue
            all_by_pair[(opinion.investor_id, opinion.asset_id)].append(opinion)

        change_by_opinion: dict[UUID, ThesisChangeView] = {}
        for change in changes:
            if investor_id is not None and change.investor_id != investor_id:
                continue
            if asset_id is not None and change.asset_id != asset_id:
                continue
            if not self._within(change.effective_time, start, end):
                continue
            current = change_by_opinion.get(change.current_opinion_id)
            if current is None or self._thesis_key(change) > self._thesis_key(current):
                change_by_opinion[change.current_opinion_id] = change

        attention_by_pair: dict[tuple[UUID, UUID], list[AttentionOccurrenceView]] = defaultdict(
            list
        )
        if include_attention_context:
            for occurrence in attention:
                if investor_id is not None and occurrence.investor_id != investor_id:
                    continue
                if asset_id is not None and occurrence.asset_id != asset_id:
                    continue
                if self._within(occurrence.published_time, start, end):
                    attention_by_pair[(occurrence.investor_id, occurrence.asset_id)].append(
                        occurrence
                    )

        assets: dict[UUID, ThesisEvolutionAssetView] = {}
        investors: dict[UUID, ThesisEvolutionInvestorView] = {}
        timelines: list[ThesisEvolutionTimeline] = []
        for pair, values in all_by_pair.items():
            ordered_all = sorted(values, key=self._opinion_key)
            visible = [
                opinion
                for opinion in ordered_all
                if self._within(opinion.published_time, start, end)
            ]
            if not visible:
                continue
            current_investor_id, current_asset_id = pair
            asset = assets.get(current_asset_id)
            if asset is None:
                asset = unit_of_work.assets.get(current_asset_id)
                if asset is None:
                    raise ThesisEvolutionAssetNotFoundError(f"asset not found: {current_asset_id}")
                assets[current_asset_id] = asset
            investor = investors.get(current_investor_id)
            if investor is None:
                investor = unit_of_work.investors.get(current_investor_id)
                if investor is None:
                    raise ThesisEvolutionInvestorNotFoundError(
                        f"investor not found: {current_investor_id}"
                    )
                investors[current_investor_id] = investor

            predecessor_by_opinion: dict[UUID, ThesisEvolutionOpinionView | None] = {}
            predecessor: ThesisEvolutionOpinionView | None = None
            for opinion in ordered_all:
                predecessor_by_opinion[opinion.opinion_id] = predecessor
                predecessor = opinion

            entries: list[ThesisEvolutionEntry] = []
            previous_visible: ThesisEvolutionOpinionView | None = None
            for opinion in visible:
                change = change_by_opinion.get(opinion.opinion_id)
                expected_predecessor = predecessor_by_opinion[opinion.opinion_id]
                has_predecessor = expected_predecessor is not None
                comparison_status = (
                    ThesisComparisonStatus.INITIAL_OPINION
                    if not has_predecessor
                    else (
                        ThesisComparisonStatus.COMPARISON_AVAILABLE
                        if change is not None
                        else ThesisComparisonStatus.MISSING_THESIS_COMPARISON
                    )
                )
                gap_seconds = (
                    (
                        self._utc(opinion.published_time)
                        - self._utc(previous_visible.published_time)
                    ).total_seconds()
                    if previous_visible is not None
                    else None
                )
                direction_transition = self._direction_transition(
                    previous_visible.direction if previous_visible is not None else None,
                    opinion.direction,
                )
                entries.append(
                    ThesisEvolutionEntry(
                        opinion_id=opinion.opinion_id,
                        raw_event_id=opinion.raw_event_id,
                        event_analysis_id=opinion.event_analysis_id,
                        published_time=self._utc(opinion.published_time),
                        direction=opinion.direction,
                        strength=opinion.strength,
                        confidence=opinion.confidence,
                        thesis=opinion.thesis,
                        catalysts=opinion.catalysts,
                        risks=opinion.risks,
                        time_horizon=opinion.time_horizon,
                        thesis_change_id=change.id if change else None,
                        thesis_change_type=change.change_type if change else None,
                        thesis_change_time=(self._utc(change.effective_time) if change else None),
                        thesis_comparison_status=comparison_status,
                        predecessor_opinion_id=(
                            change.previous_opinion_id
                            if change is not None
                            else (
                                expected_predecessor.opinion_id
                                if expected_predecessor is not None
                                else None
                            )
                        ),
                        direction_transition=direction_transition,
                        temporal_gap_from_previous=gap_seconds,
                        temporal_gap_from_previous_hours=(
                            gap_seconds / 3600 if gap_seconds is not None else None
                        ),
                        temporal_gap_from_previous_days=(
                            gap_seconds / 86400 if gap_seconds is not None else None
                        ),
                    )
                )
                previous_visible = opinion

            first_attention = None
            if include_attention_context:
                pair_attention = attention_by_pair.get(pair, [])
                if pair_attention:
                    first_attention = min(
                        pair_attention,
                        key=lambda value: (
                            self._utc(value.published_time),
                            value.id.int,
                        ),
                    )
            first_time = entries[0].published_time
            attention_lag = (
                (self._utc(first_time) - self._utc(first_attention.published_time)).total_seconds()
                if first_attention is not None
                else None
            )
            change_types = [entry.thesis_change_type for entry in entries]
            timelines.append(
                ThesisEvolutionTimeline(
                    investor_id=current_investor_id,
                    investor_name=investor.name,
                    asset_id=current_asset_id,
                    asset_name=asset.name,
                    market=asset.market,
                    symbol=asset.symbol,
                    window_start=start or first_time,
                    window_end=end or entries[-1].published_time,
                    completeness=ThesisEvolutionCompleteness.UNKNOWN,
                    opinion_count=len(entries),
                    thesis_change_count=sum(
                        entry.thesis_change_id is not None for entry in entries
                    ),
                    missing_thesis_change_count=sum(
                        entry.thesis_comparison_status
                        is ThesisComparisonStatus.MISSING_THESIS_COMPARISON
                        for entry in entries
                    ),
                    first_opinion_time=first_time,
                    latest_opinion_time=entries[-1].published_time,
                    entries=tuple(entries),
                    changed_count=sum(
                        change_type is ThesisChangeType.THESIS_CHANGED
                        for change_type in change_types
                    ),
                    extended_count=sum(
                        change_type is ThesisChangeType.THESIS_EXTENDED
                        for change_type in change_types
                    ),
                    reinforced_count=sum(
                        change_type is ThesisChangeType.THESIS_REINFORCED
                        for change_type in change_types
                    ),
                    reversal_count=sum(
                        entry.direction_transition
                        in {
                            ThesisEvolutionDirectionTransition.BULLISH_TO_BEARISH,
                            ThesisEvolutionDirectionTransition.BEARISH_TO_BULLISH,
                        }
                        for entry in entries
                    ),
                    same_direction_change_count=sum(
                        entry.thesis_change_type is ThesisChangeType.THESIS_CHANGED
                        and entry.direction_transition
                        is ThesisEvolutionDirectionTransition.SAME_DIRECTION
                        for entry in entries
                    ),
                    first_attention_time=(
                        self._utc(first_attention.published_time)
                        if first_attention is not None
                        else None
                    ),
                    attention_to_first_opinion_lag=attention_lag,
                    attention_to_first_opinion_lag_hours=(
                        attention_lag / 3600 if attention_lag is not None else None
                    ),
                    attention_to_first_opinion_lag_days=(
                        attention_lag / 86400 if attention_lag is not None else None
                    ),
                )
            )

        return sorted(
            timelines,
            key=lambda value: (
                value.investor_name,
                value.asset_name,
                value.market,
                value.symbol,
                value.investor_id.int,
                value.asset_id.int,
            ),
        )

    @staticmethod
    def _direction_transition(
        previous: OpinionDirection | None,
        current: OpinionDirection,
    ) -> ThesisEvolutionDirectionTransition:
        if previous is None:
            return ThesisEvolutionDirectionTransition.INITIAL_DIRECTION
        previous_side = ThesisEvolutionService._direction_side(previous)
        current_side = ThesisEvolutionService._direction_side(current)
        if previous_side == current_side:
            return ThesisEvolutionDirectionTransition.SAME_DIRECTION
        if previous_side == "BULLISH" and current_side == "BEARISH":
            return ThesisEvolutionDirectionTransition.BULLISH_TO_BEARISH
        if previous_side == "BEARISH" and current_side == "BULLISH":
            return ThesisEvolutionDirectionTransition.BEARISH_TO_BULLISH
        if current_side is None:
            return ThesisEvolutionDirectionTransition.TO_NEUTRAL
        if previous_side is None:
            return ThesisEvolutionDirectionTransition.FROM_NEUTRAL
        return ThesisEvolutionDirectionTransition.OTHER

    @staticmethod
    def _direction_side(direction: OpinionDirection) -> str | None:
        if direction in {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}:
            return "BULLISH"
        if direction in {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}:
            return "BEARISH"
        return None

    @classmethod
    def _within(
        cls,
        value: datetime,
        start: datetime | None,
        end: datetime | None,
    ) -> bool:
        normalized = cls._utc(value)
        return (start is None or normalized >= start) and (end is None or normalized <= end)

    @staticmethod
    def _opinion_key(
        opinion: ThesisEvolutionOpinionView,
    ) -> tuple[datetime, int, int]:
        return (
            ThesisEvolutionService._utc(opinion.published_time),
            opinion.raw_event_id.int,
            opinion.opinion_id.int,
        )

    @staticmethod
    def _thesis_key(change: ThesisChangeView) -> tuple[datetime, int]:
        return (
            ThesisEvolutionService._utc(change.effective_time),
            change.id.int,
        )

    @staticmethod
    def _normalize_optional_time(value: datetime | None, field_name: str) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _validate_window(start: datetime | None, end: datetime | None) -> None:
        if start is not None and end is not None and start > end:
            raise ValueError("window_start must be earlier than or equal to window_end")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = [
    "ThesisEvolutionAssetNotFoundError",
    "ThesisEvolutionInvestorNotFoundError",
    "ThesisEvolutionService",
    "ThesisEvolutionUnitOfWork",
    "ThesisEvolutionUnitOfWorkFactory",
]
