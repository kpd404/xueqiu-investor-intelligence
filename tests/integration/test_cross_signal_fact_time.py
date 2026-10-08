"""Direction Signal time follows voting RawEvent facts, not artifact computation."""

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from contracts import (
    AttentionEvidence,
    AttentionEvidenceType,
    AttentionOccurrenceCreate,
    EventAnalysisStatus,
    IntelligenceEventCreate,
    IntelligenceEventEvidenceCreate,
    IntelligenceEventType,
    ThesisChangeCreate,
    ThesisChangeType,
)
from contracts.cross_investor import build_cross_investor_input_identity
from database.models import (
    Asset,
    CrossInvestorAssetAlignment,
    CrossInvestorAssetSnapshot,
    CrossInvestorConsensusEvidence,
    Investor,
)
from database.repositories.attention_occurrences import AttentionOccurrenceRepository
from database.repositories.cross_investor_asset_snapshots import (
    CrossInvestorAssetSnapshotRepository,
)
from database.repositories.intelligence_event_evidence import IntelligenceEventEvidenceRepository
from database.repositories.intelligence_events import IntelligenceEventRepository
from database.repositories.thesis_changes import ThesisChangeRepository
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
from tests.integration.test_cross_signal_source_chains import (
    CROSS,
    END,
    START,
    _chain,
    _legacy,
    _read,
)
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_effective_thesis_signals import _shared_asset_change
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion

production_policies = signal_fixtures.production_policies
CALC = FACT_TIME + timedelta(days=90)


def _computed_late(factory, policies):
    chain = _chain(factory, policies)
    with factory() as session:
        for model, value in (
            (CrossInvestorAssetSnapshot, chain[1]),
            (CrossInvestorAssetAlignment, chain[2]),
            (CrossInvestorConsensusEvidence, chain[3]),
        ):
            session.get(model, value.id).calculated_at = CALC
        session.commit()
    return chain[0], *(value.model_copy(update={"calculated_at": CALC}) for value in chain[1:])


@pytest.mark.parametrize("kind", CROSS)
def test_candidates_and_legacy_read_use_voting_raw_published_time(
    db_session_factory, production_policies, kind
):
    chain = _computed_late(db_session_factory, production_policies)
    old = _legacy(db_session_factory, chain, kind)
    before = _snapshot(db_session_factory)
    generator = SignalGenerator.from_production(db_session_factory)
    plan = generator.dry_run(signal_types=(kind,))
    assert plan.candidates[0].observed_at == FACT_TIME
    assert plan.candidates[0].created_at != FACT_TIME
    assert plan.candidates[0].source_id == old.source_id
    effective = _read(db_session_factory, kind)
    assert effective[0].observed_at == FACT_TIME
    assert effective[0].id == old.id and effective[0].created_at == old.created_at
    with db_session_factory() as session:
        assert SignalRepository(session).get(old.id).observed_at == CALC
        assert SignalRepository(session).list()[0].observed_at == CALC
    assert _snapshot(db_session_factory) == before
    assert generator.generate(signal_types=(kind,)).reused_count == 1
    assert generator.generate(signal_types=(kind,)).created_count == 0
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("kind", CROSS)
def test_only_calculation_time_changes_do_not_refresh_observation(
    db_session_factory, production_policies, kind
):
    chain = _computed_late(db_session_factory, production_policies)
    _legacy(db_session_factory, chain, kind)
    first = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,))
    with db_session_factory() as session:
        model = CrossInvestorAssetAlignment if kind is CROSS[0] else CrossInvestorConsensusEvidence
        session.get(model, chain[2 if kind is CROSS[0] else 3].id).calculated_at += timedelta(
            days=3
        )
        session.commit()
    second = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,))
    assert first.candidates[0].observed_at == second.candidates[0].observed_at == FACT_TIME
    assert _read(db_session_factory, kind)[0].observed_at == FACT_TIME


