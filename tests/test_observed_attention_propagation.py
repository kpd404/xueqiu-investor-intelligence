from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID

from contracts import (
    AnalysisSpec,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    EffectiveAnalysisPolicy,
    ObservedAttentionCompleteness,
    ObservedAttentionDirectionRelation,
    ObservedAttentionTemporalRelation,
    OpinionDirection,
    OpinionTimelineEntry,
    ThesisChangeType,
    ThesisChangeView,
)
from intelligence.services.observed_attention_propagation import (
    ObservedAttentionPropagationService,
)

START = datetime(2026, 1, 1, tzinfo=UTC)
POLICY = "attention-occurrence-v1"
EFFECTIVE_POLICY = EffectiveAnalysisPolicy(
    active_spec=AnalysisSpec.from_model_version("observed-attention-test")
)


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
    evidence_type: AttentionEvidenceType = AttentionEvidenceType.EXPLICIT_MENTION,
) -> AttentionOccurrenceView:
    opinion_id = (
        _uuid(occurrence_id + 1000) if evidence_type is AttentionEvidenceType.OPINION else None
    )
    analysis_id = (
        _uuid(occurrence_id + 2000) if evidence_type is AttentionEvidenceType.OPINION else None
    )
    return AttentionOccurrenceView(
        id=_uuid(occurrence_id),
        investor_id=investor_id,
        asset_id=asset_id,
        event_id=_uuid(occurrence_id + 3000),
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
        attention_policy_version=POLICY,
        calculated_at=published_time,
    )


def _opinion(
    opinion_id: int,
    investor_id: UUID,
    asset_id: UUID,
    published_time: datetime,
    direction: OpinionDirection,
) -> OpinionTimelineEntry:
    return OpinionTimelineEntry(
        opinion_id=_uuid(opinion_id),
        event_id=_uuid(opinion_id + 5000),
        investor_id=investor_id,
        asset_id=asset_id,
        direction=direction,
        strength=70,
        confidence=0.9,
        published_time=published_time,
        generated_time=published_time,
    )


def _thesis(
    change_id: int,
    investor_id: UUID,
    asset_id: UUID,
    effective_time: datetime,
) -> ThesisChangeView:
    return ThesisChangeView(
        id=_uuid(change_id),
        investor_id=investor_id,
        asset_id=asset_id,
        previous_opinion_id=None,
        current_opinion_id=_uuid(change_id + 6000),
        previous_event_id=None,
        current_event_id=_uuid(change_id + 7000),
        effective_time=effective_time,
        change_type=ThesisChangeType.NEW_THESIS,
        confidence=0.9,
        summary="test",
        evidence=(),
        opinion_analysis_version=EFFECTIVE_POLICY.active_analysis_version,
        comparison_version="thesis-test",
        calculated_at=effective_time,
        input_identity=f"test-{change_id}",
    )


class _AttentionReader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective(self, policy, attention_policy_version, *, as_of=None):
        return list(self.values)

    def list_effective_by_asset(self, asset_id, policy, attention_policy_version, *, as_of=None):
        return [value for value in self.values if value.asset_id == asset_id]


class _OpinionReader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective_timeline_by_asset(self, asset_id, policy, *, as_of=None):
        return [value for value in self.values if value.asset_id == asset_id]


class _ThesisReader:
    def __init__(self, values):
        self.values = list(values)

    def list_effective_by_asset(self, asset_id, policy, comparison_version, *, as_of=None):
        return [value for value in self.values if value.asset_id == asset_id]


class _UnitOfWork:
    def __init__(self, assets, investors, attention, opinions=(), thesis=()):
        self.assets = {value.id: value for value in assets}
        self.investors = {value.id: value for value in investors}
        self.attention_occurrences = _AttentionReader(attention)
        self.opinions = _OpinionReader(opinions)
        self.thesis_changes = _ThesisReader(thesis)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None


