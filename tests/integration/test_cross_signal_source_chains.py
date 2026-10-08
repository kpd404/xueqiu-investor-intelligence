"""Real upstream rows and persisted legacy Signals; validation never calculates."""

from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select

from contracts import (
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceCreate,
    EventAnalysisStatus,
    SignalCreate,
    SignalState,
    SignalType,
    ThesisChangeType,
)
from database.models import (
    Asset,
    CrossInvestorAssetAlignment,
    CrossInvestorAssetSnapshot,
    CrossInvestorConsensusEvidence,
    EventAnalysis,
    Investor,
    Opinion,
)
from database.repositories.attention_occurrences import AttentionOccurrenceRepository
from database.unit_of_work import (
    SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork,
    SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork,
    SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork,
)
from intelligence.events.aggregator import IntelligenceEventAggregator
from intelligence.services.cross_investor_asset_alignment import CrossInvestorAssetAlignmentService
from intelligence.services.cross_investor_asset_snapshot import CrossInvestorAssetSnapshotService
from intelligence.services.cross_investor_consensus_evidence import (
    CrossInvestorConsensusEvidenceService,
)
from signal_engine.repository import SignalRepository
from signal_engine.service import SignalGenerator
from tests.integration import test_thesis_change_signals as signal_fixtures
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_effective_thesis_signals import _shared_asset_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion, _seed_change

production_policies = signal_fixtures.production_policies
START, END = FACT_TIME - timedelta(days=2), FACT_TIME + timedelta(days=1)
CROSS = (SignalType.CROSS_INVESTOR_ALIGNMENT, SignalType.CONSENSUS_CHANGE)


def _chain(factory, policies):
    first = _seed_change(factory, policies, ThesisChangeType.THESIS_CHANGED)
    sources = [first] + [
        _shared_asset_change(
            factory, policies, first.asset_id, ThesisChangeType.THESIS_CHANGED, FACT_TIME
        )
        for _ in range(2)
    ]
    with factory() as session:
        for source in sources:
            opinion = session.get(Opinion, source.current_opinion_id)
            AttentionOccurrenceRepository(session).replace_for_event(
                source.current_event_id,
                "attention-occurrence-v1",
                (
                    AttentionOccurrenceCreate(
                        investor_id=source.investor_id,
                        asset_id=source.asset_id,
                        event_id=source.current_event_id,
                        published_time=FACT_TIME,
                        evidence_types=(AttentionEvidenceType.OPINION,),
                        evidence=(
                            AttentionEvidence(
                                evidence_type=AttentionEvidenceType.OPINION, matched_by="fixture"
                            ),
                        ),
                        analysis_id=opinion.analysis_id,
                        opinion_id=opinion.id,
                        attention_policy_version="attention-occurrence-v1",
                        calculated_at=END,
                    ),
                ),
            )
        session.commit()
    # Setup only: actual persisted valid artifacts. The validation paths below
    # must never call calculate or rebuild them.
    snapshot = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(factory)
    ).calculate(first.asset_id, START, END)
    alignment = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(factory)
    ).calculate(snapshot.id)
    consensus = CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(factory)
    ).calculate(snapshot.id, alignment.id)
    return sources, snapshot, alignment, consensus


def _legacy(factory, chain, kind, **updates):
    source = chain[2] if kind is SignalType.CROSS_INVESTOR_ALIGNMENT else chain[3]
    command = SignalCreate(
        asset_id=source.asset_id,
        signal_type=kind,
        source_type="CrossInvestorAssetAlignment"
        if kind is CROSS[0]
        else "CrossInvestorConsensusEvidence",
        source_id=source.id,
        created_at=END,
        observed_at=source.calculated_at,
        metadata={"alignment_state": "ALIGNED_BULLISH", "consensus_state": "CONSENSUS_BULLISH"},
    ).model_copy(update=updates)
    with factory() as session:
        result, _ = SignalRepository(session).add_if_absent(command)
        session.commit()
        return result


