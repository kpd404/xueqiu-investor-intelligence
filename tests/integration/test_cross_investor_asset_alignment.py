from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.orm import Session

from contracts import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
    CrossInvestorAssetAlignmentCreate,
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    CrossInvestorContribution,
    DirectionalAlignmentState,
    OpinionCoverageState,
    OpinionDirection,
    build_cross_investor_alignment_input_identity,
    build_cross_investor_input_identity,
)
from database.models import Asset, Investor
from database.repositories import (
    CrossInvestorAssetAlignmentRepository,
    CrossInvestorAssetSnapshotRepository,
)
from intelligence.services.cross_investor_asset_alignment import (
    CrossInvestorAssetAlignmentIntegrityError,
    CrossInvestorAssetAlignmentService,
    CrossInvestorAssetSnapshotNotFoundError,
    classify_cross_investor_asset_snapshot,
)

ASSET_ID = uuid4()
SOURCE_SNAPSHOT_ID = uuid4()
INVESTOR_ONE = uuid4()
INVESTOR_TWO = uuid4()
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 7, tzinfo=UTC)
SOURCE_INPUT_IDENTITY = "a" * 64


def _contribution(
    investor_id: UUID,
    *,
    attention: bool = True,
    opinion_directions: tuple[OpinionDirection, ...] = (),
) -> CrossInvestorContribution:
    attention_ids = (uuid4(),) if attention else ()
    opinion_ids = tuple(uuid4() for _ in opinion_directions)
    latest_direction = opinion_directions[-1] if opinion_directions else None
    return CrossInvestorContribution(
        investor_id=investor_id,
        attention_occurrence_ids=attention_ids,
        attention_occurrence_count=len(attention_ids),
        first_attention_occurrence_id=attention_ids[0] if attention_ids else None,
        first_attention_published_time=START if attention_ids else None,
        window_opinion_ids=opinion_ids,
        window_opinion_count=len(opinion_ids),
        latest_window_opinion_id=opinion_ids[-1] if opinion_ids else None,
        latest_window_opinion_direction=latest_direction,
        latest_window_opinion_time=END if opinion_ids else None,
    )


def _source_snapshot(
    *contributions: CrossInvestorContribution,
    input_identity: str = SOURCE_INPUT_IDENTITY,
) -> CrossInvestorAssetSnapshotView:
    attention_investors = {
        contribution.investor_id
        for contribution in contributions
        if contribution.attention_occurrence_count > 0
    }
    opinion_investors = {
        contribution.investor_id
        for contribution in contributions
        if contribution.window_opinion_count > 0
    }
    latest_directions = [
        contribution.latest_window_opinion_direction
        for contribution in contributions
        if contribution.window_opinion_count > 0
    ]
    return CrossInvestorAssetSnapshotView(
        id=SOURCE_SNAPSHOT_ID,
        asset_id=ASSET_ID,
        as_of=END,
        window_start=START,
        window_end=END,
        attention_occurrence_count=sum(
            contribution.attention_occurrence_count for contribution in contributions
        ),
        attention_investor_count=len(attention_investors),
        new_attention_investor_count=0,
        opinion_count=sum(contribution.window_opinion_count for contribution in contributions),
        opinion_investor_count=len(opinion_investors),
        bullish_investor_count=sum(
            direction in {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}
            for direction in latest_directions
        ),
        bearish_investor_count=sum(
            direction in {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}
            for direction in latest_directions
        ),
        neutral_investor_count=sum(
            direction is OpinionDirection.NEUTRAL for direction in latest_directions
        ),
        thesis_change_count=0,
        thesis_change_investor_count=0,
        thesis_reinforced_investor_count=0,
        thesis_changed_investor_count=0,
        portfolio_action_count=0,
        portfolio_action_investor_count=0,
        position_increased_count=0,
        position_decreased_count=0,
        consistency_count=0,
        consistency_investor_count=0,
        positive_alignment_count=0,
        negative_alignment_count=0,
        contributions=contributions,
        opinion_analysis_version="alignment-test-analysis",
        attention_policy_version="alignment-test-attention",
        thesis_comparison_version="alignment-test-thesis",
        consistency_policy_version="alignment-test-consistency",
        cross_investor_policy_version=CROSS_INVESTOR_POLICY_VERSION,
        calculated_at=END,
        input_identity=input_identity,
    )