def _service(uow):
    return ObservedAttentionPropagationService(lambda: uow, EFFECTIVE_POLICY)


def test_sequence_uses_first_occurrence_per_investor_and_preserves_evidence() -> None:
    asset_id = _uuid(1)
    investor_one = _uuid(11)
    investor_two = _uuid(12)
    investor_three = _uuid(13)
    attention = [
        _attention(1, investor_one, asset_id, START, AttentionEvidenceType.OPINION),
        _attention(2, investor_one, asset_id, START + timedelta(hours=1)),
        _attention(3, investor_two, asset_id, START + timedelta(hours=2)),
        _attention(4, investor_three, asset_id, START + timedelta(days=3)),
    ]
    opinions = [
        _opinion(101, investor_one, asset_id, START, OpinionDirection.BULLISH),
        _opinion(102, investor_two, asset_id, START + timedelta(hours=2), OpinionDirection.BULLISH),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [
            _investor(investor_one, "one"),
            _investor(investor_two, "two"),
            _investor(investor_three, "three"),
        ],
        attention,
        opinions,
    )

    sequence = _service(uow).get_observed_attention_sequences(
        START,
        START + timedelta(days=4),
    )[0]

    assert sequence.completeness is ObservedAttentionCompleteness.UNKNOWN
    assert sequence.investor_count == 3
    assert sequence.occurrence_count == 4
    assert sequence.first_observed.attention_occurrence_id == _uuid(1)
    assert sequence.first_observed.evidence_types == (AttentionEvidenceType.OPINION,)
    assert [item.investor_name for item in sequence.later_observations] == ["two", "three"]
    assert sequence.later_observations[0].lag_hours == 2
    assert sequence.later_observations[1].lag_days == 3


def test_edges_compare_same_opposite_neutral_and_missing_with_strong_mapping() -> None:
    asset_id = _uuid(2)
    investors = [_uuid(value) for value in range(21, 25)]
    attention = [
        _attention(10 + index, investor_id, asset_id, START + timedelta(hours=index))
        for index, investor_id in enumerate(investors)
    ]
    opinions = [
        _opinion(110, investors[0], asset_id, START, OpinionDirection.STRONG_BULLISH),
        _opinion(111, investors[1], asset_id, START + timedelta(hours=1), OpinionDirection.BULLISH),
        _opinion(112, investors[2], asset_id, START + timedelta(hours=2), OpinionDirection.BEARISH),
        _opinion(113, investors[3], asset_id, START + timedelta(hours=3), OpinionDirection.NEUTRAL),
    ]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(value, str(index)) for index, value in enumerate(investors)],
        attention,
        opinions,
    )

    edges = _service(uow).get_observed_attention_edges(
        START,
        START + timedelta(days=1),
    )

    assert [edge.direction_relation for edge in edges] == [
        ObservedAttentionDirectionRelation.SAME_DIRECTION,
        ObservedAttentionDirectionRelation.OPPOSITE_DIRECTION,
        ObservedAttentionDirectionRelation.NEUTRAL_OR_MIXED,
    ]
    assert edges[0].earliest_first_opinion_direction is OpinionDirection.STRONG_BULLISH
    assert edges[0].later_first_opinion_direction is OpinionDirection.BULLISH
    assert edges[0].temporal_relation is ObservedAttentionTemporalRelation.OBSERVED_LATER