def _read(factory, kind):
    with factory() as session:
        return SignalRepository(session).list_cross_investor_signals_with_valid_references(
            signal_types=frozenset({kind})
        )


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize(
    "corruption",
    (
        "valid",
        "snapshot_policy",
        "opinion_policy",
        "attention_policy",
        "thesis_policy",
        "consistency_policy",
        "alignment_policy",
        "alignment_identity",
        "snapshot_identity",
        "alignment_asset",
        "alignment_snapshot",
        "missing_snapshot",
        "inactive_opinion",
        "failed_opinion",
        "late_predecessor",
        "fake_labels",
        "attention_source_policy",
        "attention_source_identity",
    ),
)
def test_candidate_and_persisted_signal_share_real_source_chain_validation(
    db_session_factory, production_policies, kind, corruption
):
    chain = _chain(db_session_factory, production_policies)
    signal = _legacy(db_session_factory, chain, kind)
    with db_session_factory() as session:
        snapshot = session.get(CrossInvestorAssetSnapshot, chain[1].id)
        alignment = session.get(CrossInvestorAssetAlignment, chain[2].id)
        policy_fields = {
            "snapshot_policy": "cross_investor_policy_version",
            "opinion_policy": "opinion_analysis_version",
            "attention_policy": "attention_policy_version",
            "thesis_policy": "thesis_comparison_version",
            "consistency_policy": "consistency_policy_version",
        }
        if corruption in policy_fields:
            setattr(snapshot, policy_fields[corruption], "inactive")
        elif corruption == "alignment_policy":
            alignment.alignment_policy_version = "inactive"
        elif corruption == "alignment_identity":
            alignment.input_identity = "0" * 64
        elif corruption == "snapshot_identity":
            snapshot.input_identity = "0" * 64
        elif corruption in {"alignment_snapshot", "missing_snapshot"}:
            alignment.source_snapshot_id = uuid4()
        elif corruption == "alignment_asset":
            other = Asset(name="Other", market="SH", symbol=str(uuid4())[:8])
            session.add(other)
            session.flush()
            alignment.asset_id = other.id
        elif corruption in {"inactive_opinion", "failed_opinion"}:
            opinion = session.get(Opinion, chain[0][0].current_opinion_id)
            analysis = session.get(EventAnalysis, opinion.analysis_id)
            if corruption == "inactive_opinion":
                analysis.analysis_version = "inactive"
            else:
                analysis.status = EventAnalysisStatus.FAILED
        elif corruption == "late_predecessor":
            source = chain[0][0]
            _add_opinion(
                session,
                session.get(Investor, source.investor_id),
                session.get(Asset, source.asset_id),
                production_policies[0].active_spec,
                FACT_TIME - timedelta(hours=12),
                EventAnalysisStatus.SUCCESS,
            )
        elif corruption == "fake_labels":
            values = [dict(value) for value in snapshot.contributions]
            values[0]["latest_window_opinion_direction"] = "BEARISH"
            snapshot.contributions = values
        elif corruption in {"attention_source_policy", "attention_source_identity"}:
            from database.models import AttentionOccurrence

            row = session.scalar(
                select(AttentionOccurrence).where(AttentionOccurrence.asset_id == snapshot.asset_id)
            )
            if corruption == "attention_source_policy":
                row.attention_policy_version = "inactive"
            else:
                row.opinion_id = chain[0][1].current_opinion_id
        session.commit()
    before = _snapshot(db_session_factory)
    plan = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,))
    assert len(plan.candidates) == int(corruption == "valid")
    if corruption == "valid":
        assert plan.candidates[0].source_id == signal.source_id
        assert plan.candidates[0].observed_at == FACT_TIME
        assert signal.observed_at == (chain[2] if kind is CROSS[0] else chain[3]).calculated_at
    assert _snapshot(db_session_factory) == before
    assert [value.id for value in _read(db_session_factory, kind)] == (
        [signal.id] if corruption == "valid" else []
    )
    aggregate = IntelligenceEventAggregator.from_production(db_session_factory).dry_run()
    assert len(aggregate.candidates) == int(corruption == "valid")
    assert _snapshot(db_session_factory) == before
    with db_session_factory() as session:
        assert SignalRepository(session).get(signal.id) == signal


