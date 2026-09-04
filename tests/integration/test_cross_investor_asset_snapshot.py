import json
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from contracts import (
    CROSS_INVESTOR_POLICY_VERSION,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    ConsistencyType,
    CrossInvestorAssetSnapshotCreate,
    CrossInvestorAssetSnapshotView,
    EffectiveAnalysisPolicy,
    OpinionActionConsistencyView,
    OpinionDirection,
    OpinionTimelineEntry,
    PortfolioActionType,
    PortfolioActionView,
    ThesisChangeType,
    ThesisChangeView,
    build_cross_investor_input_identity,
)
from contracts.analysis import AnalysisSpec
from database.models import Asset, CrossInvestorAssetSnapshot, Investor
from database.repositories import CrossInvestorAssetSnapshotRepository
from intelligence.services.cross_investor_asset_snapshot import (
    CrossInvestorAssetSnapshotService,
)

ASSET_ID = uuid4()
INVESTOR_ONE = uuid4()
INVESTOR_TWO = uuid4()
ANALYSIS_SPEC = AnalysisSpec.for_provider(
    provider_id="cross-test-provider",
    model_version="cross-test-model",
    prompt_version="cross-test-prompt",
    schema_version="cross-test-schema",
    analysis_policy_version="cross-test-policy",
)
POLICY = EffectiveAnalysisPolicy(active_spec=ANALYSIS_SPEC)
ATTENTION_POLICY = "attention-occurrence-v1"
THESIS_VERSION = "thesis-comparison-v1"
CONSISTENCY_POLICY = "opinion-action-consistency-v1"
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 7, tzinfo=UTC)


class _Reader:
    def __init__(self, values: list[object]) -> None:
        self.values = values


class _AttentionReader(_Reader):
    def list_effective_by_asset(self, asset_id, policy, attention_policy_version, *, as_of=None):
        return [
            item
            for item in self.values
            if item.asset_id == asset_id
            and item.attention_policy_version == attention_policy_version
            and (as_of is None or item.published_time <= as_of)
        ]


class _OpinionReader(_Reader):
    def list_effective_timeline_by_asset(self, asset_id, policy, *, as_of=None):
        return [
            item
            for item in self.values
            if item.asset_id == asset_id and (as_of is None or item.published_time <= as_of)
        ]


class _ThesisReader(_Reader):
    def list_effective_by_asset(self, asset_id, policy, comparison_version, *, as_of=None):
        return [
            item
            for item in self.values
            if item.asset_id == asset_id
            and item.comparison_version == comparison_version
            and (as_of is None or item.effective_time <= as_of)
        ]


class _ActionReader(_Reader):
    def list_effective_by_asset(self, asset_id, *, as_of=None):
        return [
            item
            for item in self.values
            if item.asset_id == asset_id and (as_of is None or item.effective_time <= as_of)
        ]


class _ConsistencyReader(_Reader):
    def list_effective_by_asset(
        self,
        asset_id,
        policy,
        *,
        consistency_policy_version,
        as_of=None,
    ):
        return [
            item
            for item in self.values
            if item.asset_id == asset_id
            and item.consistency_policy_version == consistency_policy_version
            and (as_of is None or item.effective_time <= as_of)
        ]


class _PortfolioReader:
    def __init__(self, values=None) -> None:
        self.values = values or []

    def list(self):
        return self.values


class _SnapshotWriter:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def add_if_absent(self, command):
        existing = self.values.get(command.input_identity)
        if existing is not None:
            return existing, False
        view = CrossInvestorAssetSnapshotView(id=uuid4(), **command.model_dump(mode="json"))
        self.values[command.input_identity] = view
        return view, True


class _Uow:
    def __init__(self, *, attention, opinions, thesis, actions, consistencies, portfolios=None):
        self.attention_occurrences = _AttentionReader(attention)
        self.opinions = _OpinionReader(opinions)
        self.thesis_changes = _ThesisReader(thesis)
        self.portfolio_actions = _ActionReader(actions)
        self.consistencies = _ConsistencyReader(consistencies)
        self.portfolios = _PortfolioReader(portfolios)
        self.cross_investor_asset_snapshots = _SnapshotWriter()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        return None