def test_missing_opinion_is_explicit_and_thesis_context_is_optional() -> None:
    asset_id = _uuid(3)
    investor_one, investor_two = _uuid(31), _uuid(32)
    attention = [
        _attention(20, investor_one, asset_id, START),
        _attention(21, investor_two, asset_id, START + timedelta(days=1)),
    ]
    thesis = [_thesis(301, investor_one, asset_id, START + timedelta(hours=3))]
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_one, "one"), _investor(investor_two, "two")],
        attention,
        thesis=thesis,
    )
    service = _service(uow)

    without_context = service.get_observed_attention_sequences(
        START,
        START + timedelta(days=2),
    )[0]
    with_context = service.get_observed_attention_sequences(
        START,
        START + timedelta(days=2),
        include_thesis_context=True,
    )[0]
    edge = service.derive_edges(with_context)[0]

    assert without_context.first_observed.latest_thesis_change_type is None
    assert with_context.first_observed.latest_thesis_change_type is ThesisChangeType.NEW_THESIS
    assert edge.direction_relation is ObservedAttentionDirectionRelation.OPINION_MISSING


def test_same_timestamp_is_not_a_positive_temporal_order() -> None:
    asset_id = _uuid(4)
    investor_one, investor_two = _uuid(41), _uuid(42)
    timestamp = START + timedelta(days=1)
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_one, "one"), _investor(investor_two, "two")],
        [
            _attention(30, investor_one, asset_id, timestamp),
            _attention(31, investor_two, asset_id, timestamp),
        ],
    )

    sequence = _service(uow).get_observed_attention_sequences(
        START,
        START + timedelta(days=2),
    )[0]
    edge = ObservedAttentionPropagationService.derive_edges(sequence)[0]

    assert edge.temporal_relation is ObservedAttentionTemporalRelation.SIMULTANEOUS_OBSERVATION
    assert edge.lag_seconds == 0
    assert edge.earliest_time == edge.later_time


def test_listing_identity_and_deterministic_repeatability_are_preserved() -> None:
    sh_asset = _asset(_uuid(5), "山东黄金", "SH", "600547")
    hk_asset = _asset(_uuid(6), "山东黄金", "HK", "01787")
    investor_one, investor_two = _uuid(51), _uuid(52)
    attention = [
        _attention(40, investor_one, sh_asset.id, START),
        _attention(41, investor_two, sh_asset.id, START + timedelta(hours=1)),
        _attention(42, investor_one, hk_asset.id, START),
        _attention(43, investor_two, hk_asset.id, START + timedelta(hours=1)),
    ]
    uow = _UnitOfWork(
        [sh_asset, hk_asset],
        [_investor(investor_one, "one"), _investor(investor_two, "two")],
        attention,
    )
    service = _service(uow)

    first = service.get_observed_attention_sequences(START, START + timedelta(days=1))
    second = service.get_observed_attention_sequences(START, START + timedelta(days=1))

    assert first == second
    assert {(item.market, item.symbol) for item in first} == {("SH", "600547"), ("HK", "01787")}
    assert len({item.asset_id for item in first}) == 2
    assert all(item.completeness is ObservedAttentionCompleteness.UNKNOWN for item in first)
    assert "score" not in first[0].model_dump()