@pytest.mark.parametrize(
    "corruption",
    (
        "policy",
        "identity",
        "asset",
        "snapshot",
        "alignment",
        "missing_alignment",
        "missing_consensus",
    ),
)
def test_consensus_references_are_checked(db_session_factory, production_policies, corruption):
    chain = _chain(db_session_factory, production_policies)
    updates = {"source_id": uuid4()} if corruption == "missing_consensus" else {}
    _legacy(db_session_factory, chain, SignalType.CONSENSUS_CHANGE, **updates)
    with db_session_factory() as session:
        row = session.get(CrossInvestorConsensusEvidence, chain[3].id)
        if corruption == "policy":
            row.consensus_policy_version = "inactive"
        elif corruption == "identity":
            row.input_identity = "0" * 64
        elif corruption == "asset":
            row.asset_id = uuid4()
        elif corruption == "snapshot":
            row.source_snapshot_id = uuid4()
        elif corruption in {"alignment", "missing_alignment"}:
            row.source_alignment_id = uuid4()
        session.commit()
    assert _read(db_session_factory, SignalType.CONSENSUS_CHANGE) == ()
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory).dry_run().candidates == ()
    )
    if corruption != "missing_consensus":
        assert (
            SignalGenerator.from_production(db_session_factory)
            .dry_run(signal_types=(SignalType.CONSENSUS_CHANGE,))
            .candidates
            == ()
        )


@pytest.mark.parametrize("kind", CROSS)
@pytest.mark.parametrize(
    "mismatch", ("state", "source_type", "missing_source", "asset", "investor")
)
def test_legacy_signal_must_match_source_identity(
    db_session_factory, production_policies, kind, mismatch
):
    chain = _chain(db_session_factory, production_policies)
    updates = {}
    if mismatch == "state":
        updates["state"] = SignalState.SUPERSEDED
    elif mismatch == "source_type":
        updates["source_type"] = "ThesisChange"
    elif mismatch == "missing_source":
        updates["source_id"] = uuid4()
    elif mismatch == "asset":
        updates["asset_id"] = uuid4()
    else:
        updates["investor_id"] = chain[0][0].investor_id
    old = _legacy(db_session_factory, chain, kind, **updates)
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory).dry_run().candidates == ()
    )
    assert _read(db_session_factory, kind) == ()
    with db_session_factory() as session:
        assert old in SignalRepository(session).list()


@pytest.mark.parametrize("late_time", (END - timedelta(hours=1), END + timedelta(days=1)))
def test_new_unreferenced_facts_do_not_assert_snapshot_completeness_or_leak_after_window(
    db_session_factory, production_policies, late_time
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)
    with db_session_factory() as session:
        source = chain[0][0]
        _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            late_time,
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    before = _snapshot(db_session_factory)
    assert (
        len(
            SignalGenerator.from_production(db_session_factory)
            .dry_run(signal_types=CROSS)
            .candidates
        )
        == 2
    )
    assert (
        len(IntelligenceEventAggregator.from_production(db_session_factory).dry_run().candidates)
        == 2
    )
    assert _snapshot(db_session_factory) == before


def test_mixed_aggregation_and_repeated_generation_are_idempotent(
    db_session_factory, production_policies
):
    good = _chain(db_session_factory, production_policies)
    bad = _chain(db_session_factory, production_policies)
    valid = [_legacy(db_session_factory, good, kind) for kind in CROSS]
    for kind in CROSS:
        _legacy(db_session_factory, bad, kind)
    with db_session_factory() as session:
        session.get(CrossInvestorAssetSnapshot, bad[1].id).opinion_analysis_version = "inactive"
        session.commit()
    generator = SignalGenerator.from_production(db_session_factory)
    assert generator.dry_run(signal_types=CROSS).created_count == 0
    assert generator.generate(signal_types=CROSS).reused_count == 2
    assert generator.generate(signal_types=CROSS).created_count == 0
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    first = aggregator.aggregate()
    second = aggregator.aggregate()
    assert first.created_evidence_count == 2
    assert second.created_evidence_count == 0 and second.reused_evidence_count == 2
    assert {value.asset_id for value in first.candidates} == {good[1].asset_id}
    assert all(value.asset_id == good[1].asset_id for value in first.events)
    from database.models import IntelligenceEventEvidence

    with db_session_factory() as session:
        assert {link.signal_id for link in session.scalars(select(IntelligenceEventEvidence))} == {
            item.id for item in valid
        }