def _attention(investor_id, published_time, policy=ATTENTION_POLICY):
    return AttentionOccurrenceView(
        id=uuid4(),
        investor_id=investor_id,
        asset_id=ASSET_ID,
        event_id=uuid4(),
        published_time=published_time,
        evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
        evidence=(
            AttentionEvidence(
                evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                matched_by="NAME",
                reference="asset",
            ),
        ),
        attention_policy_version=policy,
        calculated_at=published_time + timedelta(minutes=1),
    )


def _opinion(investor_id, published_time, direction):
    return OpinionTimelineEntry(
        opinion_id=uuid4(),
        event_id=uuid4(),
        investor_id=investor_id,
        asset_id=ASSET_ID,
        direction=direction,
        strength=70,
        confidence=0.8,
        published_time=published_time,
        generated_time=published_time + timedelta(minutes=2),
    )


def _thesis(investor_id, published_time, change_type):
    return ThesisChangeView(
        id=uuid4(),
        investor_id=investor_id,
        asset_id=ASSET_ID,
        previous_opinion_id=None,
        current_opinion_id=uuid4(),
        previous_event_id=None,
        current_event_id=uuid4(),
        effective_time=published_time,
        change_type=change_type,
        confidence=0.8,
        summary="evidence",
        evidence=("source",),
        opinion_analysis_version=ANALYSIS_SPEC.analysis_version,
        comparison_version=THESIS_VERSION,
        calculated_at=published_time + timedelta(minutes=3),
        input_identity=str(uuid4()),
    )


