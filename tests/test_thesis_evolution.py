from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from contracts import (
    AnalysisSpec,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    EffectiveAnalysisPolicy,
    OpinionDirection,
    ThesisChangeType,
    ThesisChangeView,
    ThesisComparisonStatus,
    ThesisEvolutionCompleteness,
    ThesisEvolutionDirectionTransition,
    ThesisEvolutionOpinionView,
)
from intelligence.services.thesis_evolution import ThesisEvolutionService

START = datetime(2026, 1, 1, tzinfo=UTC)
ATTENTION_POLICY = "attention-occurrence-v1"
COMPARISON_VERSION = "thesis-test"
POLICY = EffectiveAnalysisPolicy(
    active_spec=AnalysisSpec.from_model_version("thesis-evolution-test")
)


def _uuid(value: int) -> UUID:
    return UUID(int=value)


def _asset(asset_id: UUID, name: str = "Test Asset", market: str = "SH", symbol: str = "600000"):
    return SimpleNamespace(id=asset_id, name=name, market=market, symbol=symbol)


def _investor(investor_id: UUID, name: str):
    return SimpleNamespace(id=investor_id, name=name)


def _opinion(
    opinion_id: int,
    investor_id: UUID,
    asset_id: UUID,
    published_time: datetime,
    direction: OpinionDirection,
    *,
    thesis: tuple[str, ...] = ("test thesis",),
) -> ThesisEvolutionOpinionView:
    return ThesisEvolutionOpinionView(
        opinion_id=_uuid(opinion_id),
        raw_event_id=_uuid(opinion_id + 1000),
        event_analysis_id=_uuid(opinion_id + 2000),
        investor_id=investor_id,
        asset_id=asset_id,
        analysis_version=POLICY.active_analysis_version,
        published_time=published_time,
        direction=direction,
        strength=75,
        confidence=0.9,
        thesis=thesis,
        catalysts=("catalyst",),
        risks=("risk",),
        time_horizon="LONG_TERM",
    )


def _change(
    change_id: int,
    opinion_id: int,
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
        previous_opinion_id=_uuid(previous_opinion_id) if previous_opinion_id else None,
        current_opinion_id=_uuid(opinion_id),
        previous_event_id=(_uuid(previous_opinion_id + 1000) if previous_opinion_id else None),
        current_event_id=_uuid(opinion_id + 1000),
        effective_time=effective_time,
        change_type=change_type,
        confidence=0.9,
        summary="existing comparator output",
        evidence=("existing evidence",),
        opinion_analysis_version=POLICY.active_analysis_version,
        comparison_version=COMPARISON_VERSION,
        calculated_at=effective_time,
        input_identity=f"change-{change_id}",
    )


def _attention(
    occurrence_id: int,
    investor_id: UUID,
    asset_id: UUID,
    published_time: datetime,
) -> AttentionOccurrenceView:
    return AttentionOccurrenceView(
        id=_uuid(occurrence_id),
        investor_id=investor_id,
        asset_id=asset_id,
        event_id=_uuid(occurrence_id + 3000),
        published_time=published_time,
        evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
        evidence=(
            AttentionEvidence(
                evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                matched_by="test",
            ),
        ),
        attention_policy_version=ATTENTION_POLICY,
        calculated_at=published_time,
    )


class _OpinionReader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective_evolution_timeline(self, policy, *, as_of=None):
        return list(self.values)

    def list_effective_evolution_timeline_by_asset(self, asset_id, policy, *, as_of=None):
        return [value for value in self.values if value.asset_id == asset_id]


class _ChangeReader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective(self, policy, comparison_version=None, *, as_of=None):
        return list(self.values)

    def list_effective_by_asset(
        self,
        asset_id,
        policy,
        comparison_version=None,
        *,
        as_of=None,
    ):
        return [value for value in self.values if value.asset_id == asset_id]


class _AttentionReader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective(self, policy, attention_policy_version, *, as_of=None):
        return list(self.values)

    def list_effective_by_asset(self, asset_id, policy, attention_policy_version, *, as_of=None):
        return [value for value in self.values if value.asset_id == asset_id]


