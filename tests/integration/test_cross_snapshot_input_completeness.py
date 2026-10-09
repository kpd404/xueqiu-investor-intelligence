"""Current database window membership, using real selectors and persisted sources."""

from datetime import timedelta

import pytest

from contracts import (
    AnalysisSpec,
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceCreate,
    EventAnalysisStatus,
    SignalState,
)
from database.models import Asset, CrossInvestorAssetSnapshot, EventAnalysis, Investor, Opinion
from database.repositories.attention_occurrences import AttentionOccurrenceRepository
from database.repositories.opinions import OpinionRepository
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
from tests.integration.test_cross_signal_source_chains import (
    CROSS,
    END,
    START,
    _chain,
    _legacy,
    _read,
)
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion
from tests.integration.test_thesis_change_signals import production_policies as production_policies


def _attention(session, opinion, published_time):
    AttentionOccurrenceRepository(session).replace_for_event(
        opinion.event_id,
        "attention-occurrence-v1",
        (
            AttentionOccurrenceCreate(
                investor_id=opinion.investor_id,
                asset_id=opinion.asset_id,
                event_id=opinion.event_id,
                published_time=published_time,
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


def _refresh(factory, chain, start=START, end=END, as_of=None):
    snapshot = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(factory)
    ).calculate(chain[1].asset_id, start, end, as_of=as_of)
    alignment = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(factory)
    ).calculate(snapshot.id)
    consensus = CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(factory)
    ).calculate(snapshot.id, alignment.id)
    return chain[0], snapshot, alignment, consensus


@pytest.mark.parametrize("kind", CROSS)
def test_late_window_input_invalidates_still_valid_references(
    db_session_factory, production_policies, kind
):
    chain = _chain(db_session_factory, production_policies)
    old = _legacy(db_session_factory, chain, kind)
    source = chain[0][0]
    with db_session_factory() as session:
        _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            FACT_TIME + timedelta(hours=1),
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    # Existing references are still effective; the missing new input is the bug.
    from database.repositories.opinions import OpinionRepository

    with db_session_factory() as session:
        effective = OpinionRepository(session).list_effective_timeline_by_asset(
            source.asset_id, production_policies[0].as_effective_policy(), as_of=END
        )
        assert {i for c in chain[1].contributions for i in c.window_opinion_ids} < {
            value.opinion_id for value in effective
        }
    before = _snapshot(db_session_factory)
    assert _read(db_session_factory, kind) == ()
    assert (
        SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,)).candidates
        == ()
    )
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory).dry_run().candidates == ()
    )
    with db_session_factory() as session:
        history = SignalRepository(session).list()
        assert any(value.id == old.id and value.state is SignalState.ACTIVE for value in history)
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize(
    "change",
    ("attention", "attention_only", "same_count_replacement", "predecessor", "first_history"),
)
def test_input_changes_reject_old_chain_and_refreshed_identity_passes(
    db_session_factory, production_policies, change
):
    chain = _chain(db_session_factory, production_policies)
    old_signals = [_legacy(db_session_factory, chain, kind) for kind in CROSS]
    source = chain[0][0]
    with db_session_factory() as session:
        time = {
            "attention": FACT_TIME + timedelta(hours=1),
            "attention_only": FACT_TIME - timedelta(days=1),
            "same_count_replacement": FACT_TIME,
            "predecessor": FACT_TIME - timedelta(hours=12),
            "first_history": START - timedelta(hours=1),
        }[change]
        opinion = (
            session.get(Opinion, source.previous_opinion_id)
            if change == "attention_only"
            else _add_opinion(
                session,
                session.get(Investor, source.investor_id),
                session.get(Asset, source.asset_id),
                production_policies[0].active_spec,
                time,
                EventAnalysisStatus.SUCCESS,
            )
        )
        if change in ("attention", "attention_only", "first_history"):
            _attention(session, opinion, time)
        if change == "same_count_replacement":
            old = session.get(Opinion, source.current_opinion_id)
            session.get(EventAnalysis, old.analysis_id).status = EventAnalysisStatus.FAILED
            _attention(session, opinion, time)
        session.commit()
        if change == "same_count_replacement":
            current = OpinionRepository(session).list_effective_timeline_by_asset(
                source.asset_id, production_policies[0].as_effective_policy(), as_of=END
            )
            assert len(current) == chain[1].opinion_count
            assert source.current_opinion_id not in {i.opinion_id for i in current}
    before = _snapshot(db_session_factory)
    for kind in CROSS:
        assert _read(db_session_factory, kind) == ()
    assert (
        SignalGenerator.from_production(db_session_factory).dry_run(signal_types=CROSS).candidates
        == ()
    )
    assert _snapshot(db_session_factory) == before
    refreshed = _refresh(db_session_factory, chain)
    assert refreshed[1].id != chain[1].id
    if change == "attention_only":
        assert refreshed[1].opinion_count == chain[1].opinion_count
        assert refreshed[1].attention_occurrence_count == chain[1].attention_occurrence_count + 1
    if change == "first_history":
        assert refreshed[1].opinion_count == chain[1].opinion_count
        assert refreshed[1].attention_occurrence_count == chain[1].attention_occurrence_count
        assert refreshed[1].input_identity != chain[1].input_identity
    generator = SignalGenerator.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    assert len(generator.dry_run(signal_types=CROSS).candidates) == 2
    assert _snapshot(db_session_factory) == before
    assert generator.generate(signal_types=CROSS).created_count == 2
    assert generator.generate(signal_types=CROSS).reused_count == 2
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    assert aggregator.aggregate().created_evidence_count == 2
    assert aggregator.aggregate().created_evidence_count == 0
    for kind in CROSS:
        assert len(_read(db_session_factory, kind)) == 1
    with db_session_factory() as session:
        assert session.get(CrossInvestorAssetSnapshot, chain[1].id) is not None
        history = SignalRepository(session).list()
        assert all(
            any(i.id == old.id and i.state is SignalState.ACTIVE for i in history)
            for old in old_signals
        )


