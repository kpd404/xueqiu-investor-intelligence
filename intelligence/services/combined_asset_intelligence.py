"""Read-only composition of existing Asset intelligence evidence."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from types import TracebackType
from typing import Any, Protocol, Self
from uuid import UUID

from contracts import (
    CONSISTENCY_POLICY_VERSION,
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
    PRODUCTION_ATTENTION_POLICY_VERSION,
    PRODUCTION_THESIS_COMPARISON_VERSION,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    CombinedAssetAttentionSummary,
    CombinedAssetDataQuality,
    CombinedAssetIntelligenceView,
    CombinedAssetInvestorView,
    CombinedAssetTimelineEvent,
    CombinedAssetTimelineEventType,
    CombinedAttentionOpinionRelation,
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    CrossInvestorConsensusEvidenceView,
    EffectiveAnalysisPolicy,
    ObservedAttentionSequence,
    ThesisEvolutionTimeline,
)
from intelligence.services.observed_attention_propagation import (
    ObservedAttentionPropagationService,
)
from intelligence.services.thesis_evolution import ThesisEvolutionService


class CombinedAssetAssetView(Protocol):
    id: UUID
    name: str
    market: str
    symbol: str


class CombinedAssetRawEventReader(Protocol):
    def published_time_bounds(self) -> tuple[datetime | None, datetime | None]: ...


class CombinedAssetAssetReader(Protocol):
    def get(self, asset_id: UUID) -> CombinedAssetAssetView | None: ...


class CombinedAssetSnapshotReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> list[CrossInvestorAssetSnapshotView]: ...


class CombinedAssetAlignmentReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> list[CrossInvestorAssetAlignmentView]: ...


class CombinedAssetConsensusReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> list[CrossInvestorConsensusEvidenceView]: ...


class CombinedAssetUnitOfWork(Protocol):
    raw_events: CombinedAssetRawEventReader
    assets: CombinedAssetAssetReader
    cross_investor_asset_snapshots: CombinedAssetSnapshotReader
    cross_investor_asset_alignments: CombinedAssetAlignmentReader
    cross_investor_consensus_evidences: CombinedAssetConsensusReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


CombinedAssetUnitOfWorkFactory = Callable[[], CombinedAssetUnitOfWork]


class CombinedAssetNotFoundError(LookupError):
    """Raised when a requested Asset cannot be resolved."""


class CombinedAssetIntelligenceService:
    """Compose existing Attention, Thesis, and Cross-Investor read models."""

    def __init__(
        self,
        unit_of_work_factory: CombinedAssetUnitOfWorkFactory,
        effective_analysis_policy: EffectiveAnalysisPolicy,
        *,
        attention_policy_version: str = PRODUCTION_ATTENTION_POLICY_VERSION,
        thesis_comparison_version: str = PRODUCTION_THESIS_COMPARISON_VERSION,
        cross_investor_policy_version: str = CROSS_INVESTOR_POLICY_VERSION,
        alignment_policy_version: str = CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
        consensus_policy_version: str = CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
        consistency_policy_version: str = CONSISTENCY_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._effective_analysis_policy = effective_analysis_policy
        self._attention_policy_version = attention_policy_version
        self._thesis_comparison_version = thesis_comparison_version
        self._cross_investor_policy_version = cross_investor_policy_version
        self._alignment_policy_version = alignment_policy_version
        self._consensus_policy_version = consensus_policy_version
        self._consistency_policy_version = consistency_policy_version
        self._attention_service = ObservedAttentionPropagationService(
            unit_of_work_factory,
            effective_analysis_policy,
            attention_policy_version=attention_policy_version,
            thesis_comparison_version=thesis_comparison_version,
        )
        self._thesis_service = ThesisEvolutionService(
            unit_of_work_factory,
            effective_analysis_policy,
            attention_policy_version=attention_policy_version,
            thesis_comparison_version=thesis_comparison_version,
        )

    @classmethod
    def from_production(
        cls,
        unit_of_work_factory: CombinedAssetUnitOfWorkFactory,
    ) -> "CombinedAssetIntelligenceService":
        """Compose the view from the explicit production policies."""

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

    def get_asset_view(
        self,
        asset_id: UUID,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
    ) -> CombinedAssetIntelligenceView | None:
        """Return one Asset view, using the observed database bounds when omitted."""

        start, end = self._resolve_window(window_start, window_end)
        views = self._query_views(start, end, asset_id=asset_id)
        if not views or not views[0].investor_views:
            return None
        return views[0]

    def list_asset_views(
        self,
        window_start: datetime | None = None,
        window_end: datetime | None = None,
        *,
        min_attention_investors: int | None = None,
        min_opinion_investors: int | None = None,
    ) -> tuple[CombinedAssetIntelligenceView, ...]:
        """Return Asset views with query-only breadth filters."""

        start, end = self._resolve_window(window_start, window_end)
        if min_attention_investors is not None and min_attention_investors < 0:
            raise ValueError("min_attention_investors must be non-negative")
        if min_opinion_investors is not None and min_opinion_investors < 0:
            raise ValueError("min_opinion_investors must be non-negative")
        views = self._query_views(start, end)
        return tuple(
            view
            for view in views
            if (
                min_attention_investors is None
                or view.attention_summary.attention_investor_count >= min_attention_investors
            )
            and (
                min_opinion_investors is None
                or sum(item.opinion_count > 0 for item in view.investor_views)
                >= min_opinion_investors
            )
        )

    def _resolve_window(
        self,
        window_start: datetime | None,
        window_end: datetime | None,
    ) -> tuple[datetime, datetime]:
        start = self._normalize_optional_time(window_start, "window_start")
        end = self._normalize_optional_time(window_end, "window_end")
        if start is None or end is None:
            with self._unit_of_work_factory() as unit_of_work:
                observed_start, observed_end = unit_of_work.raw_events.published_time_bounds()
            if start is None:
                start = self._normalize_optional_time(observed_start, "database window_start")
            if end is None:
                end = self._normalize_optional_time(observed_end, "database window_end")
        if start is None or end is None:
            raise ValueError("an Asset view requires a non-empty observed database window")
        self._validate_window(start, end)
        return start, end

    def _query_views(
        self,
        start: datetime,
        end: datetime,
        *,
        asset_id: UUID | None = None,
    ) -> list[CombinedAssetIntelligenceView]:
        attention_occurrences = list(
            self._attention_service.get_effective_attention_occurrences(
                start,
                end,
                asset_id=asset_id,
            )
        )
        attention_sequences = list(
            self._attention_service.get_observed_attention_sequences(
                start,
                end,
                asset_id=asset_id,
                min_investors=1,
            )
        )
        thesis_timelines = list(
            self._thesis_service.list_thesis_timelines(
                start,
                end,
                min_opinions=1,
                asset_id=asset_id,
                include_attention_context=False,
            )
        )

        asset_ids = (
            {value.asset_id for value in attention_occurrences}
            | {value.asset_id for value in attention_sequences}
            | {value.asset_id for value in thesis_timelines}
        )
        if asset_id is not None:
            asset_ids.add(asset_id)
        attention_by_asset: dict[UUID, list[AttentionOccurrenceView]] = defaultdict(list)
        for occurrence in attention_occurrences:
            attention_by_asset[occurrence.asset_id].append(occurrence)
        sequence_by_asset = {value.asset_id: value for value in attention_sequences}
        thesis_by_asset: dict[UUID, list[ThesisEvolutionTimeline]] = defaultdict(list)
        for timeline in thesis_timelines:
            thesis_by_asset[timeline.asset_id].append(timeline)

        with self._unit_of_work_factory() as unit_of_work:
            views: list[CombinedAssetIntelligenceView] = []
            for current_asset_id in sorted(asset_ids, key=lambda value: value.int):
                asset = unit_of_work.assets.get(current_asset_id)
                if asset is None:
                    if asset_id == current_asset_id:
                        raise CombinedAssetNotFoundError(f"asset not found: {current_asset_id}")
                    continue
                cross_context = self._select_cross_context(
                    unit_of_work,
                    current_asset_id,
                    start,
                    end,
                    {value.id for value in attention_by_asset.get(current_asset_id, [])},
                )
                views.append(
                    self._build_view(
                        asset,
                        start,
                        end,
                        attention_by_asset.get(current_asset_id, []),
                        sequence_by_asset.get(current_asset_id),
                        thesis_by_asset.get(current_asset_id, []),
                        cross_context,
                    )
                )
        return sorted(
            views,
            key=lambda value: (
                value.asset_name,
                value.market,
                value.symbol,
                value.asset_id.int,
            ),
        )

    def _select_cross_context(
        self,
        unit_of_work: CombinedAssetUnitOfWork,
        asset_id: UUID,
        start: datetime,
        end: datetime,
        current_attention_ids: set[UUID],
    ) -> tuple[
        CrossInvestorAssetSnapshotView | None,
        CrossInvestorAssetAlignmentView | None,
        CrossInvestorConsensusEvidenceView | None,
    ]:
        snapshots = [
            value
            for value in unit_of_work.cross_investor_asset_snapshots.list_by_asset(asset_id)
            if (
                value.window_start == start
                and value.window_end == end
                and value.opinion_analysis_version
                == self._effective_analysis_policy.active_analysis_version
                and value.attention_policy_version == self._attention_policy_version
                and value.thesis_comparison_version == self._thesis_comparison_version
                and value.consistency_policy_version == self._consistency_policy_version
                and value.cross_investor_policy_version == self._cross_investor_policy_version
            )
        ]
        snapshot = self._latest(snapshots, "calculated_at")
        if snapshot is None:
            return None, None, None
        snapshot_attention_ids = {
            occurrence_id
            for contribution in snapshot.contributions
            for occurrence_id in contribution.attention_occurrence_ids
        }
        if snapshot_attention_ids != current_attention_ids:
            return None, None, None

        alignments = [
            value
            for value in unit_of_work.cross_investor_asset_alignments.list_by_asset(asset_id)
            if (
                value.source_snapshot_id == snapshot.id
                and value.alignment_policy_version == self._alignment_policy_version
            )
        ]
        alignment = self._latest(alignments, "calculated_at")
        if alignment is None:
            return snapshot, None, None

        consensus = self._latest(
            [
                value
                for value in unit_of_work.cross_investor_consensus_evidences.list_by_asset(asset_id)
                if (
                    value.source_snapshot_id == snapshot.id
                    and value.source_alignment_id == alignment.id
                    and value.consensus_policy_version == self._consensus_policy_version
                )
            ],
            "calculated_at",
        )
        return snapshot, alignment, consensus

    def _build_view(
        self,
        asset: CombinedAssetAssetView,
        start: datetime,
        end: datetime,
        attention: list[AttentionOccurrenceView],
        sequence: ObservedAttentionSequence | None,
        thesis_timelines: list[ThesisEvolutionTimeline],
        cross_context: tuple[
            CrossInvestorAssetSnapshotView | None,
            CrossInvestorAssetAlignmentView | None,
            CrossInvestorConsensusEvidenceView | None,
        ],
    ) -> CombinedAssetIntelligenceView:
        snapshot, alignment, consensus = cross_context
        attention = sorted(
            attention,
            key=lambda value: (self._utc(value.published_time), value.id.int),
        )
        thesis_by_investor = {value.investor_id: value for value in thesis_timelines}
        attention_by_investor: dict[UUID, list[AttentionOccurrenceView]] = defaultdict(list)
        for occurrence in attention:
            attention_by_investor[occurrence.investor_id].append(occurrence)

        names = {
            observation.investor_id: observation.investor_name
            for observation in (
                (sequence.first_observed, *sequence.later_observations)
                if sequence is not None
                else ()
            )
        }
        names.update({value.investor_id: value.investor_name for value in thesis_timelines})
        investor_ids = set(attention_by_investor) | set(thesis_by_investor)
        investor_views = tuple(
            sorted(
                (
                    self._build_investor_view(
                        investor_id,
                        names[investor_id],
                        attention_by_investor.get(investor_id, []),
                        thesis_by_investor.get(investor_id),
                    )
                    for investor_id in investor_ids
                ),
                key=lambda value: (value.investor_name, value.investor_id.int),
            )
        )
        summary = self._build_attention_summary(attention, names, sequence)
        data_quality = self._build_data_quality(investor_views, alignment, consensus)
        return CombinedAssetIntelligenceView(
            asset_id=asset.id,
            asset_name=asset.name,
            market=asset.market,
            symbol=asset.symbol,
            window_start=start,
            window_end=end,
            attention_summary=summary,
            observed_attention_sequence=sequence,
            investor_views=investor_views,
            alignment=alignment,
            consensus=consensus,
            data_quality=data_quality,
            event_timeline=self._build_event_timeline(
                attention,
                thesis_timelines,
                start,
                end,
                names,
            ),
        )

    def _build_investor_view(
        self,
        investor_id: UUID,
        investor_name: str,
        attention: list[AttentionOccurrenceView],
        thesis: ThesisEvolutionTimeline | None,
    ) -> CombinedAssetInvestorView:
        attention = sorted(
            attention,
            key=lambda value: (self._utc(value.published_time), value.id.int),
        )
        first_attention = attention[0] if attention else None
        latest_attention = attention[-1] if attention else None
        evidence_types = tuple(
            sorted(
                {evidence_type for value in attention for evidence_type in value.evidence_types},
                key=self._evidence_order,
            )
        )
        first_opinion = thesis.entries[0] if thesis is not None else None
        latest_opinion = thesis.entries[-1] if thesis is not None else None
        first_attention_time = (
            self._utc(first_attention.published_time) if first_attention else None
        )
        first_opinion_time = first_opinion.published_time if first_opinion else None
        relation, lag = self._attention_opinion_relation(
            first_attention,
            first_attention_time,
            first_opinion_time,
        )
        latest_change_type = None
        if thesis is not None:
            latest_change_type = next(
                (
                    entry.thesis_change_type
                    for entry in reversed(thesis.entries)
                    if entry.thesis_change_type is not None
                ),
                None,
            )
        return CombinedAssetInvestorView(
            investor_id=investor_id,
            investor_name=investor_name,
            first_attention_time=first_attention_time,
            latest_attention_time=(
                self._utc(latest_attention.published_time) if latest_attention else None
            ),
            attention_occurrence_count=len(attention),
            attention_evidence_types=evidence_types,
            first_attention_raw_event_id=first_attention.event_id if first_attention else None,
            opinion_count=thesis.opinion_count if thesis else 0,
            first_opinion_time=first_opinion_time,
            latest_opinion_time=thesis.latest_opinion_time if thesis else None,
            latest_observed_direction=latest_opinion.direction if latest_opinion else None,
            latest_observed_confidence=latest_opinion.confidence if latest_opinion else None,
            thesis_change_count=thesis.thesis_change_count if thesis else 0,
            latest_thesis_change_type=latest_change_type,
            reversal_count=thesis.reversal_count if thesis else 0,
            changed_count=thesis.changed_count if thesis else 0,
            extended_count=thesis.extended_count if thesis else 0,
            missing_thesis_comparison_count=(thesis.missing_thesis_change_count if thesis else 0),
            thesis_timeline=thesis,
            attention_opinion_relation=relation,
            attention_to_first_opinion_lag=lag,
            attention_to_first_opinion_lag_hours=lag / 3600 if lag is not None else None,
            attention_to_first_opinion_lag_days=lag / 86400 if lag is not None else None,
        )

    def _build_attention_summary(
        self,
        attention: list[AttentionOccurrenceView],
        names: dict[UUID, str],
        sequence: ObservedAttentionSequence | None,
    ) -> CombinedAssetAttentionSummary:
        if not attention:
            return CombinedAssetAttentionSummary(
                attention_investor_count=0,
                attention_occurrence_count=0,
                temporal_edges=(),
            )
        first = attention[0]
        span_seconds = (
            self._utc(attention[-1].published_time) - self._utc(first.published_time)
        ).total_seconds()
        return CombinedAssetAttentionSummary(
            attention_investor_count=len({value.investor_id for value in attention}),
            attention_occurrence_count=len(attention),
            earliest_observed_time=self._utc(first.published_time),
            earliest_observed_investor_id=first.investor_id,
            earliest_observed_investor_name=names.get(first.investor_id),
            observed_span_seconds=span_seconds,
            observed_span_hours=span_seconds / 3600,
            observed_span_days=span_seconds / 86400,
            temporal_edges=(
                ObservedAttentionPropagationService.derive_edges(sequence)
                if sequence is not None
                else ()
            ),
        )

    def _build_data_quality(
        self,
        investor_views: tuple[CombinedAssetInvestorView, ...],
        alignment: CrossInvestorAssetAlignmentView | None,
        consensus: CrossInvestorConsensusEvidenceView | None,
    ) -> CombinedAssetDataQuality:
        limitations = [
            "HISTORICAL_COMPLETENESS_UNKNOWN",
            "ABSENCE_INFERENCE_UNSUPPORTED",
            "LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY",
        ]
        if alignment is None or consensus is None:
            limitations.append("CROSS_INVESTOR_LINEAGE_UNAVAILABLE")
        missing_comparisons = sum(value.missing_thesis_comparison_count for value in investor_views)
        if missing_comparisons:
            limitations.append("MISSING_THESIS_COMPARISON")
        return CombinedAssetDataQuality(
            opinion_coverage=alignment.opinion_coverage_state if alignment else None,
            missing_thesis_comparison_count=missing_comparisons,
            cross_investor_evidence_available=alignment is not None and consensus is not None,
            unresolved_semantic_limitations=tuple(limitations),
        )

    def _build_event_timeline(
        self,
        attention: list[AttentionOccurrenceView],
        thesis_timelines: list[ThesisEvolutionTimeline],
        start: datetime,
        end: datetime,
        names: dict[UUID, str],
    ) -> tuple[CombinedAssetTimelineEvent, ...]:
        events: list[CombinedAssetTimelineEvent] = []
        first_by_investor: set[UUID] = set()
        opinion_by_id = {
            entry.opinion_id: entry for timeline in thesis_timelines for entry in timeline.entries
        }
        evidence_by_event: dict[UUID, tuple[AttentionEvidenceType, ...]] = {}
        for occurrence in attention:
            current = evidence_by_event.get(occurrence.event_id, ())
            evidence_by_event[occurrence.event_id] = self._merge_evidence_types(
                current,
                occurrence.evidence_types,
            )
        for occurrence in attention:
            is_first = occurrence.investor_id not in first_by_investor
            first_by_investor.add(occurrence.investor_id)
            opinion = opinion_by_id.get(occurrence.opinion_id) if occurrence.opinion_id else None
            events.append(
                CombinedAssetTimelineEvent(
                    published_time=self._utc(occurrence.published_time),
                    investor_id=occurrence.investor_id,
                    investor_name=names[occurrence.investor_id],
                    event_type=(
                        CombinedAssetTimelineEventType.ATTENTION_FIRST_OBSERVED
                        if is_first
                        else CombinedAssetTimelineEventType.ATTENTION_OBSERVED
                    ),
                    evidence_types=tuple(occurrence.evidence_types),
                    direction=opinion.direction if opinion else None,
                    attention_occurrence_id=occurrence.id,
                    opinion_id=occurrence.opinion_id,
                    event_analysis_id=occurrence.analysis_id,
                    raw_event_id=occurrence.event_id,
                )
            )
        for timeline in thesis_timelines:
            for entry in timeline.entries:
                evidence_types = evidence_by_event.get(entry.raw_event_id, ())
                events.append(
                    CombinedAssetTimelineEvent(
                        published_time=entry.published_time,
                        investor_id=timeline.investor_id,
                        investor_name=timeline.investor_name,
                        event_type=CombinedAssetTimelineEventType.OPINION_OBSERVED,
                        evidence_types=evidence_types,
                        direction=entry.direction,
                        opinion_id=entry.opinion_id,
                        event_analysis_id=entry.event_analysis_id,
                        raw_event_id=entry.raw_event_id,
                    )
                )
                if entry.thesis_change_id is not None:
                    events.append(
                        CombinedAssetTimelineEvent(
                            published_time=entry.thesis_change_time or entry.published_time,
                            investor_id=timeline.investor_id,
                            investor_name=timeline.investor_name,
                            event_type=CombinedAssetTimelineEventType.THESIS_CHANGE_OBSERVED,
                            evidence_types=evidence_types,
                            direction=entry.direction,
                            thesis_change_type=entry.thesis_change_type,
                            opinion_id=entry.opinion_id,
                            event_analysis_id=entry.event_analysis_id,
                            raw_event_id=entry.raw_event_id,
                            thesis_change_id=entry.thesis_change_id,
                            predecessor_opinion_id=entry.predecessor_opinion_id,
                        )
                    )
        return tuple(
            sorted(
                (event for event in events if start <= self._utc(event.published_time) <= end),
                key=self._event_key,
            )
        )

    def _attention_opinion_relation(
        self,
        first_attention: AttentionOccurrenceView | None,
        first_attention_time: datetime | None,
        first_opinion_time: datetime | None,
    ) -> tuple[CombinedAttentionOpinionRelation, float | None]:
        if first_attention_time is None and first_opinion_time is None:
            raise ValueError("an Investor view must have Attention or Opinion evidence")
        if first_attention_time is None:
            return CombinedAttentionOpinionRelation.OPINION_WITHOUT_PRIOR_ATTENTION, None
        if first_opinion_time is None:
            return CombinedAttentionOpinionRelation.ATTENTION_WITHOUT_OPINION, None
        lag = (self._utc(first_opinion_time) - first_attention_time).total_seconds()
        if lag == 0:
            if (
                first_attention is not None
                and AttentionEvidenceType.OPINION in first_attention.evidence_types
            ):
                return CombinedAttentionOpinionRelation.OPINION_AT_FIRST_ATTENTION, lag
            return CombinedAttentionOpinionRelation.SIMULTANEOUS, lag
        if lag > 0:
            return CombinedAttentionOpinionRelation.OPINION_AFTER_ATTENTION, lag
        return CombinedAttentionOpinionRelation.OPINION_WITHOUT_PRIOR_ATTENTION, lag

    @staticmethod
    def _merge_evidence_types(
        left: Iterable[AttentionEvidenceType],
        right: Iterable[AttentionEvidenceType],
    ) -> tuple[AttentionEvidenceType, ...]:
        order = {
            AttentionEvidenceType.OPINION: 0,
            AttentionEvidenceType.EXPLICIT_MENTION: 1,
            AttentionEvidenceType.REPOST: 2,
        }
        return tuple(sorted(set(left) | set(right), key=order.__getitem__))

    @staticmethod
    def _evidence_order(value: AttentionEvidenceType) -> int:
        return {
            AttentionEvidenceType.OPINION: 0,
            AttentionEvidenceType.EXPLICIT_MENTION: 1,
            AttentionEvidenceType.REPOST: 2,
        }[value]

    @staticmethod
    def _event_key(
        event: CombinedAssetTimelineEvent,
    ) -> tuple[datetime, int, int, int, int]:
        event_order = {
            CombinedAssetTimelineEventType.ATTENTION_FIRST_OBSERVED: 0,
            CombinedAssetTimelineEventType.ATTENTION_OBSERVED: 1,
            CombinedAssetTimelineEventType.OPINION_OBSERVED: 2,
            CombinedAssetTimelineEventType.THESIS_CHANGE_OBSERVED: 3,
        }
        item_id = (
            event.attention_occurrence_id
            or event.opinion_id
            or event.thesis_change_id
            or UUID(int=0)
        )
        return (
            CombinedAssetIntelligenceService._utc(event.published_time),
            event_order[event.event_type],
            event.investor_id.int,
            item_id.int,
            event.raw_event_id.int if event.raw_event_id else 0,
        )

    @staticmethod
    def _latest(values: list[Any], time_field: str) -> Any | None:
        if not values:
            return None
        return max(
            values,
            key=lambda value: (
                CombinedAssetIntelligenceService._utc(getattr(value, time_field)),
                value.id.int,
            ),
        )

    @staticmethod
    def _normalize_time(value: datetime, field_name: str) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError(f"{field_name} must be timezone-aware")
        return value.astimezone(UTC)

    @staticmethod
    def _normalize_optional_time(
        value: datetime | None,
        field_name: str,
    ) -> datetime | None:
        if value is None:
            return None
        return CombinedAssetIntelligenceService._normalize_time(value, field_name)

    @staticmethod
    def _validate_window(start: datetime, end: datetime) -> None:
        if start > end:
            raise ValueError("window_start must be earlier than or equal to window_end")

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = [
    "CombinedAssetIntelligenceService",
    "CombinedAssetUnitOfWork",
    "CombinedAssetUnitOfWorkFactory",
    "CombinedAssetNotFoundError",
]
