from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from contracts import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
    CROSS_INVESTOR_POLICY_VERSION,
    ConsensusEvidenceState,
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    CrossInvestorContribution,
    OpinionCoverageState,
    OpinionDirection,
)
from intelligence.services.cross_investor_consensus_evidence import (
    CrossInvestorConsensusEvidenceIntegrityError,
    CrossInvestorConsensusEvidenceService,
    build_cross_investor_consensus_evidence,
)

ASSET_ID = uuid4()
SNAPSHOT_ID = uuid4()
START = datetime(2026, 9, 1, tzinfo=UTC)
END = datetime(2026, 9, 9, tzinfo=UTC)
SOURCE_INPUT_IDENTITY = "a" * 64
ALIGNMENT_INPUT_IDENTITY = "b" * 64


def _contribution(
    investor_id: UUID,
    *,
    directions: tuple[OpinionDirection, ...] = (),
    attention: bool = True,
) -> CrossInvestorContribution:
    attention_ids = (uuid4(),) if attention else ()
    opinion_ids = tuple(uuid4() for _ in directions)
    return CrossInvestorContribution(
        investor_id=investor_id,
        attention_occurrence_ids=attention_ids,
        attention_occurrence_count=len(attention_ids),
        first_attention_occurrence_id=attention_ids[0] if attention_ids else None,
        first_attention_published_time=START if attention_ids else None,
        window_opinion_ids=opinion_ids,
        window_opinion_count=len(opinion_ids),
        latest_window_opinion_id=opinion_ids[-1] if opinion_ids else None,
        latest_window_opinion_direction=directions[-1] if directions else None,
        latest_window_opinion_time=END if directions else None,
    )


def _snapshot(*contributions: CrossInvestorContribution) -> CrossInvestorAssetSnapshotView:
    attention = [item for item in contributions if item.attention_occurrence_count > 0]
    opinions = [item for item in attention if item.window_opinion_count > 0]
    directions = [item.latest_window_opinion_direction for item in opinions]
    return CrossInvestorAssetSnapshotView(
        id=SNAPSHOT_ID,
        asset_id=ASSET_ID,
        as_of=END,
        window_start=START,
        window_end=END,
        attention_occurrence_count=sum(item.attention_occurrence_count for item in attention),
        attention_investor_count=len(attention),
        new_attention_investor_count=0,
        opinion_count=sum(item.window_opinion_count for item in opinions),
        opinion_investor_count=len(opinions),
        bullish_investor_count=sum(
            direction in {OpinionDirection.BULLISH, OpinionDirection.STRONG_BULLISH}
            for direction in directions
        ),
        bearish_investor_count=sum(
            direction in {OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH}
            for direction in directions
        ),
        neutral_investor_count=sum(
            direction is OpinionDirection.NEUTRAL for direction in directions
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
        opinion_analysis_version="analysis-v1",
        attention_policy_version="attention-v1",
        thesis_comparison_version="thesis-v1",
        consistency_policy_version="consistency-v1",
        cross_investor_policy_version=CROSS_INVESTOR_POLICY_VERSION,
        calculated_at=END,
        input_identity=SOURCE_INPUT_IDENTITY,
    )


def _alignment(snapshot: CrossInvestorAssetSnapshotView) -> CrossInvestorAssetAlignmentView:
    from intelligence.services.cross_investor_asset_alignment import (
        classify_cross_investor_asset_snapshot,
    )

    coverage, directional = classify_cross_investor_asset_snapshot(snapshot)
    return CrossInvestorAssetAlignmentView(
        id=uuid4(),
        asset_id=snapshot.asset_id,
        source_snapshot_id=snapshot.id,
        opinion_coverage_state=coverage,
        directional_alignment_state=directional,
        alignment_policy_version=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
        input_identity=ALIGNMENT_INPUT_IDENTITY,
        calculated_at=END,
        created_at=END,
    )


@pytest.mark.parametrize(
    ("directions", "expected"),
    [
        (
            (OpinionDirection.BULLISH, OpinionDirection.BULLISH),
            ConsensusEvidenceState.INSUFFICIENT_EVIDENCE,
        ),
        (
            (OpinionDirection.BULLISH, OpinionDirection.BULLISH, OpinionDirection.BULLISH),
            ConsensusEvidenceState.CONSENSUS_BULLISH,
        ),
        (
            (OpinionDirection.BEARISH, OpinionDirection.STRONG_BEARISH, OpinionDirection.BEARISH),
            ConsensusEvidenceState.CONSENSUS_BEARISH,
        ),
        (
            (OpinionDirection.NEUTRAL, OpinionDirection.NEUTRAL, OpinionDirection.NEUTRAL),
            ConsensusEvidenceState.CONSENSUS_NEUTRAL,
        ),
        (
            (OpinionDirection.BULLISH, OpinionDirection.BULLISH, OpinionDirection.BEARISH),
            ConsensusEvidenceState.DIVERGENT,
        ),
        (
            (
                OpinionDirection.BULLISH,
                OpinionDirection.BEARISH,
                OpinionDirection.NEUTRAL,
            ),
            ConsensusEvidenceState.DIVERGENT,
        ),
    ],
)
def test_consensus_state_uses_latest_direction_per_investor(directions, expected):
    snapshot = _snapshot(
        *(_contribution(uuid4(), directions=(direction,)) for direction in directions)
    )

    evidence = build_cross_investor_consensus_evidence(
        snapshot,
        _alignment(snapshot),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1,
        calculated_at=END,
    )

    assert evidence.consensus_state is expected


@pytest.mark.parametrize(
    "consensus_policy_version",
    [
        CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1,
        CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
    ],
)
def test_repeated_opinions_do_not_add_votes(consensus_policy_version):
    snapshot = _snapshot(
        _contribution(
            uuid4(),
            directions=(OpinionDirection.BEARISH, OpinionDirection.BULLISH),
        ),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
    )

    evidence = build_cross_investor_consensus_evidence(
        snapshot,
        _alignment(snapshot),
        consensus_policy_version=consensus_policy_version,
        calculated_at=END,
    )

    assert evidence.opinion_investor_count == 3
    assert evidence.opinion_coverage_state is OpinionCoverageState.COMPLETE
    assert evidence.bullish_investor_count == 3
    assert evidence.bearish_investor_count == 0
    assert len(evidence.latest_opinions) == 3
    assert evidence.consensus_state is ConsensusEvidenceState.CONSENSUS_BULLISH


def test_partial_attention_coverage_is_preserved():
    snapshot = _snapshot(
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4()),
        _contribution(uuid4()),
    )

    evidence = build_cross_investor_consensus_evidence(
        snapshot,
        _alignment(snapshot),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1,
        calculated_at=END,
    )

    assert evidence.attention_investor_count == 5
    assert evidence.opinion_investor_count == 3
    assert evidence.opinion_coverage_state is OpinionCoverageState.PARTIAL
    assert evidence.consensus_state is ConsensusEvidenceState.CONSENSUS_BULLISH