class _UnitOfWork:
    def __init__(self, assets, investors, opinions, changes=(), attention=()):
        self.assets = {value.id: value for value in assets}
        self.investors = {value.id: value for value in investors}
        self.opinions = _OpinionReader(opinions)
        self.thesis_changes = _ChangeReader(changes)
        self.attention_occurrences = _AttentionReader(attention)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def _service(uow):
    return ThesisEvolutionService(
        lambda: uow,
        POLICY,
        attention_policy_version=ATTENTION_POLICY,
        thesis_comparison_version=COMPARISON_VERSION,
    )


def test_single_opinion_is_initial_and_has_no_missing_comparison() -> None:
    investor_id, asset_id = _uuid(1), _uuid(2)
    opinion = _opinion(10, investor_id, asset_id, START, OpinionDirection.BULLISH)
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        [opinion],
    )

    timeline = _service(uow).get_thesis_timeline(investor_id, asset_id)

    assert timeline is not None
    assert timeline.opinion_count == 1
    assert timeline.thesis_change_count == 0
    assert timeline.missing_thesis_change_count == 0
    assert (
        timeline.entries[0].direction_transition
        is ThesisEvolutionDirectionTransition.INITIAL_DIRECTION
    )
    assert timeline.entries[0].thesis_comparison_status is ThesisComparisonStatus.INITIAL_OPINION
    assert timeline.completeness is ThesisEvolutionCompleteness.UNKNOWN


def test_same_direction_keeps_direction_separate_from_extended_and_changed_thesis() -> None:
    investor_id, asset_id = _uuid(3), _uuid(4)
    opinions = [
        _opinion(20, investor_id, asset_id, START, OpinionDirection.BULLISH),
        _opinion(21, investor_id, asset_id, START + timedelta(days=1), OpinionDirection.BULLISH),
        _opinion(22, investor_id, asset_id, START + timedelta(days=2), OpinionDirection.BULLISH),
    ]
    changes = [
        _change(120, 20, investor_id, asset_id, START, ThesisChangeType.NEW_THESIS),
        _change(
            121,
            21,
            investor_id,
            asset_id,
            START + timedelta(days=1),
            ThesisChangeType.THESIS_EXTENDED,
            20,
        ),
        _change(
            122,
            22,
            investor_id,
            asset_id,
            START + timedelta(days=2),
            ThesisChangeType.THESIS_CHANGED,
            21,
        ),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        opinions,
        changes,
    )

    timeline = _service(uow).get_thesis_timeline(investor_id, asset_id)

    assert timeline is not None
    assert [entry.direction_transition for entry in timeline.entries] == [
        ThesisEvolutionDirectionTransition.INITIAL_DIRECTION,
        ThesisEvolutionDirectionTransition.SAME_DIRECTION,
        ThesisEvolutionDirectionTransition.SAME_DIRECTION,
    ]
    assert [entry.thesis_change_type for entry in timeline.entries] == [
        ThesisChangeType.NEW_THESIS,
        ThesisChangeType.THESIS_EXTENDED,
        ThesisChangeType.THESIS_CHANGED,
    ]
    assert timeline.extended_count == 1
    assert timeline.changed_count == 1
    assert timeline.same_direction_change_count == 1


