from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from contracts import (
    CONSISTENCY_POLICY_VERSION,
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
    AnalysisSpec,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    CombinedAssetTimelineEventType,
    CombinedAttentionOpinionRelation,
    ConsensusEvidenceState,
    ConsensusInvestorContribution,
    CrossInvestorAssetAlignmentView,
    CrossInvestorConsensusEvidenceView,
    EffectiveAnalysisPolicy,
    OpinionCoverageState,
    OpinionDirection,
    OpinionTimelineEntry,
    ThesisChangeType,
    ThesisChangeView,
    ThesisEvolutionOpinionView,
)
from intelligence.services.combined_asset_intelligence import (
    CombinedAssetIntelligenceService,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
ATTENTION_POLICY = "attention-occurrence-v1"
THESIS_VERSION = "thesis-test"
POLICY = EffectiveAnalysisPolicy(active_spec=AnalysisSpec.from_model_version("combined-view-test"))


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _asset(asset_id: UUID, name: str = "Test Asset", market: str = "SH", symbol: str = "600000"):
    return SimpleNamespace(id=asset_id, name=name, market=market, symbol=symbol)


def _investor(investor_id: UUID, name: str):
    return SimpleNamespace(id=investor_id, name=name)


def _attention(
    occurrence_id: int,
    investor_id: UUID,
    asset_id: UUID,
    published_time: datetime,
    evidence_type: AttentionEvidenceType,
    *,
    opinion_id: UUID | None = None,
    analysis_id: UUID | None = None,
) -> AttentionOccurrenceView:
    return AttentionOccurrenceView(
        id=_uuid(occurrence_id),
        investor_id=investor_id,
        asset_id=asset_id,
        event_id=_uuid(occurrence_id + 1000),
        published_time=published_time,
        evidence_types=(evidence_type,),
        evidence=(
            AttentionEvidence(
                evidence_type=evidence_type,
                matched_by="test",
            ),
        ),
        analysis_id=analysis_id,
        opinion_id=opinion_id,
        attention_policy_version=ATTENTION_POLICY,
        calculated_at=published_time,
    )


def _opinion(
    opinion_id: int,
    investor_id: UUID,
    asset_id: UUID,
    published_time: datetime,
    direction: OpinionDirection,
) -> tuple[OpinionTimelineEntry, ThesisEvolutionOpinionView]:
    raw_event_id = _uuid(opinion_id + 1000)
    analysis_id = _uuid(opinion_id + 2000)
    timeline = OpinionTimelineEntry(
        opinion_id=_uuid(opinion_id),
        event_id=raw_event_id,
        investor_id=investor_id,
        asset_id=asset_id,
        direction=direction,
        strength=80,
        confidence=0.9,
        published_time=published_time,
        generated_time=published_time,
    )
    evolution = ThesisEvolutionOpinionView(
        opinion_id=_uuid(opinion_id),
        raw_event_id=raw_event_id,
        event_analysis_id=analysis_id,
        investor_id=investor_id,
        asset_id=asset_id,
        analysis_version=POLICY.active_analysis_version,
        published_time=published_time,
        direction=direction,
        strength=80,
        confidence=0.9,
        thesis=("existing thesis",),
        catalysts=("existing catalyst",),
        risks=("existing risk",),
        time_horizon="LONG_TERM",
    )
    return timeline, evolution


def _change(
    change_id: int,
    current_opinion_id: int,
    investor_id: UUID,
    asset_id: UUID,
    effective_time: datetime,
    change_type: ThesisChangeType,
    previous_opinion_id: int | None = None,
) -> ThesisChangeView:
    return ThesisChangeView(
        id=_uuid(change_id),
        investor_id=investor_id,
        asset_id=asset_id,
        previous_opinion_id=(
            _uuid(previous_opinion_id) if previous_opinion_id is not None else None
        ),
        current_opinion_id=_uuid(current_opinion_id),
        previous_event_id=(
            _uuid(previous_opinion_id + 1000) if previous_opinion_id is not None else None
        ),
        current_event_id=_uuid(current_opinion_id + 1000),
        effective_time=effective_time,
        change_type=change_type,
        confidence=0.9,
        summary="existing comparison",
        evidence=("existing evidence",),
        opinion_analysis_version=POLICY.active_analysis_version,
        comparison_version=THESIS_VERSION,
        calculated_at=effective_time,
        input_identity=f"{change_id:064x}",
    )


class _Reader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective(self, *args, **kwargs):
        return list(self.values)

    def list_effective_by_asset(self, asset_id, *args, **kwargs):
        return [value for value in self.values if value.asset_id == asset_id]

    def list_by_asset(self, asset_id):
        return [value for value in self.values if value.asset_id == asset_id]


class _EvolutionOpinionReader(_Reader):
    def __init__(self, values, timeline_values):
        super().__init__(values)
        self.timeline_values = list(timeline_values)

    def list_effective_evolution_timeline(self, *args, **kwargs):
        return list(self.values)

    def list_effective_evolution_timeline_by_asset(self, asset_id, *args, **kwargs):
        return [value for value in self.values if value.asset_id == asset_id]

    def list_effective_timeline_by_asset(self, asset_id, *args, **kwargs):
        return [value for value in self.timeline_values if value.asset_id == asset_id]


class _RawEvents:
    def published_time_bounds(self):
        return START, START + timedelta(days=10)


class _UnitOfWork:
    def __init__(
        self,
        assets,
        investors,
        attention,
        opinion_timelines,
        evolution_opinions,
        changes,
        snapshots=(),
        alignments=(),
        consensus=(),
    ):
        self.raw_events = _RawEvents()
        self.assets = {value.id: value for value in assets}
        self.investors = {value.id: value for value in investors}
        self.attention_occurrences = _Reader(attention)
        self.opinions = _EvolutionOpinionReader(evolution_opinions, opinion_timelines)
        self.thesis_changes = _Reader(changes)
        self.cross_investor_asset_snapshots = _Reader(snapshots)
        self.cross_investor_asset_alignments = _Reader(alignments)
        self.cross_investor_consensus_evidences = _Reader(consensus)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def _cross_context(asset_id: UUID, investor_one: UUID, investor_two: UUID):
    snapshot = SimpleNamespace(
        id=_uuid(900),
        asset_id=asset_id,
        window_start=START,
        window_end=START + timedelta(days=3),
        opinion_analysis_version=POLICY.active_analysis_version,
        attention_policy_version=ATTENTION_POLICY,
        thesis_comparison_version=THESIS_VERSION,
        consistency_policy_version=CONSISTENCY_POLICY_VERSION,
        cross_investor_policy_version=CROSS_INVESTOR_POLICY_VERSION,
        calculated_at=START + timedelta(days=3),
        contributions=(
            SimpleNamespace(attention_occurrence_ids=(_uuid(10),)),
            SimpleNamespace(attention_occurrence_ids=(_uuid(11),)),
        ),
    )
    alignment = CrossInvestorAssetAlignmentView(
        id=_uuid(901),
        asset_id=asset_id,
        source_snapshot_id=snapshot.id,
        opinion_coverage_state=OpinionCoverageState.COMPLETE,
        directional_alignment_state="MIXED_DIRECTION",
        alignment_policy_version=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
        input_identity="a" * 64,
        calculated_at=START + timedelta(days=3),
        created_at=START + timedelta(days=3),
    )
    consensus = CrossInvestorConsensusEvidenceView(
        id=_uuid(902),
        asset_id=asset_id,
        source_snapshot_id=snapshot.id,
        source_alignment_id=alignment.id,
        attention_investor_count=2,
        opinion_investor_count=2,
        bullish_investor_count=1,
        bearish_investor_count=1,
        neutral_investor_count=0,
        opinion_coverage_state=OpinionCoverageState.COMPLETE,
        consensus_state=ConsensusEvidenceState.INSUFFICIENT_EVIDENCE,
        contributing_investor_ids=(investor_one, investor_two),
        latest_opinions=(
            ConsensusInvestorContribution(
                investor_id=investor_one,
                window_opinion_count=1,
                latest_opinion_id=_uuid(101),
                latest_opinion_direction=OpinionDirection.BULLISH,
            ),
            ConsensusInvestorContribution(
                investor_id=investor_two,
                window_opinion_count=1,
                latest_opinion_id=_uuid(102),
                latest_opinion_direction=OpinionDirection.BEARISH,
            ),
        ),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
        input_identity="b" * 64,
        calculated_at=START + timedelta(days=3),
        created_at=START + timedelta(days=3),
    )
    return snapshot, alignment, consensus


def _service(uow):
    return CombinedAssetIntelligenceService(
        lambda: uow,
        POLICY,
        attention_policy_version=ATTENTION_POLICY,
        thesis_comparison_version=THESIS_VERSION,
    )


def test_composes_attention_thesis_and_existing_cross_investor_context() -> None:
    asset_id = _uuid(1)
    investor_one, investor_two = _uuid(11), _uuid(12)
    attention = [
        _attention(
            10,
            investor_one,
            asset_id,
            START,
            AttentionEvidenceType.OPINION,
            opinion_id=_uuid(101),
            analysis_id=_uuid(201),
        ),
        _attention(
            11,
            investor_two,
            asset_id,
            START + timedelta(days=1),
            AttentionEvidenceType.EXPLICIT_MENTION,
        ),
    ]
    first_opinion, first_evolution = _opinion(
        101, investor_one, asset_id, START, OpinionDirection.BULLISH
    )
    second_opinion, second_evolution = _opinion(
        102,
        investor_two,
        asset_id,
        START + timedelta(days=1),
        OpinionDirection.BEARISH,
    )
    changes = [
        _change(201, 101, investor_one, asset_id, START, ThesisChangeType.NEW_THESIS),
        _change(
            202,
            102,
            investor_two,
            asset_id,
            START + timedelta(days=1),
            ThesisChangeType.THESIS_CHANGED,
            101,
        ),
    ]
    snapshot, alignment, consensus = _cross_context(asset_id, investor_one, investor_two)
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_one, "one"), _investor(investor_two, "two")],
        attention,
        [first_opinion, second_opinion],
        [first_evolution, second_evolution],
        changes,
        [snapshot],
        [alignment],
        [consensus],
    )

    view = _service(uow).get_asset_view(asset_id, START, START + timedelta(days=3))

    assert view is not None
    assert view.attention_summary.attention_investor_count == 2
    assert view.attention_summary.attention_occurrence_count == 2
    assert view.observed_attention_sequence is not None
    assert [item.investor_name for item in view.observed_attention_sequence.later_observations] == [
        "two"
    ]
    assert view.attention_summary.temporal_edges[0].direction_relation.value == "OPPOSITE_DIRECTION"
    assert view.alignment == alignment
    assert view.consensus == consensus
    assert view.data_quality.opinion_coverage is OpinionCoverageState.COMPLETE
    assert view.data_quality.cross_investor_evidence_available
    assert [item.attention_opinion_relation for item in view.investor_views] == [
        CombinedAttentionOpinionRelation.OPINION_AT_FIRST_ATTENTION,
        CombinedAttentionOpinionRelation.SIMULTANEOUS,
    ]
    assert {event.event_type for event in view.event_timeline} == {
        CombinedAssetTimelineEventType.ATTENTION_FIRST_OBSERVED,
        CombinedAssetTimelineEventType.OPINION_OBSERVED,
        CombinedAssetTimelineEventType.THESIS_CHANGE_OBSERVED,
    }
    assert all(
        field not in view.model_dump()
        for field in ("score", "source", "follower", "influencer", "caused_by")
    )