def test_invalid_asset_provenance_is_rejected():
    snapshot = _snapshot(
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
    )
    alignment = _alignment(snapshot).model_copy(update={"asset_id": uuid4()})

    with pytest.raises(CrossInvestorConsensusEvidenceIntegrityError, match="same Asset"):
        build_cross_investor_consensus_evidence(
            snapshot,
            alignment,
            consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1,
            calculated_at=END,
        )


def test_opinion_outside_attention_is_rejected():
    outside = _contribution(
        uuid4(),
        directions=(OpinionDirection.BULLISH,),
        attention=False,
    )
    base = _snapshot(_contribution(uuid4()), _contribution(uuid4()))
    snapshot = base.model_copy(
        update={
            "contributions": base.contributions + (outside,),
            "opinion_count": 1,
            "opinion_investor_count": 1,
            "bullish_investor_count": 1,
        }
    )

    with pytest.raises(ValueError, match="subset"):
        _alignment(snapshot)


@pytest.mark.parametrize(
    ("directions", "expected"),
    [
        (
            (
                OpinionDirection.BULLISH,
                OpinionDirection.BULLISH,
                OpinionDirection.BULLISH,
            ),
            ConsensusEvidenceState.CONSENSUS_BULLISH,
        ),
        (
            (
                OpinionDirection.BEARISH,
                OpinionDirection.BEARISH,
                OpinionDirection.BEARISH,
            ),
            ConsensusEvidenceState.CONSENSUS_BEARISH,
        ),
        (
            (
                OpinionDirection.NEUTRAL,
                OpinionDirection.NEUTRAL,
                OpinionDirection.NEUTRAL,
            ),
            ConsensusEvidenceState.CONSENSUS_NEUTRAL,
        ),
        (
            (
                OpinionDirection.BULLISH,
                OpinionDirection.BEARISH,
                OpinionDirection.NEUTRAL,
            ),
            ConsensusEvidenceState.DIVERGENT,
        ),
        (
            (
                OpinionDirection.BULLISH,
                OpinionDirection.BULLISH,
                OpinionDirection.BEARISH,
            ),
            ConsensusEvidenceState.DIVERGENT,
        ),
        (
            (
                OpinionDirection.BULLISH,
                OpinionDirection.NEUTRAL,
                OpinionDirection.NEUTRAL,
            ),
            ConsensusEvidenceState.MIXED_WITH_NEUTRAL,
        ),
        (
            (
                OpinionDirection.BEARISH,
                OpinionDirection.NEUTRAL,
                OpinionDirection.NEUTRAL,
            ),
            ConsensusEvidenceState.MIXED_WITH_NEUTRAL,
        ),
        (
            (OpinionDirection.BULLISH, OpinionDirection.NEUTRAL),
            ConsensusEvidenceState.INSUFFICIENT_EVIDENCE,
        ),
    ],
)
def test_v2_consensus_taxonomy(directions, expected):
    snapshot = _snapshot(
        *(_contribution(uuid4(), directions=(direction,)) for direction in directions)
    )

    evidence = build_cross_investor_consensus_evidence(
        snapshot,
        _alignment(snapshot),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
        calculated_at=END,
    )

    assert evidence.consensus_state is expected