def test_named_reality_study_cases_are_regression_fixtures() -> None:
    招商轮船 = _asset(_uuid(80), "招商轮船", "SH", "601872")
    龙源电力 = _asset(_uuid(81), "龙源电力", "HK", "00916")
    贵州茅台 = _asset(_uuid(82), "贵州茅台", "SH", "600519")
    山东黄金_sh = _asset(_uuid(83), "山东黄金", "SH", "600547")
    山东黄金_hk = _asset(_uuid(84), "山东黄金", "HK", "01787")
    investor_names = {
        801: "笨笨的投资者2",
        802: "沈阳城",
        803: "Captain-Nemo船长",
        804: "看好股市的新人",
        811: "沈阳城",
        812: "重组专家",
        813: "爱投资的小人书",
        821: "看好股市的新人",
        822: "人生是历练",
        823: "Captain-Nemo船长",
        831: "人生是历练",
        832: "沈阳城",
        833: "Captain-Nemo船长",
        841: "人生是历练",
        842: "沈阳城",
    }
    investor_ids = {key: _uuid(key) for key in investor_names}
    attention = [
        _attention(60, investor_ids[801], 招商轮船.id, START),
        _attention(61, investor_ids[802], 招商轮船.id, START + timedelta(days=5)),
        _attention(62, investor_ids[803], 招商轮船.id, START + timedelta(days=8)),
        _attention(63, investor_ids[804], 招商轮船.id, START + timedelta(days=13)),
        _attention(64, investor_ids[811], 龙源电力.id, START),
        _attention(65, investor_ids[812], 龙源电力.id, START + timedelta(days=6)),
        _attention(66, investor_ids[813], 龙源电力.id, START + timedelta(days=26)),
        _attention(67, investor_ids[821], 贵州茅台.id, START),
        _attention(68, investor_ids[822], 贵州茅台.id, START + timedelta(hours=1)),
        _attention(69, investor_ids[823], 贵州茅台.id, START + timedelta(days=2)),
        _attention(70, investor_ids[831], 山东黄金_sh.id, START),
        _attention(71, investor_ids[832], 山东黄金_sh.id, START + timedelta(days=1)),
        _attention(72, investor_ids[833], 山东黄金_sh.id, START + timedelta(days=2)),
        _attention(73, investor_ids[841], 山东黄金_hk.id, START),
        _attention(74, investor_ids[842], 山东黄金_hk.id, START + timedelta(days=1)),
    ]
    opinions = [
        _opinion(401, investor_ids[811], 龙源电力.id, START, OpinionDirection.BEARISH),
        _opinion(
            402,
            investor_ids[812],
            龙源电力.id,
            START + timedelta(days=6),
            OpinionDirection.BEARISH,
        ),
        _opinion(
            403,
            investor_ids[813],
            龙源电力.id,
            START + timedelta(days=26),
            OpinionDirection.BULLISH,
        ),
        _opinion(
            404,
            investor_ids[823],
            贵州茅台.id,
            START + timedelta(days=2),
            OpinionDirection.NEUTRAL,
        ),
    ]
    uow = _UnitOfWork(
        [
            招商轮船,
            龙源电力,
            贵州茅台,
            山东黄金_sh,
            山东黄金_hk,
        ],
        [_investor(value, investor_names[key]) for key, value in investor_ids.items()],
        attention,
        opinions,
    )
    service = _service(uow)
    sequences = service.get_observed_attention_sequences(START, START + timedelta(days=30))
    by_listing = {(item.market, item.symbol): item for item in sequences}

    assert [
        by_listing[("SH", "601872")].first_observed.investor_name,
        *[item.investor_name for item in by_listing[("SH", "601872")].later_observations],
    ] == ["笨笨的投资者2", "沈阳城", "Captain-Nemo船长", "看好股市的新人"]
    longyuan_edges = service.derive_edges(by_listing[("HK", "00916")])
    assert [item.direction_relation for item in longyuan_edges] == [
        ObservedAttentionDirectionRelation.SAME_DIRECTION,
        ObservedAttentionDirectionRelation.OPPOSITE_DIRECTION,
    ]
    maotai = by_listing[("SH", "600519")]
    assert maotai.investor_count == 3
    assert (
        sum(
            item.first_effective_opinion_id is not None
            for item in (maotai.first_observed, *maotai.later_observations)
        )
        == 1
    )
    assert by_listing[("SH", "600547")].asset_id != by_listing[("HK", "01787")].asset_id


def test_min_investors_is_a_query_filter_not_a_contract_threshold() -> None:
    asset_id = _uuid(7)
    investor_id = _uuid(71)
    uow = _UnitOfWork(
        [_asset(asset_id)],
        [_investor(investor_id, "one")],
        [_attention(50, investor_id, asset_id, START)],
    )

    sequences = _service(uow).get_observed_attention_sequences(
        START,
        START + timedelta(days=1),
        min_investors=1,
    )

    assert len(sequences) == 1
    assert sequences[0].investor_count == 1
    assert sequences[0].later_observations == ()