def _consistency(investor_id, published_time):
    opinion_id = uuid4()
    action_id = uuid4()
    identity = json.dumps(
        {
            "consistency_policy_version": CONSISTENCY_POLICY,
            "opinion_id": str(opinion_id),
            "portfolio_action_id": str(action_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return OpinionActionConsistencyView(
        id=uuid4(),
        investor_id=investor_id,
        asset_id=ASSET_ID,
        opinion_id=opinion_id,
        opinion_direction=OpinionDirection.BULLISH,
        portfolio_action_id=action_id,
        action_type=PortfolioActionType.POSITION_INCREASED,
        consistency_type=ConsistencyType.POSITIVE_ALIGNMENT,
        confidence=0.8,
        evidence={},
        effective_time=published_time,
        calculated_at=published_time + timedelta(minutes=4),
        opinion_analysis_version=ANALYSIS_SPEC.analysis_version,
        consistency_policy_version=CONSISTENCY_POLICY,
        input_identity=identity,
    )


def _action(investor_id, published_time):
    return PortfolioActionView(
        id=uuid4(),
        portfolio_id=uuid4(),
        asset_id=ASSET_ID,
        asset_reference_id=None,
        previous_snapshot_batch_id=uuid4(),
        current_snapshot_batch_id=uuid4(),
        previous_position_snapshot_id=uuid4(),
        current_position_snapshot_id=uuid4(),
        action_type=PortfolioActionType.POSITION_INCREASED,
        effective_time=published_time,
        calculated_at=published_time + timedelta(minutes=5),
        created_at=published_time + timedelta(minutes=5),
    )


def _service(uow):
    return CrossInvestorAssetSnapshotService(
        lambda: uow,
        POLICY,
        attention_policy_version=ATTENTION_POLICY,
        thesis_comparison_version=THESIS_VERSION,
        consistency_policy_version=CONSISTENCY_POLICY,
    )


def test_cross_investor_snapshot_aggregates_contributions_and_latest_direction():
    attention = [
        _attention(INVESTOR_ONE, START + timedelta(days=1)),
        _attention(INVESTOR_TWO, START + timedelta(days=2)),
    ]
    opinions = [
        _opinion(INVESTOR_ONE, START + timedelta(days=1), OpinionDirection.BULLISH),
        _opinion(INVESTOR_ONE, START + timedelta(days=3), OpinionDirection.BEARISH),
        _opinion(INVESTOR_TWO, START + timedelta(days=2), OpinionDirection.NEUTRAL),
    ]
    thesis = [
        _thesis(INVESTOR_ONE, START + timedelta(days=2), ThesisChangeType.THESIS_REINFORCED),
        _thesis(INVESTOR_TWO, START + timedelta(days=4), ThesisChangeType.THESIS_CHANGED),
    ]
    actions = [_action(INVESTOR_ONE, START + timedelta(days=3))]
    consistencies = [_consistency(INVESTOR_ONE, START + timedelta(days=3))]
    portfolio = type(
        "Portfolio", (), {"id": actions[0].portfolio_id, "investor_id": INVESTOR_ONE}
    )()
    uow = _Uow(
        attention=attention,
        opinions=opinions,
        thesis=thesis,
        actions=actions,
        consistencies=consistencies,
        portfolios=[portfolio],
    )

    snapshot = _service(uow).calculate(ASSET_ID, START, END)

    assert snapshot.attention_occurrence_count == 2
    assert snapshot.attention_investor_count == 2
    assert snapshot.new_attention_investor_count == 2
    assert snapshot.opinion_count == 3
    assert snapshot.opinion_investor_count == 2
    assert snapshot.bullish_investor_count == 0
    assert snapshot.bearish_investor_count == 1
    assert snapshot.neutral_investor_count == 1
    assert snapshot.thesis_change_count == 2
    assert snapshot.thesis_change_investor_count == 2
    assert snapshot.thesis_reinforced_investor_count == 1
    assert snapshot.thesis_changed_investor_count == 1
    assert snapshot.portfolio_action_count == 1
    assert snapshot.portfolio_action_investor_count == 1
    assert snapshot.position_increased_count == 1
    assert snapshot.consistency_count == 1
    assert snapshot.positive_alignment_count == 1
    assert {item.investor_id for item in snapshot.contributions} == {
        INVESTOR_ONE,
        INVESTOR_TWO,
    }
    first = next(item for item in snapshot.contributions if item.investor_id == INVESTOR_ONE)
    assert first.attention_occurrence_count == 1
    assert first.window_opinion_count == 2
    assert len(first.window_opinion_ids) == 2
    assert first.latest_window_opinion_direction is OpinionDirection.BEARISH
    assert first.latest_window_opinion_id in first.window_opinion_ids
    assert first.thesis_change_types == (ThesisChangeType.THESIS_REINFORCED,)
    assert first.portfolio_action_types == (PortfolioActionType.POSITION_INCREASED,)
    assert first.consistency_types == (ConsistencyType.POSITIVE_ALIGNMENT,)
    assert (
        sum(item.attention_occurrence_count for item in snapshot.contributions)
        == snapshot.attention_occurrence_count
    )
    assert (
        sum(item.window_opinion_count for item in snapshot.contributions) == snapshot.opinion_count
    )
    assert (
        sum(bool(item.window_opinion_ids) for item in snapshot.contributions)
        == snapshot.opinion_investor_count
    )
    assert (
        sum(len(item.thesis_change_ids) for item in snapshot.contributions)
        == snapshot.thesis_change_count
    )
    assert (
        sum(len(item.portfolio_action_ids) for item in snapshot.contributions)
        == snapshot.portfolio_action_count
    )
    assert (
        sum(len(item.consistency_ids) for item in snapshot.contributions)
        == snapshot.consistency_count
    )


def test_cross_investor_snapshot_isolates_attention_policy_and_future_data():
    attention = [
        _attention(INVESTOR_ONE, START + timedelta(days=1), "attention-occurrence-v1"),
        _attention(INVESTOR_TWO, START + timedelta(days=1), "attention-occurrence-v2"),
        _attention(INVESTOR_TWO, END + timedelta(days=1), ATTENTION_POLICY),
    ]
    uow = _Uow(attention=attention, opinions=[], thesis=[], actions=[], consistencies=[])

    snapshot = _service(uow).calculate(ASSET_ID, START, END)

    assert snapshot.attention_occurrence_count == 1
    assert snapshot.attention_investor_count == 1


def test_cross_investor_snapshot_excludes_old_and_future_opinions():
    opinions = [
        _opinion(INVESTOR_ONE, START - timedelta(days=30), OpinionDirection.BULLISH),
        _opinion(INVESTOR_ONE, START + timedelta(days=1), OpinionDirection.BEARISH),
        _opinion(INVESTOR_TWO, END + timedelta(days=1), OpinionDirection.BULLISH),
    ]
    uow = _Uow(attention=[], opinions=opinions, thesis=[], actions=[], consistencies=[])

    snapshot = _service(uow).calculate(ASSET_ID, START, END)

    assert snapshot.opinion_count == 1
    assert snapshot.opinion_investor_count == 1
    assert snapshot.bearish_investor_count == 1
    assert snapshot.bullish_investor_count == 0


def test_late_first_attention_changes_fingerprint_and_metric():
    attention = [_attention(INVESTOR_ONE, START + timedelta(days=2))]
    uow = _Uow(attention=attention, opinions=[], thesis=[], actions=[], consistencies=[])
    service = _service(uow)

    first = service.calculate(ASSET_ID, START, END)
    attention.append(_attention(INVESTOR_ONE, START - timedelta(days=1)))
    second = service.calculate(ASSET_ID, START, END)

    assert first.input_identity != second.input_identity
    assert first.new_attention_investor_count == 1
    assert second.new_attention_investor_count == 0
    assert len(uow.cross_investor_asset_snapshots.values) == 2


def test_cross_investor_snapshot_reuses_identical_input():
    uow = _Uow(attention=[], opinions=[], thesis=[], actions=[], consistencies=[])
    service = _service(uow)

    first = service.calculate(ASSET_ID, START, END)
    second = service.calculate(ASSET_ID, START, END)

    assert first.id == second.id
    assert len(uow.cross_investor_asset_snapshots.values) == 1


def test_cross_investor_policy_change_creates_new_version():
    uow = _Uow(attention=[], opinions=[], thesis=[], actions=[], consistencies=[])
    first = _service(uow).calculate(ASSET_ID, START, END)
    second = CrossInvestorAssetSnapshotService(
        lambda: uow,
        POLICY,
        attention_policy_version="attention-occurrence-v2",
        thesis_comparison_version=THESIS_VERSION,
        consistency_policy_version=CONSISTENCY_POLICY,
    ).calculate(ASSET_ID, START, END)

    assert first.input_identity != second.input_identity
    assert len(uow.cross_investor_asset_snapshots.values) == 2


def test_cross_investor_snapshot_repository_is_idempotent(db_session: Session):
    investor = Investor(
        name="Cross Snapshot Investor", platform="manual", platform_user_id="cross-1"
    )
    asset = Asset(name="Cross Snapshot Asset", market="SH", symbol="CROSS1")
    db_session.add_all([investor, asset])
    db_session.flush()
    identity = build_cross_investor_input_identity(
        asset_id=asset.id,
        as_of=END,
        window_start=START,
        window_end=END,
        opinion_analysis_version=ANALYSIS_SPEC.analysis_version,
        attention_policy_version=ATTENTION_POLICY,
        thesis_comparison_version=THESIS_VERSION,
        consistency_policy_version=CONSISTENCY_POLICY,
        cross_investor_policy_version=CROSS_INVESTOR_POLICY_VERSION,
    )
    values = {
        "asset_id": asset.id,
        "as_of": END,
        "window_start": START,
        "window_end": END,
        "attention_occurrence_count": 0,
        "attention_investor_count": 0,
        "new_attention_investor_count": 0,
        "opinion_count": 0,
        "opinion_investor_count": 0,
        "bullish_investor_count": 0,
        "bearish_investor_count": 0,
        "neutral_investor_count": 0,
        "thesis_change_count": 0,
        "thesis_change_investor_count": 0,
        "thesis_reinforced_investor_count": 0,
        "thesis_changed_investor_count": 0,
        "portfolio_action_count": 0,
        "portfolio_action_investor_count": 0,
        "position_increased_count": 0,
        "position_decreased_count": 0,
        "consistency_count": 0,
        "consistency_investor_count": 0,
        "positive_alignment_count": 0,
        "negative_alignment_count": 0,
        "opinion_analysis_version": ANALYSIS_SPEC.analysis_version,
        "attention_policy_version": ATTENTION_POLICY,
        "thesis_comparison_version": THESIS_VERSION,
        "consistency_policy_version": CONSISTENCY_POLICY,
        "input_identity": identity,
    }
    command = CrossInvestorAssetSnapshotCreate(**values)
    repository = CrossInvestorAssetSnapshotRepository(db_session)

    first, created = repository.add_if_absent(command)
    second, reused = repository.add_if_absent(command)
    db_session.commit()

    assert created is True
    assert reused is False
    assert first.id == second.id
    assert db_session.scalar(select(func.count()).select_from(CrossInvestorAssetSnapshot)) == 1
