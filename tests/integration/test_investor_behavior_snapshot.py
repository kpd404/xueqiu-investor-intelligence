from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy.orm import Session

from behavior.services.investor_behavior_snapshot import InvestorBehaviorSnapshotService
from contracts import (
    BEHAVIOR_SNAPSHOT_POLICY_VERSION,
    CONSISTENCY_POLICY_VERSION,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceView,
    ConsistencyType,
    EffectiveAnalysisPolicy,
    InvestorBehaviorSnapshotCreate,
    InvestorBehaviorSnapshotView,
    OpinionActionConsistencyView,
    OpinionDirection,
    OpinionTimelineEntry,
    PortfolioActionType,
    PortfolioActionView,
    ThesisChangeType,
    ThesisChangeView,
)
from contracts.analysis import AnalysisSpec
from database.models import Investor
from database.repositories import InvestorBehaviorSnapshotRepository

ASSET_ONE = uuid4()
ASSET_TWO = uuid4()
INVESTOR_ID = uuid4()
ANALYSIS_SPEC = AnalysisSpec.for_provider(
    provider_id="test-provider",
    model_version="test-model",
    prompt_version="test-prompt",
    schema_version="test-schema",
    analysis_policy_version="test-policy",
)
POLICY = EffectiveAnalysisPolicy(active_spec=ANALYSIS_SPEC)


class _Reader:
    def __init__(self, values: list[object]) -> None:
        self.values = values


class _Opinions(_Reader):
    def list_effective_timeline_by_investor(self, investor_id, policy):
        return self.values


class _Attention(_Reader):
    def list_effective_by_investor(self, investor_id, policy):
        return self.values


class _Thesis(_Reader):
    def list_effective_by_investor(
        self,
        investor_id,
        policy,
        comparison_version=None,
        *,
        as_of=None,
    ):
        return self.values


class _Actions(_Reader):
    def list_by_investor(self, investor_id):
        return self.values


class _Consistency(_Reader):
    def list_by_investor(
        self,
        investor_id,
        *,
        opinion_analysis_version=None,
        consistency_policy_version=None,
    ):
        return self.values


class _SnapshotWriter:
    def __init__(self) -> None:
        self.values: dict[str, InvestorBehaviorSnapshotView] = {}

    def add_if_absent(self, command: InvestorBehaviorSnapshotCreate):
        existing = self.values.get(command.input_identity)
        if existing is not None:
            return existing, False
        view = InvestorBehaviorSnapshotView(id=uuid4(), **command.model_dump())
        self.values[command.input_identity] = view
        return view, True


class _Uow:
    def __init__(self, *, attention, opinions, thesis, actions, consistencies, snapshots) -> None:
        self.attention_occurrences = _Attention(attention)
        self.opinions = _Opinions(opinions)
        self.thesis_changes = _Thesis(thesis)
        self.portfolio_actions = _Actions(actions)
        self.consistencies = _Consistency(consistencies)
        self.behavior_snapshots = snapshots
        self.commit_count = 0

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        self.commit_count += 1


def _attention(asset_id, published_time):
    return AttentionOccurrenceView(
        id=uuid4(),
        investor_id=INVESTOR_ID,
        asset_id=asset_id,
        event_id=uuid4(),
        published_time=published_time,
        evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
        evidence=(
            AttentionEvidence(
                evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                matched_by="NAME",
                reference="Asset",
            ),
        ),
        attention_policy_version="attention-occurrence-v1",
        calculated_at=published_time + timedelta(minutes=1),
    )


def _opinion(asset_id, published_time, direction):
    return OpinionTimelineEntry(
        opinion_id=uuid4(),
        event_id=uuid4(),
        investor_id=INVESTOR_ID,
        asset_id=asset_id,
        direction=direction,
        strength=80,
        confidence=0.9,
        published_time=published_time,
        generated_time=published_time + timedelta(minutes=2),
    )


def _thesis(asset_id, effective_time):
    return ThesisChangeView(
        id=uuid4(),
        investor_id=INVESTOR_ID,
        asset_id=asset_id,
        previous_opinion_id=None,
        current_opinion_id=uuid4(),
        previous_event_id=None,
        current_event_id=uuid4(),
        effective_time=effective_time,
        change_type=ThesisChangeType.THESIS_REINFORCED,
        confidence=0.8,
        summary="same thesis with supporting evidence",
        evidence=("same business driver",),
        opinion_analysis_version=ANALYSIS_SPEC.analysis_version,
        comparison_version="comparison-v1",
        calculated_at=effective_time + timedelta(minutes=3),
        input_identity=str(uuid4()),
    )


def _action(asset_id, effective_time, action_type):
    previous_position_id = uuid4()
    current_position_id = uuid4()
    return PortfolioActionView(
        id=uuid4(),
        portfolio_id=uuid4(),
        asset_id=asset_id,
        asset_reference_id=None,
        previous_snapshot_batch_id=uuid4(),
        current_snapshot_batch_id=uuid4(),
        previous_position_snapshot_id=previous_position_id,
        current_position_snapshot_id=current_position_id,
        action_type=action_type,
        effective_time=effective_time,
        calculated_at=effective_time + timedelta(minutes=4),
        created_at=effective_time + timedelta(minutes=4),
    )


