"""Deterministic, query-time observed Attention temporal ordering.

The service describes presence and ordering in a monitored sample. It never
infers absence, history completeness, causality, influence, following, or
propagation success. It reads effective, version-selected artifacts through
ports and does not persist a derived edge or score.
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
    ObservedAttentionCompleteness,
    ObservedAttentionDirectionRelation,
    ObservedAttentionEdge,
    ObservedAttentionObservation,
    ObservedAttentionSequence,
    ObservedAttentionTemporalRelation,
    OpinionDirection,
    OpinionTimelineEntry,
    ThesisChangeView,
)


class ObservedAttentionAssetView(Protocol):
    id: UUID
    name: str
    market: str
    symbol: str


class ObservedAttentionInvestorView(Protocol):
    id: UUID
    name: str


class ObservedAttentionAssetReader(Protocol):
    def get(self, asset_id: UUID) -> ObservedAttentionAssetView | None: ...


class ObservedAttentionInvestorReader(Protocol):
    def get(self, investor_id: UUID) -> ObservedAttentionInvestorView | None: ...


class ObservedAttentionOccurrenceReader(Protocol):
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


class ObservedAttentionOpinionReader(Protocol):
    def list_effective_timeline_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        *,
        as_of: datetime | None = None,
    ) -> list[OpinionTimelineEntry]: ...


class ObservedAttentionThesisReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: EffectiveAnalysisPolicy,
        comparison_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list[ThesisChangeView]: ...


class ObservedAttentionUnitOfWork(Protocol):
    assets: ObservedAttentionAssetReader
    investors: ObservedAttentionInvestorReader
    attention_occurrences: ObservedAttentionOccurrenceReader
    opinions: ObservedAttentionOpinionReader
    thesis_changes: ObservedAttentionThesisReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


ObservedAttentionUnitOfWorkFactory = Callable[[], ObservedAttentionUnitOfWork]


class ObservedAttentionAssetNotFoundError(LookupError):
    """Raised when an explicitly requested Asset is not present."""


class ObservedAttentionInvestorNotFoundError(LookupError):
    """Raised when an effective occurrence references a missing Investor."""


class ObservedAttentionPropagationService:
    """Build observed Attention sequences and edges without persistence."""

    def __init__(
        self,
        unit_of_work_factory: ObservedAttentionUnitOfWorkFactory,
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
        unit_of_work_factory: ObservedAttentionUnitOfWorkFactory,
    ) -> "ObservedAttentionPropagationService":
        """Compose the service from the explicit production policy source."""

        from config import (
            get_production_analysis_policy,
            get_production_attention_policy_version,
        )

        return cls(
            unit_of_work_factory,
            get_production_analysis_policy().as_effective_policy(),
            attention_policy_version=get_production_attention_policy_version(),
        )

    def get_observed_attention_sequences(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        asset_id: UUID | None = None,
        min_investors: int = 2,
        include_thesis_context: bool = False,
    ) -> tuple[ObservedAttentionSequence, ...]:
        """Return one sequence per Asset meeting the query-time filter."""

        start = self._normalize_time(window_start, "window_start")
        end = self._normalize_time(window_end, "window_end")
        if start > end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if min_investors < 1:
            raise ValueError("min_investors must be at least 1")

        with self._unit_of_work_factory() as unit_of_work:
            if asset_id is not None and unit_of_work.assets.get(asset_id) is None:
                raise ObservedAttentionAssetNotFoundError(f"asset not found: {asset_id}")
            if asset_id is None:
                history = unit_of_work.attention_occurrences.list_effective(
                    self._effective_analysis_policy,
                    self._attention_policy_version,
                    as_of=end,
                )
            else:
                history = unit_of_work.attention_occurrences.list_effective_by_asset(
                    asset_id,
                    self._effective_analysis_policy,
                    self._attention_policy_version,
                    as_of=end,
                )
            occurrences = [
                value for value in history if start <= self._utc(value.published_time) <= end
            ]
            occurrences_by_asset: dict[UUID, list[AttentionOccurrenceView]] = defaultdict(list)
            for occurrence in occurrences:
                occurrences_by_asset[occurrence.asset_id].append(occurrence)

            sequences: list[ObservedAttentionSequence] = []
            for current_asset_id, asset_occurrences in occurrences_by_asset.items():
                first_by_investor = self._first_by_investor(asset_occurrences)
                if len(first_by_investor) < min_investors:
                    continue
                asset = unit_of_work.assets.get(current_asset_id)
                if asset is None:
                    raise ObservedAttentionAssetNotFoundError(
                        f"asset not found: {current_asset_id}"
                    )
                investors = {
                    investor_id: self._require_investor(unit_of_work, investor_id)
                    for investor_id in first_by_investor
                }
                first_opinions = self._first_opinions(
                    unit_of_work,
                    current_asset_id,
                    start,
                    end,
                )
                latest_thesis = (
                    self._latest_thesis_changes(
                        unit_of_work,
                        current_asset_id,
                        start,
                        end,
                    )
                    if include_thesis_context
                    else {}
                )
                ordered = sorted(
                    first_by_investor.values(),
                    key=lambda value: (
                        self._utc(value.published_time),
                        value.investor_id.int,
                        value.id.int,
                    ),
                )
                first = self._build_observation(
                    ordered[0],
                    investors[ordered[0].investor_id],
                    first_opinions.get(ordered[0].investor_id),
                    latest_thesis.get(ordered[0].investor_id),
                )
                later = tuple(
                    self._build_observation(
                        occurrence,
                        investors[occurrence.investor_id],
                        first_opinions.get(occurrence.investor_id),
                        latest_thesis.get(occurrence.investor_id),
                        lag_from=ordered[0].published_time,
                    )
                    for occurrence in ordered[1:]
                )
                sequences.append(
                    ObservedAttentionSequence(
                        asset_id=current_asset_id,
                        asset_name=asset.name,
                        market=asset.market,
                        symbol=asset.symbol,
                        window_start=start,
                        window_end=end,
                        completeness=ObservedAttentionCompleteness.UNKNOWN,
                        investor_count=len(ordered),
                        occurrence_count=len(asset_occurrences),
                        first_observed=first,
                        later_observations=later,
                    )
                )

        return tuple(
            sorted(
                sequences,
                key=lambda value: (
                    value.asset_name,
                    value.market,
                    value.symbol,
                    value.asset_id.int,
                ),
            )
        )

    def get_effective_attention_occurrences(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        asset_id: UUID | None = None,
    ) -> tuple[AttentionOccurrenceView, ...]:
        """Return effective Attention evidence for presentation-layer composition."""

        start = self._normalize_time(window_start, "window_start")
        end = self._normalize_time(window_end, "window_end")
        if start > end:
            raise ValueError("window_start must be earlier than or equal to window_end")

        with self._unit_of_work_factory() as unit_of_work:
            if asset_id is None:
                history = unit_of_work.attention_occurrences.list_effective(
                    self._effective_analysis_policy,
                    self._attention_policy_version,
                    as_of=end,
                )
            else:
                history = unit_of_work.attention_occurrences.list_effective_by_asset(
                    asset_id,
                    self._effective_analysis_policy,
                    self._attention_policy_version,
                    as_of=end,
                )
        return tuple(
            sorted(
                (value for value in history if start <= self._utc(value.published_time) <= end),
                key=lambda value: (self._utc(value.published_time), value.id.int),
            )
        )

    def get_observed_attention_edges(
        self,
        window_start: datetime,
        window_end: datetime,
        *,
        asset_id: UUID | None = None,
        min_investors: int = 2,
        include_thesis_context: bool = False,
    ) -> tuple[ObservedAttentionEdge, ...]:
        """Derive anchor-to-later edges from query-time sequences."""

        sequences = self.get_observed_attention_sequences(
            window_start,
            window_end,
            asset_id=asset_id,
            min_investors=min_investors,
            include_thesis_context=include_thesis_context,
        )
        return tuple(edge for sequence in sequences for edge in self.derive_edges(sequence))

    @staticmethod
    def derive_edges(sequence: ObservedAttentionSequence) -> tuple[ObservedAttentionEdge, ...]:
        """Derive one edge from the first observation to each other Investor."""

        first = sequence.first_observed
        edges: list[ObservedAttentionEdge] = []
        for later in sequence.later_observations:
            lag_seconds = max(
                0.0,
                (
                    ObservedAttentionPropagationService._utc(later.published_time)
                    - ObservedAttentionPropagationService._utc(first.published_time)
                ).total_seconds(),
            )
            simultaneous = later.published_time == first.published_time
            edges.append(
                ObservedAttentionEdge(
                    asset_id=sequence.asset_id,
                    asset_name=sequence.asset_name,
                    market=sequence.market,
                    symbol=sequence.symbol,
                    window_start=sequence.window_start,
                    window_end=sequence.window_end,
                    completeness=sequence.completeness,
                    earliest_observed_investor_id=first.investor_id,
                    earliest_observed_investor_name=first.investor_name,
                    later_observed_investor_id=later.investor_id,
                    later_observed_investor_name=later.investor_name,
                    earliest_time=first.published_time,
                    later_time=later.published_time,
                    lag_seconds=lag_seconds,
                    lag_hours=lag_seconds / 3600,
                    lag_days=lag_seconds / 86400,
                    earliest_evidence_types=first.evidence_types,
                    later_evidence_types=later.evidence_types,
                    direction_relation=ObservedAttentionPropagationService._direction_relation(
                        first.first_opinion_direction,
                        later.first_opinion_direction,
                    ),
                    temporal_relation=(
                        ObservedAttentionTemporalRelation.SIMULTANEOUS_OBSERVATION
                        if simultaneous
                        else ObservedAttentionTemporalRelation.OBSERVED_LATER
                    ),
                    earliest_attention_occurrence_id=first.attention_occurrence_id,
                    later_attention_occurrence_id=later.attention_occurrence_id,
                    earliest_raw_event_id=first.raw_event_id,
                    later_raw_event_id=later.raw_event_id,
                    earliest_first_effective_opinion_id=first.first_effective_opinion_id,
                    earliest_first_opinion_time=first.first_opinion_time,
                    earliest_first_opinion_direction=first.first_opinion_direction,
                    later_first_effective_opinion_id=later.first_effective_opinion_id,
                    later_first_opinion_time=later.first_opinion_time,
                    later_first_opinion_direction=later.first_opinion_direction,
                    earliest_latest_thesis_change_type=first.latest_thesis_change_type,
                    earliest_latest_thesis_change_time=first.latest_thesis_change_time,
                    later_latest_thesis_change_type=later.latest_thesis_change_type,
                    later_latest_thesis_change_time=later.latest_thesis_change_time,
                )
            )
        return tuple(edges)

    @staticmethod
    def _first_by_investor(
        occurrences: list[AttentionOccurrenceView],
    ) -> dict[UUID, AttentionOccurrenceView]:
        first_by_investor: dict[UUID, AttentionOccurrenceView] = {}
        for occurrence in sorted(
            occurrences,
            key=lambda value: (
                ObservedAttentionPropagationService._utc(value.published_time),
                value.id.int,
            ),
        ):
            first_by_investor.setdefault(occurrence.investor_id, occurrence)
        return first_by_investor

    def _first_opinions(
        self,
        unit_of_work: ObservedAttentionUnitOfWork,
        asset_id: UUID,
        start: datetime,
        end: datetime,
    ) -> dict[UUID, OpinionTimelineEntry]:
        first_by_investor: dict[UUID, OpinionTimelineEntry] = {}
        for opinion in unit_of_work.opinions.list_effective_timeline_by_asset(
            asset_id,
            self._effective_analysis_policy,
            as_of=end,
        ):
            published_time = self._utc(opinion.published_time)
            if not start <= published_time <= end:
                continue
            current = first_by_investor.get(opinion.investor_id)
            if current is None or self._opinion_key(opinion) < self._opinion_key(current):
                first_by_investor[opinion.investor_id] = opinion
        return first_by_investor

    def _latest_thesis_changes(
        self,
        unit_of_work: ObservedAttentionUnitOfWork,
        asset_id: UUID,
        start: datetime,
        end: datetime,
    ) -> dict[UUID, ThesisChangeView]:
        latest_by_investor: dict[UUID, ThesisChangeView] = {}
        for change in unit_of_work.thesis_changes.list_effective_by_asset(
            asset_id,
            self._effective_analysis_policy,
            self._thesis_comparison_version,
            as_of=end,
        ):
            effective_time = self._utc(change.effective_time)
            if not start <= effective_time <= end:
                continue
            current = latest_by_investor.get(change.investor_id)
            if current is None or self._thesis_key(change) > self._thesis_key(current):
                latest_by_investor[change.investor_id] = change
        return latest_by_investor

    @staticmethod
    def _build_observation(
        occurrence: AttentionOccurrenceView,
        investor: ObservedAttentionInvestorView,
        opinion: OpinionTimelineEntry | None,
        thesis_change: ThesisChangeView | None,
        *,
        lag_from: datetime | None = None,
    ) -> ObservedAttentionObservation:
        lag_seconds: float | None = None
        if lag_from is not None:
            lag_seconds = max(
                0.0,
                (
                    ObservedAttentionPropagationService._utc(occurrence.published_time)
                    - ObservedAttentionPropagationService._utc(lag_from)
                ).total_seconds(),
            )
        return ObservedAttentionObservation(
            investor_id=occurrence.investor_id,
            investor_name=investor.name,
            attention_occurrence_id=occurrence.id,
            raw_event_id=occurrence.event_id,
            published_time=ObservedAttentionPropagationService._utc(occurrence.published_time),
            evidence_types=tuple(occurrence.evidence_types),
            lag_seconds=lag_seconds,
            lag_hours=lag_seconds / 3600 if lag_seconds is not None else None,
            lag_days=lag_seconds / 86400 if lag_seconds is not None else None,
            first_effective_opinion_id=opinion.opinion_id if opinion else None,
            first_opinion_time=opinion.published_time if opinion else None,
            first_opinion_direction=opinion.direction if opinion else None,
            latest_thesis_change_type=thesis_change.change_type if thesis_change else None,
            latest_thesis_change_time=thesis_change.effective_time if thesis_change else None,
        )

    @staticmethod
    def _require_investor(
        unit_of_work: ObservedAttentionUnitOfWork,
        investor_id: UUID,
    ) -> ObservedAttentionInvestorView:
        investor = unit_of_work.investors.get(investor_id)
        if investor is None:
            raise ObservedAttentionInvestorNotFoundError(f"investor not found: {investor_id}")
        return investor

    @staticmethod
    def _direction_relation(
        earliest: OpinionDirection | None,
        later: OpinionDirection | None,
    ) -> ObservedAttentionDirectionRelation:
        if earliest is None or later is None:
            return ObservedAttentionDirectionRelation.OPINION_MISSING
        earliest_side = ObservedAttentionPropagationService._direction_side(earliest)
        later_side = ObservedAttentionPropagationService._direction_side(later)
        if earliest_side is None or later_side is None:
            return ObservedAttentionDirectionRelation.NEUTRAL_OR_MIXED
        if earliest_side == later_side:
            return ObservedAttentionDirectionRelation.SAME_DIRECTION
        return ObservedAttentionDirectionRelation.OPPOSITE_DIRECTION

    @staticmethod
    def _direction_side(direction: OpinionDirection) -> str | None:
        if direction in {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}:
            return "BULLISH"
        if direction in {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}:
            return "BEARISH"
        return None

    @staticmethod
    def _opinion_key(opinion: OpinionTimelineEntry) -> tuple[datetime, int, int]:
        return (
            ObservedAttentionPropagationService._utc(opinion.published_time),
            opinion.event_id.int,
            opinion.opinion_id.int,
        )

    @staticmethod
    def _thesis_key(change: ThesisChangeView) -> tuple[datetime, int]:
        return (
            ObservedAttentionPropagationService._utc(change.effective_time),
            change.id.int,
        )

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


__all__ = [
    "ObservedAttentionAssetNotFoundError",
    "ObservedAttentionInvestorNotFoundError",
    "ObservedAttentionPropagationService",
    "ObservedAttentionUnitOfWork",
    "ObservedAttentionUnitOfWorkFactory",
]