def test_attention_only_opinion_only_listing_separation_and_filters() -> None:
    attention_asset = _asset(_uuid(2), "Attention Only", "SH", "600001")
    opinion_asset = _asset(_uuid(3), "Opinion Only", "SH", "600002")
    sh_asset = _asset(_uuid(4), "山东黄金", "SH", "600547")
    hk_asset = _asset(_uuid(5), "山东黄金", "HK", "01787")
    investor_one, investor_two = _uuid(21), _uuid(22)
    attention = [
        _attention(
            20,
            investor_one,
            attention_asset.id,
            START,
            AttentionEvidenceType.EXPLICIT_MENTION,
        ),
        _attention(
            21,
            investor_one,
            sh_asset.id,
            START,
            AttentionEvidenceType.REPOST,
        ),
        _attention(
            22,
            investor_two,
            sh_asset.id,
            START + timedelta(days=1),
            AttentionEvidenceType.EXPLICIT_MENTION,
        ),
        _attention(
            23,
            investor_one,
            hk_asset.id,
            START,
            AttentionEvidenceType.EXPLICIT_MENTION,
        ),
        _attention(
            24,
            investor_two,
            hk_asset.id,
            START + timedelta(days=1),
            AttentionEvidenceType.EXPLICIT_MENTION,
        ),
    ]
    opinion_timeline, opinion_evolution = _opinion(
        301,
        investor_two,
        opinion_asset.id,
        START + timedelta(hours=1),
        OpinionDirection.NEUTRAL,
    )
    sh_opinion, sh_evolution = _opinion(
        302,
        investor_one,
        sh_asset.id,
        START,
        OpinionDirection.BULLISH,
    )
    changes = [
        _change(
            401,
            301,
            investor_two,
            opinion_asset.id,
            START + timedelta(hours=1),
            ThesisChangeType.NEW_THESIS,
        ),
        _change(
            402,
            302,
            investor_one,
            sh_asset.id,
            START,
            ThesisChangeType.NEW_THESIS,
        ),
    ]
    uow = _UnitOfWork(
        [attention_asset, opinion_asset, sh_asset, hk_asset],
        [_investor(investor_one, "one"), _investor(investor_two, "two")],
        attention,
        [opinion_timeline, sh_opinion],
        [opinion_evolution, sh_evolution],
        changes,
    )
    service = _service(uow)

    views = service.list_asset_views(START, START + timedelta(days=2), min_opinion_investors=0)
    by_symbol = {view.symbol: view for view in views}
    attention_only = by_symbol["600001"]
    opinion_only = by_symbol["600002"]

    assert attention_only.investor_views[0].attention_opinion_relation is (
        CombinedAttentionOpinionRelation.ATTENTION_WITHOUT_OPINION
    )
    assert opinion_only.investor_views[0].attention_opinion_relation is (
        CombinedAttentionOpinionRelation.OPINION_WITHOUT_PRIOR_ATTENTION
    )
    assert by_symbol["600547"].asset_id != by_symbol["01787"].asset_id
    assert (
        len(
            service.list_asset_views(
                START,
                START + timedelta(days=2),
                min_attention_investors=2,
            )
        )
        == 2
    )
    assert (
        service.get_asset_view(opinion_asset.id, START, START + timedelta(days=2)) == opinion_only
    )