class _SnapshotReader:
    def __init__(self, snapshot: CrossInvestorAssetSnapshotView) -> None:
        self.snapshot = snapshot

    def get(self, snapshot_id: UUID) -> CrossInvestorAssetSnapshotView | None:
        return self.snapshot if snapshot_id == self.snapshot.id else None


class _AlignmentWriter:
    def __init__(self) -> None:
        self.values: dict[str, CrossInvestorAssetAlignmentView] = {}

    def add_if_absent(self, command: CrossInvestorAssetAlignmentCreate):
        existing = self.values.get(command.input_identity)
        if existing is not None:
            return existing, False
        view = CrossInvestorAssetAlignmentView(
            id=uuid4(),
            **command.model_dump(mode="json"),
        )
        self.values[command.input_identity] = view
        return view, True


class _Uow:
    def __init__(self, snapshot: CrossInvestorAssetSnapshotView) -> None:
        self.cross_investor_asset_snapshots = _SnapshotReader(snapshot)
        self.cross_investor_asset_alignments = _AlignmentWriter()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        return None


def _service(
    uow: _Uow,
    *,
    policy_version: str = CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
) -> CrossInvestorAssetAlignmentService:
    return CrossInvestorAssetAlignmentService(
        lambda: uow,
        alignment_policy_version=policy_version,
    )


def test_case_a_none_coverage_and_insufficient_direction():
    snapshot = _source_snapshot(_contribution(INVESTOR_ONE), _contribution(INVESTOR_TWO))

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert coverage is OpinionCoverageState.NONE
    assert direction is DirectionalAlignmentState.INSUFFICIENT_EVIDENCE


def test_case_b_partial_coverage_and_insufficient_direction():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BULLISH,)),
        _contribution(INVESTOR_TWO),
    )

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert coverage is OpinionCoverageState.PARTIAL
    assert direction is DirectionalAlignmentState.INSUFFICIENT_EVIDENCE


def test_case_c_complete_bullish_alignment():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BULLISH,)),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.BULLISH,)),
    )

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert coverage is OpinionCoverageState.COMPLETE
    assert direction is DirectionalAlignmentState.ALIGNED_BULLISH


def test_case_d_complete_bearish_alignment():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BEARISH,)),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.BEARISH,)),
    )

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert coverage is OpinionCoverageState.COMPLETE
    assert direction is DirectionalAlignmentState.ALIGNED_BEARISH


def test_case_e_complete_neutral_alignment():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.NEUTRAL,)),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.NEUTRAL,)),
    )

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert coverage is OpinionCoverageState.COMPLETE
    assert direction is DirectionalAlignmentState.ALIGNED_NEUTRAL


def test_case_f_complete_mixed_direction():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BULLISH,)),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.BEARISH,)),
    )

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert coverage is OpinionCoverageState.COMPLETE
    assert direction is DirectionalAlignmentState.MIXED_DIRECTION


def test_case_g_repeated_opinions_do_not_add_investor_votes():
    snapshot = _source_snapshot(
        _contribution(
            INVESTOR_ONE,
            opinion_directions=(OpinionDirection.BULLISH, OpinionDirection.BULLISH),
        ),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.BULLISH,)),
    )

    coverage, direction = classify_cross_investor_asset_snapshot(snapshot)

    assert snapshot.opinion_count == 3
    assert snapshot.opinion_investor_count == 2
    assert coverage is OpinionCoverageState.COMPLETE
    assert direction is DirectionalAlignmentState.ALIGNED_BULLISH


@pytest.mark.parametrize(
    ("direction", "expected"),
    [
        (OpinionDirection.STRONG_BULLISH, DirectionalAlignmentState.ALIGNED_BULLISH),
        (OpinionDirection.STRONG_BEARISH, DirectionalAlignmentState.ALIGNED_BEARISH),
    ],
)
def test_case_h_strong_directions_map_to_their_side(direction, expected):
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(direction,)),
        _contribution(INVESTOR_TWO, opinion_directions=(direction,)),
    )

    _coverage, actual = classify_cross_investor_asset_snapshot(snapshot)

    assert actual is expected