def _consistency(asset_id, effective_time):
    opinion_id = uuid4()
    action_id = uuid4()
    import json

    identity = json.dumps(
        {
            "consistency_policy_version": CONSISTENCY_POLICY_VERSION,
            "opinion_id": str(opinion_id),
            "portfolio_action_id": str(action_id),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return OpinionActionConsistencyView(
        id=uuid4(),
        investor_id=INVESTOR_ID,
        asset_id=asset_id,
        opinion_id=opinion_id,
        opinion_direction=OpinionDirection.BULLISH,
        portfolio_action_id=action_id,
        action_type=PortfolioActionType.POSITION_INCREASED,
        consistency_type=ConsistencyType.POSITIVE_ALIGNMENT,
        confidence=0.8,
        evidence={},
        effective_time=effective_time,
        calculated_at=effective_time + timedelta(minutes=5),
        opinion_analysis_version=ANALYSIS_SPEC.analysis_version,
        consistency_policy_version=CONSISTENCY_POLICY_VERSION,
        input_identity=identity,
    )


def test_behavior_snapshot_aggregates_active_fact_time_and_is_idempotent():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 7, tzinfo=UTC)
    old = start - timedelta(days=4)
    future = end + timedelta(days=1)
    attention = [
        _attention(ASSET_ONE, old),
        _attention(ASSET_ONE, start + timedelta(days=1)),
        _attention(ASSET_TWO, start + timedelta(days=2)),
    ]
    opinions = [
        _opinion(ASSET_ONE, start + timedelta(days=1), OpinionDirection.BULLISH),
        _opinion(ASSET_TWO, future, OpinionDirection.BEARISH),
    ]
    thesis = [_thesis(ASSET_ONE, start + timedelta(days=2))]
    actions = [
        _action(ASSET_ONE, start + timedelta(days=3), PortfolioActionType.POSITION_INCREASED),
        _action(ASSET_TWO, future, PortfolioActionType.POSITION_DECREASED),
    ]
    consistencies = [_consistency(ASSET_ONE, start + timedelta(days=3))]
    snapshots = _SnapshotWriter()
    uow = _Uow(
        attention=attention,
        opinions=opinions,
        thesis=thesis,
        actions=actions,
        consistencies=consistencies,
        snapshots=snapshots,
    )
    service = InvestorBehaviorSnapshotService(
        lambda: uow,
        POLICY,
        behavior_policy_version=BEHAVIOR_SNAPSHOT_POLICY_VERSION,
    )

    first = service.calculate(INVESTOR_ID, start, end)
    second = service.calculate(INVESTOR_ID, start, end)

    assert first.id == second.id
    assert first.attention_asset_count == 2
    assert first.attention_occurrence_count == 2
    assert first.new_attention_count == 1
    assert first.opinion_count == 1
    assert first.bullish_count == 1
    assert first.bearish_count == 0
    assert first.thesis_change_count == 1
    assert first.thesis_reinforced_count == 1
    assert first.portfolio_action_count == 1
    assert first.position_increased_count == 1
    assert first.position_decreased_count == 0
    assert first.positive_alignment_count == 1
    assert first.negative_alignment_count == 0
    assert first.as_of == end
    assert len(snapshots.values) == 1
    assert uow.commit_count == 2


def test_behavior_snapshot_window_identity_changes_with_window_end():
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 7, tzinfo=UTC)
    snapshots = _SnapshotWriter()
    uow = _Uow(
        attention=[],
        opinions=[],
        thesis=[],
        actions=[],
        consistencies=[],
        snapshots=snapshots,
    )
    service = InvestorBehaviorSnapshotService(lambda: uow, POLICY)

    first = service.process(INVESTOR_ID, start, end)
    second = service.process(INVESTOR_ID, start, end + timedelta(days=1))

    assert first.id != second.id
    assert len(snapshots.values) == 2


def test_behavior_snapshot_repository_database_identity_is_idempotent(db_session: Session):
    investor = Investor(name="Behavior Investor", platform="manual", platform_user_id="behavior-1")
    db_session.add(investor)
    db_session.flush()
    start = datetime(2026, 9, 1, tzinfo=UTC)
    end = datetime(2026, 9, 7, tzinfo=UTC)
    command = InvestorBehaviorSnapshotCreate(
        investor_id=investor.id,
        as_of=end,
        window_start=start,
        window_end=end,
        attention_asset_count=0,
        attention_occurrence_count=0,
        new_attention_count=0,
        opinion_count=0,
        bullish_count=0,
        bearish_count=0,
        thesis_change_count=0,
        thesis_reinforced_count=0,
        thesis_changed_count=0,
        portfolio_action_count=0,
        position_increased_count=0,
        position_decreased_count=0,
        positive_alignment_count=0,
        negative_alignment_count=0,
        input_identity=(
            '{"behavior_policy_version":"investor-behavior-snapshot-v1",'
            f'"investor_id":"{investor.id}",'
            '"window_end":"2026-09-07T00:00:00+00:00",'
            '"window_start":"2026-09-01T00:00:00+00:00"}'
        ),
    )
    repository = InvestorBehaviorSnapshotRepository(db_session)

    first, created = repository.add_if_absent(command)
    second, reused = repository.add_if_absent(command)
    db_session.commit()

    assert created is True
    assert reused is False
    assert first.id == second.id
    assert len(repository.list_by_investor(investor.id)) == 1