def test_direction_reversal_and_neutral_transitions_are_deterministic() -> None:
    investor_id, asset_id = _uuid(5), _uuid(6)
    directions = (
        OpinionDirection.BULLISH,
        OpinionDirection.BEARISH,
        OpinionDirection.STRONG_BEARISH,
        OpinionDirection.NEUTRAL,
        OpinionDirection.STRONG_BULLISH,
    )
    opinions = [
        _opinion(30 + index, investor_id, asset_id, START + timedelta(days=index), direction)
        for index, direction in enumerate(directions)
    ]
    changes = [
        _change(130, 30, investor_id, asset_id, START, ThesisChangeType.NEW_THESIS),
        _change(
            131,
            31,
            investor_id,
            asset_id,
            START + timedelta(days=1),
            ThesisChangeType.THESIS_CHANGED,
            30,
        ),
        _change(
            132,
            32,
            investor_id,
            asset_id,
            START + timedelta(days=2),
            ThesisChangeType.THESIS_UNCHANGED,
            31,
        ),
        _change(
            133,
            33,
            investor_id,
            asset_id,
            START + timedelta(days=3),
            ThesisChangeType.THESIS_EXTENDED,
            32,
        ),
        _change(
            134,
            34,
            investor_id,
            asset_id,
            START + timedelta(days=4),
            ThesisChangeType.THESIS_CHANGED,
            33,
        ),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        opinions,
        changes,
    )

    timeline = _service(uow).get_thesis_timeline(investor_id, asset_id)

    assert timeline is not None
    assert [entry.direction_transition for entry in timeline.entries] == [
        ThesisEvolutionDirectionTransition.INITIAL_DIRECTION,
        ThesisEvolutionDirectionTransition.BULLISH_TO_BEARISH,
        ThesisEvolutionDirectionTransition.SAME_DIRECTION,
        ThesisEvolutionDirectionTransition.TO_NEUTRAL,
        ThesisEvolutionDirectionTransition.FROM_NEUTRAL,
    ]
    assert timeline.reversal_count == 1


def test_missing_thesis_comparison_is_explicit_and_not_repaired() -> None:
    investor_id, asset_id = _uuid(7), _uuid(8)
    opinions = [
        _opinion(40, investor_id, asset_id, START, OpinionDirection.BULLISH),
        _opinion(41, investor_id, asset_id, START + timedelta(days=1), OpinionDirection.BULLISH),
        _opinion(42, investor_id, asset_id, START + timedelta(days=2), OpinionDirection.BEARISH),
    ]
    changes = [
        _change(140, 40, investor_id, asset_id, START, ThesisChangeType.NEW_THESIS),
        _change(
            141,
            41,
            investor_id,
            asset_id,
            START + timedelta(days=1),
            ThesisChangeType.THESIS_EXTENDED,
            40,
        ),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        opinions,
        changes,
    )

    timeline = _service(uow).get_thesis_timeline(investor_id, asset_id)

    assert timeline is not None
    missing = timeline.entries[-1]
    assert missing.thesis_comparison_status is ThesisComparisonStatus.MISSING_THESIS_COMPARISON
    assert missing.thesis_change_id is None
    assert missing.thesis_change_type is None
    assert missing.predecessor_opinion_id == _uuid(41)
    assert timeline.missing_thesis_change_count == 1


def test_insufficient_evidence_is_existing_semantics_not_missing_comparison() -> None:
    investor_id, asset_id = _uuid(9), _uuid(10)
    opinions = [
        _opinion(50, investor_id, asset_id, START, OpinionDirection.BULLISH),
        _opinion(51, investor_id, asset_id, START + timedelta(days=1), OpinionDirection.BULLISH),
    ]
    changes = [
        _change(150, 50, investor_id, asset_id, START, ThesisChangeType.NEW_THESIS),
        _change(
            151,
            51,
            investor_id,
            asset_id,
            START + timedelta(days=1),
            ThesisChangeType.INSUFFICIENT_EVIDENCE,
            50,
        ),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        opinions,
        changes,
    )

    timeline = _service(uow).get_thesis_timeline(investor_id, asset_id)

    assert timeline is not None
    assert (
        timeline.entries[-1].thesis_comparison_status is ThesisComparisonStatus.COMPARISON_AVAILABLE
    )
    assert timeline.entries[-1].thesis_change_type is ThesisChangeType.INSUFFICIENT_EVIDENCE
    assert timeline.missing_thesis_change_count == 0