@pytest.mark.parametrize("change", ("other_asset", "after_window", "failed", "inactive"))
def test_outside_scope_and_ineffective_inputs_do_not_change_identity(
    db_session_factory, production_policies, change
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)
    source = chain[0][0]
    if change == "other_asset":
        other = _chain(db_session_factory, production_policies)
        source = other[0][0]
    with db_session_factory() as session:
        _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            AnalysisSpec.from_model_version("inactive-model")
            if change == "inactive"
            else production_policies[0].active_spec,
            END + timedelta(hours=1)
            if change == "after_window"
            else FACT_TIME + timedelta(hours=1),
            EventAnalysisStatus.FAILED if change == "failed" else EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    before = _snapshot(db_session_factory)
    for kind in CROSS:
        assert len(_read(db_session_factory, kind)) == 1
    assert _snapshot(db_session_factory) == before
    assert _refresh(db_session_factory, chain)[1].id == chain[1].id


def test_full_window_scopes_and_as_of_keep_existing_identity_rules(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    versions = [
        chain,
        _refresh(db_session_factory, chain, start=START - timedelta(hours=1)),
        _refresh(db_session_factory, chain, as_of=END + timedelta(days=2)),
    ]
    for version in versions:
        for kind in CROSS:
            _legacy(db_session_factory, version, kind)
    before = _snapshot(db_session_factory)
    for kind in CROSS:
        assert len(_read(db_session_factory, kind)) == 1
    # All three legal source windows still pass their own completeness checks;
    # only Signal consumption selects one equivalent representative per type.
    from signal_engine.cross_investor_sources import CrossInvestorReferencedEvidenceReader

    with db_session_factory() as session:
        alignments, consensus, _times = CrossInvestorReferencedEvidenceReader(
            session
        ).list_with_fact_times()
        assert len(alignments) == len(consensus) == 3
        assert len(SignalRepository(session).list()) == 6
    assert _snapshot(db_session_factory) == before
    for version in versions:
        assert (
            _refresh(
                db_session_factory, chain, start=version[1].window_start, as_of=version[1].as_of
            )[1].id
            == version[1].id
        )