def test_reads_group_by_window_scope_not_per_signal(
    db_engine, db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)
    statements = []

    def track(_connection, _cursor, statement, _parameters, _context, _executemany):
        statements.append(statement)

    def count(persisted=False):
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            if persisted:
                with db_session_factory() as session:
                    SignalRepository(session).list_cross_investor_signals_with_valid_references()
            else:
                SignalGenerator.from_production(db_session_factory).dry_run(signal_types=CROSS)
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(value.lstrip().upper().startswith("SELECT") for value in statements)
        return len(statements)

    before = _snapshot(db_session_factory)
    first_count = count()
    first_persisted_count = count(persisted=True)
    assert _snapshot(db_session_factory) == before
    for _ in range(5):
        snapshot = CrossInvestorAssetSnapshotService.from_production(
            lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(db_session_factory)
        ).calculate(chain[1].asset_id, START - timedelta(hours=_ + 1), END)
        alignment = CrossInvestorAssetAlignmentService(
            lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(db_session_factory)
        ).calculate(snapshot.id)
        consensus = CrossInvestorConsensusEvidenceService(
            lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(db_session_factory)
        ).calculate(snapshot.id, alignment.id)
        version = (chain[0], snapshot, alignment, consensus)
        for kind in CROSS:
            _legacy(db_session_factory, version, kind)
    # Six window versions share one asset/window_end scope; only repository
    # identity lookups for additional candidate sources may grow here.
    assert count() == first_count + 10
    assert first_count == 11
    assert count(persisted=True) == first_persisted_count == 10


@pytest.mark.parametrize("kind", CROSS)
def test_existing_snapshot_reference_mismatch_is_not_a_missing_row_fallback(
    db_session_factory, production_policies, kind
):
    chain = _chain(db_session_factory, production_policies)
    _legacy(db_session_factory, chain, kind)
    other = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(db_session_factory)
    ).calculate(chain[1].asset_id, START - timedelta(hours=1), END)
    with db_session_factory() as session:
        if kind is SignalType.CROSS_INVESTOR_ALIGNMENT:
            session.get(CrossInvestorAssetAlignment, chain[2].id).source_snapshot_id = other.id
        else:
            session.get(CrossInvestorConsensusEvidence, chain[3].id).source_snapshot_id = other.id
        session.commit()
    assert _read(db_session_factory, kind) == ()
    assert (
        SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,)).candidates
        == ()
    )


def test_validation_is_read_only_and_never_calls_artifact_calculate(
    db_session_factory, production_policies, monkeypatch
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)

    def forbidden(*args, **kwargs):
        raise AssertionError("calculate is fixture setup only, never read validation")

    for service in (
        CrossInvestorAssetSnapshotService,
        CrossInvestorAssetAlignmentService,
        CrossInvestorConsensusEvidenceService,
    ):
        monkeypatch.setattr(service, "calculate", forbidden)
    before = _snapshot(db_session_factory)
    assert (
        len(
            SignalGenerator.from_production(db_session_factory)
            .dry_run(signal_types=CROSS)
            .candidates
        )
        == 2
    )
    assert (
        len(IntelligenceEventAggregator.from_production(db_session_factory).dry_run().candidates)
        == 2
    )
    assert _snapshot(db_session_factory) == before


def test_referenced_missing_portfolio_fact_is_not_assumed_available(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)
    with db_session_factory() as session:
        row = session.get(CrossInvestorAssetSnapshot, chain[1].id)
        values = [dict(item) for item in row.contributions]
        values[0]["portfolio_action_ids"] = [str(uuid4())]
        values[0]["portfolio_action_types"] = ["POSITION_INCREASED"]
        row.contributions = values
        session.commit()
    before = _snapshot(db_session_factory)
    assert (
        SignalGenerator.from_production(db_session_factory).dry_run(signal_types=CROSS).candidates
        == ()
    )
    assert _snapshot(db_session_factory) == before