@pytest.mark.parametrize("kind", CROSS)
def test_future_unreferenced_opinions_and_labels_cannot_override_real_time(
    db_session_factory, production_policies, kind
):
    chain = _computed_late(db_session_factory, production_policies)
    _legacy(db_session_factory, chain, kind)
    with db_session_factory() as session:
        source = chain[0][0]
        _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            END + timedelta(days=1),
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    assert _read(db_session_factory, kind)[0].observed_at == FACT_TIME
    with db_session_factory() as session:
        snapshot = session.get(CrossInvestorAssetSnapshot, chain[1].id)
        values = [dict(value) for value in snapshot.contributions]
        values[0]["latest_window_opinion_time"] = CALC.isoformat()
        snapshot.contributions = values
        session.commit()
    assert _read(db_session_factory, kind) == ()
    assert (
        SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,)).candidates
        == ()
    )


@pytest.mark.parametrize("kind", CROSS)
def test_newer_non_voting_attention_does_not_refresh_direction_time(
    db_session_factory, production_policies, kind
):
    chain = _computed_late(db_session_factory, production_policies)
    # This fourth investor contributes a newer mention but no effective Opinion vote.
    with db_session_factory() as session:
        investor = Investor(name="Attention only", platform="manual", platform_user_id=str(uuid4()))
        session.add(investor)
        session.flush()
        opinion = _add_opinion(
            session,
            investor,
            session.get(Asset, chain[1].asset_id),
            production_policies[0].active_spec,
            END - timedelta(hours=1),
            EventAnalysisStatus.SUCCESS,
        )
        # Explicit mention evidence is source-fact support, not an Opinion vote.
        AttentionOccurrenceRepository(session).replace_for_event(
            opinion.event_id,
            "attention-occurrence-v1",
            (
                AttentionOccurrenceCreate(
                    investor_id=investor.id,
                    asset_id=chain[1].asset_id,
                    event_id=opinion.event_id,
                    published_time=END - timedelta(hours=1),
                    evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
                    evidence=(
                        AttentionEvidence(
                            evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                            matched_by="fixture",
                        ),
                    ),
                    attention_policy_version="attention-occurrence-v1",
                    calculated_at=CALC,
                ),
            ),
        )
        # Its interpretation is inactive, so it cannot cast a direction vote.
        from database.models import EventAnalysis

        session.get(EventAnalysis, opinion.analysis_id).analysis_version = "inactive"
        session.commit()
    snapshot = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(db_session_factory)
    ).calculate(chain[1].asset_id, START, END)
    alignment = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(db_session_factory)
    ).calculate(snapshot.id)
    CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(db_session_factory)
    ).calculate(snapshot.id, alignment.id)
    candidate = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,))
    assert {value.observed_at for value in candidate.candidates} == {FACT_TIME}