def test_opinion_after_attention_relation_is_explicit() -> None:
    asset_id = _uuid(55)
    investor_id = _uuid(551)
    attention_time = START
    opinion_time = START + timedelta(hours=2)
    opinion_timeline, opinion_evolution = _opinion(
        5501,
        investor_id,
        asset_id,
        opinion_time,
        OpinionDirection.BULLISH,
    )
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "one")],
        [
            _attention(
                5502,
                investor_id,
                asset_id,
                attention_time,
                AttentionEvidenceType.EXPLICIT_MENTION,
            )
        ],
        [opinion_timeline],
        [opinion_evolution],
        [
            _change(
                5503,
                5501,
                investor_id,
                asset_id,
                opinion_time,
                ThesisChangeType.NEW_THESIS,
            )
        ],
    )

    view = _service(uow).get_asset_view(asset_id, START, START + timedelta(days=1))

    assert view is not None
    assert view.investor_views[0].attention_opinion_relation is (
        CombinedAttentionOpinionRelation.OPINION_AFTER_ATTENTION
    )
    assert view.investor_views[0].attention_to_first_opinion_lag_hours == 2


def test_missing_thesis_comparison_and_window_repeatability_are_visible() -> None:
    asset_id = _uuid(6)
    investor_id = _uuid(61)
    opinions = [
        _opinion(501, investor_id, asset_id, START, OpinionDirection.BULLISH),
        _opinion(502, investor_id, asset_id, START + timedelta(days=1), OpinionDirection.BULLISH),
    ]
    changes = [
        _change(601, 501, investor_id, asset_id, START, ThesisChangeType.NEW_THESIS),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "one")],
        [],
        [item[0] for item in opinions],
        [item[1] for item in opinions],
        changes,
    )
    service = _service(uow)

    first = service.get_asset_view(asset_id, START + timedelta(hours=12), START + timedelta(days=2))
    second = service.get_asset_view(
        asset_id, START + timedelta(hours=12), START + timedelta(days=2)
    )
    default_window = service.get_asset_view(asset_id)

    assert first == second
    assert first is not None
    assert default_window is not None
    assert default_window.window_start == START
    assert default_window.window_end == START + timedelta(days=10)
    investor = first.investor_views[0]
    assert investor.opinion_count == 1
    assert investor.missing_thesis_comparison_count == 1
    assert first.data_quality.missing_thesis_comparison_count == 1
    assert first.event_timeline[0].event_type is CombinedAssetTimelineEventType.OPINION_OBSERVED