def test_provenance_attention_context_listing_separation_and_determinism() -> None:
    investor_id, second_investor_id = _uuid(11), _uuid(12)
    sh_asset = _asset(_uuid(13), "山东黄金", "SH", "600547")
    hk_asset = _asset(_uuid(14), "山东黄金", "HK", "01787")
    sh_opinion = _opinion(
        60, investor_id, sh_asset.id, START + timedelta(hours=1), OpinionDirection.BULLISH
    )
    hk_opinions = [
        _opinion(61, investor_id, hk_asset.id, START, OpinionDirection.BULLISH),
        _opinion(
            62,
            second_investor_id,
            hk_asset.id,
            START + timedelta(days=1),
            OpinionDirection.BEARISH,
        ),
    ]
    attention = [_attention(160, investor_id, hk_asset.id, START)]
    uow = _UnitOfWork(
        [sh_asset, hk_asset],
        [_investor(investor_id, "one"), _investor(second_investor_id, "two")],
        [sh_opinion, *hk_opinions],
        attention=attention,
    )
    service = _service(uow)

    first = service.get_thesis_timeline(
        investor_id,
        hk_asset.id,
        include_attention_context=True,
    )
    second = service.get_thesis_timeline(
        investor_id,
        hk_asset.id,
        include_attention_context=True,
    )
    all_timelines = service.list_thesis_timelines(
        START,
        START + timedelta(days=2),
        min_opinions=1,
    )

    assert first == second
    assert first is not None
    assert first.entries[0].raw_event_id == _uuid(1061)
    assert first.entries[0].event_analysis_id == _uuid(2061)
    assert first.first_attention_time == START
    assert first.attention_to_first_opinion_lag == 0
    assert first.asset_id == hk_asset.id
    assert len(all_timelines) == 3
    assert {timeline.asset_id for timeline in all_timelines} == {sh_asset.id, hk_asset.id}
    assert all(
        timeline.completeness is ThesisEvolutionCompleteness.UNKNOWN for timeline in all_timelines
    )
    assert "score" not in first.model_dump()


def test_window_filtering_keeps_window_relative_initial_direction() -> None:
    investor_id, asset_id = _uuid(15), _uuid(16)
    opinions = [
        _opinion(70, investor_id, asset_id, START, OpinionDirection.BULLISH),
        _opinion(71, investor_id, asset_id, START + timedelta(days=1), OpinionDirection.BEARISH),
        _opinion(72, investor_id, asset_id, START + timedelta(days=2), OpinionDirection.BULLISH),
    ]
    changes = [
        _change(170, 70, investor_id, asset_id, START, ThesisChangeType.NEW_THESIS),
        _change(
            171,
            71,
            investor_id,
            asset_id,
            START + timedelta(days=1),
            ThesisChangeType.THESIS_CHANGED,
            70,
        ),
        _change(
            172,
            72,
            investor_id,
            asset_id,
            START + timedelta(days=2),
            ThesisChangeType.THESIS_CHANGED,
            71,
        ),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        opinions,
        changes,
    )
    service = _service(uow)

    timeline = service.get_thesis_timeline(
        investor_id,
        asset_id,
        START + timedelta(days=1),
        START + timedelta(days=2),
    )

    assert timeline is not None
    assert timeline.opinion_count == 2
    assert (
        timeline.entries[0].direction_transition
        is ThesisEvolutionDirectionTransition.INITIAL_DIRECTION
    )
    assert (
        timeline.entries[0].thesis_comparison_status is ThesisComparisonStatus.COMPARISON_AVAILABLE
    )
    assert timeline.entries[0].predecessor_opinion_id == _uuid(70)
    assert timeline.entries[0].temporal_gap_from_previous is None
    assert (
        timeline.entries[1].direction_transition
        is ThesisEvolutionDirectionTransition.BEARISH_TO_BULLISH
    )
    assert timeline.entries[1].temporal_gap_from_previous_days == 1


def test_min_opinions_is_a_query_filter_and_single_pair_get_is_supported() -> None:
    investor_id, asset_id = _uuid(17), _uuid(18)
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "Investor")],
        [_opinion(80, investor_id, asset_id, START, OpinionDirection.NEUTRAL)],
    )
    service = _service(uow)

    assert service.get_thesis_timeline(investor_id, asset_id) is not None
    assert service.list_thesis_timelines(START, START + timedelta(days=1)) == ()
    assert (
        len(
            service.list_thesis_timelines(
                START,
                START + timedelta(days=1),
                min_opinions=1,
            )
        )
        == 1
    )