@pytest.mark.parametrize("kind", CROSS)
def test_newer_referenced_thesis_does_not_refresh_older_direction_votes(
    db_session_factory, production_policies, kind
):
    chain = _computed_late(db_session_factory, production_policies)
    original = chain[0][0]
    with db_session_factory() as session:
        current = _add_opinion(
            session,
            session.get(Investor, original.investor_id),
            session.get(Asset, original.asset_id),
            production_policies[0].active_spec,
            END - timedelta(hours=1),
            EventAnalysisStatus.SUCCESS,
        )
        newer = ThesisChangeRepository(session).add_if_absent(
            ThesisChangeCreate(
                investor_id=original.investor_id,
                asset_id=original.asset_id,
                previous_opinion_id=original.current_opinion_id,
                previous_event_id=original.current_event_id,
                current_opinion_id=current.id,
                current_event_id=current.event_id,
                effective_time=END - timedelta(hours=1),
                change_type=ThesisChangeType.THESIS_CHANGED,
                confidence=0.9,
                summary="Newer Thesis, not a referenced direction vote",
                evidence=("fixture",),
                opinion_analysis_version=original.opinion_analysis_version,
                comparison_version=original.comparison_version,
                calculated_at=CALC,
                input_identity=str(uuid4()),
            )
        )
        contributions = tuple(
            contribution.model_copy(
                update={
                    "thesis_change_ids": (*contribution.thesis_change_ids, newer.id),
                    "thesis_change_types": (*contribution.thesis_change_types, newer.change_type),
                }
            )
            if contribution.investor_id == original.investor_id
            else contribution
            for contribution in chain[1].contributions
        )
        snapshot = chain[1].model_copy(
            update={
                "contributions": contributions,
                "thesis_change_count": chain[1].thesis_change_count + 1,
            }
        )
        snapshot = snapshot.model_copy(
            update={
                "input_identity": build_cross_investor_input_identity(
                    asset_id=snapshot.asset_id,
                    as_of=snapshot.as_of,
                    window_start=snapshot.window_start,
                    window_end=snapshot.window_end,
                    opinion_analysis_version=snapshot.opinion_analysis_version,
                    attention_policy_version=snapshot.attention_policy_version,
                    thesis_comparison_version=snapshot.thesis_comparison_version,
                    consistency_policy_version=snapshot.consistency_policy_version,
                    cross_investor_policy_version=snapshot.cross_investor_policy_version,
                    attention_occurrence_ids=tuple(
                        identity for c in contributions for identity in c.attention_occurrence_ids
                    ),
                    opinion_ids=tuple(
                        identity for c in contributions for identity in c.window_opinion_ids
                    ),
                    thesis_change_ids=tuple(
                        identity for c in contributions for identity in c.thesis_change_ids
                    ),
                    first_attention_dependencies=tuple(
                        (
                            c.investor_id,
                            c.first_attention_occurrence_id,
                            c.first_attention_published_time,
                        )
                        for c in contributions
                        if c.attention_occurrence_ids
                    ),
                )
            }
        )
        saved, _ = CrossInvestorAssetSnapshotRepository(session).add_if_absent(snapshot)
        session.commit()
    alignment = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(db_session_factory)
    ).calculate(saved.id)
    consensus = CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(db_session_factory)
    ).calculate(saved.id, alignment.id)
    result = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,))
    source_id = alignment.id if kind is CROSS[0] else consensus.id
    matching = [value for value in result.candidates if value.source_id == source_id]
    assert len(matching) == 1
    assert matching[0].observed_at == FACT_TIME < newer.effective_time


def test_late_old_voting_fact_uses_original_publication_not_new_recording_time(
    db_session_factory, production_policies
):
    chain = _computed_late(db_session_factory, production_policies)
    late = _shared_asset_change(
        db_session_factory,
        production_policies,
        chain[1].asset_id,
        ThesisChangeType.THESIS_CHANGED,
        FACT_TIME + timedelta(hours=2),
    )
    with db_session_factory() as session:
        from database.models import Opinion

        opinion = session.get(Opinion, late.current_opinion_id)
        AttentionOccurrenceRepository(session).replace_for_event(
            late.current_event_id,
            "attention-occurrence-v1",
            (
                AttentionOccurrenceCreate(
                    investor_id=late.investor_id,
                    asset_id=late.asset_id,
                    event_id=late.current_event_id,
                    published_time=late.effective_time,
                    evidence_types=(AttentionEvidenceType.OPINION,),
                    evidence=(
                        AttentionEvidence(
                            evidence_type=AttentionEvidenceType.OPINION, matched_by="fixture"
                        ),
                    ),
                    opinion_id=opinion.id,
                    analysis_id=opinion.analysis_id,
                    attention_policy_version="attention-occurrence-v1",
                    calculated_at=CALC,
                ),
            ),
        )
        session.commit()
    snapshot = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(db_session_factory)
    ).calculate(chain[1].asset_id, START, END)
    alignment = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(db_session_factory)
    ).calculate(snapshot.id)
    CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(db_session_factory)
    ).calculate(snapshot.id, alignment.id)
    for kind in CROSS:
        result = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=(kind,))
        assert max(value.observed_at for value in result.candidates) == late.effective_time
        assert all(value.observed_at < CALC for value in result.candidates)