def test_v2_strong_directions_map_to_bullish_and_bearish_sides():
    snapshot = _snapshot(
        _contribution(uuid4(), directions=(OpinionDirection.STRONG_BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.STRONG_BEARISH,)),
    )

    evidence = build_cross_investor_consensus_evidence(
        snapshot,
        _alignment(snapshot),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
        calculated_at=END,
    )

    assert evidence.bullish_investor_count == 2
    assert evidence.bearish_investor_count == 1
    assert evidence.neutral_investor_count == 0
    assert evidence.consensus_state is ConsensusEvidenceState.DIVERGENT


class _SnapshotReader:
    def __init__(self, snapshot):
        self.snapshot = snapshot

    def get(self, snapshot_id):
        return self.snapshot if snapshot_id == self.snapshot.id else None


class _AlignmentReader:
    def __init__(self, alignment):
        self.alignment = alignment

    def get(self, alignment_id):
        return self.alignment if alignment_id == self.alignment.id else None

    def list_by_source_snapshot(self, source_snapshot_id):
        return [self.alignment] if source_snapshot_id == self.alignment.source_snapshot_id else []


class _EvidenceWriter:
    def __init__(self):
        self.values = {}

    def add_if_absent(self, evidence):
        existing = self.values.get(evidence.input_identity)
        if existing is not None:
            return existing, False
        view = evidence.model_copy(update={"id": uuid4()})
        self.values[evidence.input_identity] = view
        return view, True


class _UnitOfWork:
    def __init__(self, snapshot, alignment):
        self.cross_investor_asset_snapshots = _SnapshotReader(snapshot)
        self.cross_investor_asset_alignments = _AlignmentReader(alignment)
        self.cross_investor_consensus_evidences = _EvidenceWriter()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def commit(self):
        return None


def test_identical_input_is_idempotent_and_policy_change_appends():
    snapshot = _snapshot(
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
        _contribution(uuid4(), directions=(OpinionDirection.BULLISH,)),
    )
    alignment = _alignment(snapshot)
    uow = _UnitOfWork(snapshot, alignment)
    v1_service = CrossInvestorConsensusEvidenceService(
        lambda: uow,
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1,
    )

    first = v1_service.calculate(snapshot.id, alignment.id)
    second = v1_service.calculate(snapshot.id, alignment.id)
    v2_service = CrossInvestorConsensusEvidenceService(
        lambda: uow,
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
    )
    changed = v2_service.calculate(snapshot.id, alignment.id)
    repeated_v2 = v2_service.calculate(snapshot.id, alignment.id)

    assert first.id == second.id
    assert first.input_identity == second.input_identity
    assert first.consensus_policy_version == CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V1
    assert changed.id != first.id
    assert changed.input_identity != first.input_identity
    assert repeated_v2.id == changed.id
    assert repeated_v2.input_identity == changed.input_identity
    assert changed.consensus_policy_version == CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2
    assert len(uow.cross_investor_consensus_evidences.values) == 2