def test_case_i_opinion_investor_outside_attention_is_rejected():
    unexpected_investor = uuid4()
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE),
        _contribution(INVESTOR_TWO),
        _contribution(
            unexpected_investor, attention=False, opinion_directions=(OpinionDirection.BULLISH,)
        ),
    )

    with pytest.raises(CrossInvestorAssetAlignmentIntegrityError, match="subset"):
        classify_cross_investor_asset_snapshot(snapshot)


def test_case_j_same_input_reuses_alignment_artifact():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BULLISH,)),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.BULLISH,)),
    )
    uow = _Uow(snapshot)
    service = _service(uow)

    first = service.calculate(SOURCE_SNAPSHOT_ID)
    second = service.calculate(SOURCE_SNAPSHOT_ID)

    assert first.id == second.id
    assert first.input_identity == build_cross_investor_alignment_input_identity(
        source_snapshot_input_identity=SOURCE_INPUT_IDENTITY,
        alignment_policy_version=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    )
    assert len(uow.cross_investor_asset_alignments.values) == 1


def test_case_k_policy_change_creates_new_immutable_artifact():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BULLISH,)),
        _contribution(INVESTOR_TWO, opinion_directions=(OpinionDirection.BULLISH,)),
    )
    uow = _Uow(snapshot)

    first = _service(uow).calculate(SOURCE_SNAPSHOT_ID)
    second = _service(uow, policy_version="cross-investor-directional-alignment-v2").calculate(
        SOURCE_SNAPSHOT_ID
    )

    assert first.id != second.id
    assert first.input_identity != second.input_identity
    assert first.alignment_policy_version != second.alignment_policy_version
    assert len(uow.cross_investor_asset_alignments.values) == 2


def test_alignment_requires_two_attention_investors():
    snapshot = _source_snapshot(
        _contribution(INVESTOR_ONE, opinion_directions=(OpinionDirection.BULLISH,)),
    )

    with pytest.raises(CrossInvestorAssetAlignmentIntegrityError, match="at least two"):
        classify_cross_investor_asset_snapshot(snapshot)


def test_missing_source_snapshot_is_explicit():
    snapshot = _source_snapshot(_contribution(INVESTOR_ONE), _contribution(INVESTOR_TWO))
    uow = _Uow(snapshot)

    with pytest.raises(CrossInvestorAssetSnapshotNotFoundError):
        _service(uow).calculate(uuid4())


def test_alignment_repository_is_idempotent_and_lists_provenance(db_session: Session):
    investor = Investor(
        name="Alignment Investor", platform="manual", platform_user_id="alignment-1"
    )
    asset = Asset(name="Alignment Asset", market="SH", symbol="ALIGN1")
    db_session.add_all([investor, asset])
    db_session.flush()

    source_identity = build_cross_investor_input_identity(
        asset_id=asset.id,
        as_of=END,
        window_start=START,
        window_end=END,
        opinion_analysis_version="alignment-test-analysis",
        attention_policy_version="alignment-test-attention",
        thesis_comparison_version="alignment-test-thesis",
        consistency_policy_version="alignment-test-consistency",
        cross_investor_policy_version=CROSS_INVESTOR_POLICY_VERSION,
    )
    source = CrossInvestorAssetSnapshotRepository(db_session).create(
        _source_snapshot(input_identity=source_identity).model_copy(update={"asset_id": asset.id})
    )
    alignment = CrossInvestorAssetAlignmentCreate(
        asset_id=asset.id,
        source_snapshot_id=source.id,
        opinion_coverage_state=OpinionCoverageState.COMPLETE,
        directional_alignment_state=DirectionalAlignmentState.ALIGNED_BULLISH,
        alignment_policy_version=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
        input_identity=build_cross_investor_alignment_input_identity(
            source_snapshot_input_identity=source.input_identity,
            alignment_policy_version=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
        ),
        calculated_at=END,
        created_at=END,
    )
    repository = CrossInvestorAssetAlignmentRepository(db_session)

    first, created = repository.add_if_absent(alignment)
    second, reused = repository.add_if_absent(alignment)
    db_session.commit()

    assert created is True
    assert reused is False
    assert first.id == second.id
    assert repository.get_by_input_identity(alignment.input_identity) is not None
    assert [item.id for item in repository.list_by_asset(asset.id)] == [first.id]
    assert [item.id for item in repository.list_by_source_snapshot(source.id)] == [first.id]