@pytest.mark.parametrize("kind", CROSS)
def test_new_aggregate_candidates_are_correct_but_old_event_time_is_retained(
    db_session_factory, production_policies, kind
):
    chain = _computed_late(db_session_factory, production_policies)
    signal = _legacy(db_session_factory, chain, kind)
    event_type = (
        IntelligenceEventType.CROSS_INVESTOR_DISCOVERY
        if kind is CROSS[0]
        else IntelligenceEventType.CONSENSUS_STATE_CHANGE
    )
    with db_session_factory() as session:
        old, _ = IntelligenceEventRepository(session).add_if_absent(
            IntelligenceEventCreate(
                asset_id=signal.asset_id,
                event_type=event_type,
                first_observed_at=CALC,
                last_observed_at=CALC,
            )
        )
        IntelligenceEventEvidenceRepository(session).add_if_absent(
            IntelligenceEventEvidenceCreate(event_id=old.id, signal_id=signal.id)
        )
        session.commit()
    before = _snapshot(db_session_factory)
    aggregate = IntelligenceEventAggregator.from_production(db_session_factory)
    plan = aggregate.dry_run()
    assert plan.candidates[0].first_observed_at == plan.candidates[0].last_observed_at == FACT_TIME
    assert _snapshot(db_session_factory) == before
    result = aggregate.aggregate()
    assert result.events[0].id == old.id
    assert result.events[0].first_observed_at == FACT_TIME
    assert result.events[0].last_observed_at == CALC
    assert aggregate.aggregate().created_evidence_count == 0
    with db_session_factory() as session:
        assert SignalRepository(session).get(signal.id).observed_at == CALC


def test_new_signal_rows_have_fact_observation_and_generation_creation_time(
    db_session_factory, production_policies
):
    _computed_late(db_session_factory, production_policies)
    generator = SignalGenerator.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    assert generator.dry_run(signal_types=CROSS).created_count == 2
    assert _snapshot(db_session_factory) == before
    started = datetime.now(UTC)
    result = generator.generate(signal_types=CROSS)
    finished = datetime.now(UTC)
    assert result.created_count == 2
    assert all(value.observed_at == FACT_TIME for value in result.signals)
    assert all(started <= value.created_at <= finished for value in result.signals)
    repeated = generator.generate(signal_types=CROSS)
    assert repeated.created_count == 0 and repeated.reused_count == 2
    assert {value.id for value in repeated.signals} == {value.id for value in result.signals}


def test_mixed_window_signal_inputs_produce_fact_based_aggregate_ranges(
    db_session_factory, production_policies
):
    chain = _computed_late(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)
    source = chain[0][0]
    late_time = FACT_TIME + timedelta(hours=2)
    with db_session_factory() as session:
        _add_opinion(
            session,
            session.get(Investor, source.investor_id),
            session.get(Asset, source.asset_id),
            production_policies[0].active_spec,
            late_time,
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    snapshot = CrossInvestorAssetSnapshotService.from_production(
        lambda: SqlAlchemyCrossInvestorAssetSnapshotUnitOfWork(db_session_factory)
    ).calculate(source.asset_id, START, END)
    alignment = CrossInvestorAssetAlignmentService(
        lambda: SqlAlchemyCrossInvestorAssetAlignmentUnitOfWork(db_session_factory)
    ).calculate(snapshot.id)
    consensus = CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(db_session_factory)
    ).calculate(snapshot.id, alignment.id)
    for kind in CROSS:
        _legacy(db_session_factory, (chain[0], snapshot, alignment, consensus), kind)
    before = _snapshot(db_session_factory)
    aggregate = IntelligenceEventAggregator.from_production(db_session_factory)
    plan = aggregate.dry_run()
    assert len(plan.candidates) == 2
    assert all(value.metadata["signal_count"] == 2 for value in plan.candidates)
    assert all(
        value.first_observed_at == FACT_TIME and value.last_observed_at == late_time
        for value in plan.candidates
    )
    assert _snapshot(db_session_factory) == before
    result = aggregate.aggregate()
    assert all(
        value.first_observed_at == FACT_TIME and value.last_observed_at == late_time
        for value in result.events
    )
    assert aggregate.aggregate().created_evidence_count == 0
