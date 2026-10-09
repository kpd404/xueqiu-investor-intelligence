"""Different legal windows are calculation versions, not new input evidence."""

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
    SignalState,
    ThesisChangeType,
)
from database.models import Asset, CrossInvestorAssetSnapshot, Investor, Signal
from intelligence.events.aggregator import IntelligenceEventAggregator
from operations.refresh import OperationalRefreshService
from signal_engine.repository import SignalRepository
from signal_engine.service import SignalGenerator
from tests.integration.test_cross_signal_source_chains import CROSS, END, START, _chain, _legacy
from tests.integration.test_cross_snapshot_input_completeness import _refresh
from tests.integration.test_effective_thesis_feed_query import _snapshot
from tests.integration.test_thesis_change_signals import FACT_TIME, _add_opinion
from tests.integration.test_thesis_change_signals import production_policies as production_policies


def _windows(factory, policies):
    original = _chain(factory, policies)
    other = _refresh(
        factory,
        original,
        start=START - timedelta(hours=1),
        end=END + timedelta(hours=1),
        as_of=END + timedelta(days=2),
    )
    assert other[1].id != original[1].id
    assert other[1].contributions == original[1].contributions
    return original, other


def test_same_batch_equivalent_windows_generate_once(db_session_factory, production_policies):
    first, second = _windows(db_session_factory, production_policies)
    generator = SignalGenerator.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    plan = generator.dry_run(signal_types=CROSS)
    assert _snapshot(db_session_factory) == before
    assert len(plan.candidates) == plan.created_count == 2
    actual = generator.generate(signal_types=CROSS)
    assert actual.created_count == 2
    assert {c.source_id for c in actual.candidates} == {c.source_id for c in plan.candidates}
    assert {c.source_id for c in plan.candidates} == {
        min(first[index].id, second[index].id, key=lambda identity: identity.int)
        for index in (2, 3)
    }
    assert {c.observed_at for c in actual.candidates} == {FACT_TIME}
    after = _snapshot(db_session_factory)
    assert {table: rows for table, rows in after.items() if table != "signals"} == {
        table: rows for table, rows in before.items() if table != "signals"
    }
    assert generator.generate(signal_types=CROSS).reused_count == 2
    aggregator = IntelligenceEventAggregator.from_production(db_session_factory)
    result = aggregator.aggregate()
    assert all(c.metadata["signal_count"] == 1 for c in result.candidates)
    assert aggregator.aggregate().created_evidence_count == 0


def test_old_duplicates_are_historical_but_aggregate_once(db_session_factory, production_policies):
    windows = _windows(db_session_factory, production_policies)
    old = [_legacy(db_session_factory, chain, kind) for chain in windows for kind in CROSS]
    before = _snapshot(db_session_factory)
    with db_session_factory() as session:
        effective = SignalRepository(session).list_cross_investor_signals_with_valid_references()
        assert len(effective) == 2
        assert len(SignalRepository(session).list()) == 4
        assert all(value.state is SignalState.ACTIVE for value in SignalRepository(session).list())
    assert _snapshot(db_session_factory) == before
    result = IntelligenceEventAggregator.from_production(db_session_factory).aggregate()
    assert result.created_evidence_count == 2
    assert all(c.metadata["signal_count"] == 1 for c in result.candidates)
    assert {s.id for s in effective} <= {s.id for s in old}
    before = _snapshot(db_session_factory)
    plan = SignalGenerator.from_production(db_session_factory).dry_run(signal_types=CROSS)
    assert plan.created_count == 0 and plan.reused_count == 2
    assert {s.id for s in plan.signals} == {s.id for s in effective}
    assert _snapshot(db_session_factory) == before
    assert (
        IntelligenceEventAggregator.from_production(db_session_factory)
        .aggregate()
        .created_evidence_count
        == 0
    )


@pytest.mark.parametrize("boundary", ("start", "end", "as_of", "calculation"))
def test_new_equivalent_version_prefers_existing_real_signal(
    db_session_factory, production_policies, boundary
):
    chain = _chain(db_session_factory, production_policies)
    generator = SignalGenerator.from_production(db_session_factory)
    first = generator.generate(signal_types=CROSS)
    if boundary == "calculation":
        from database.models import CrossInvestorAssetAlignment, CrossInvestorConsensusEvidence

        with db_session_factory() as session:
            session.get(CrossInvestorAssetSnapshot, chain[1].id).calculated_at = END + timedelta(
                days=5
            )
            session.get(CrossInvestorAssetAlignment, chain[2].id).calculated_at = END + timedelta(
                days=5
            )
            session.get(CrossInvestorConsensusEvidence, chain[3].id).calculated_at = (
                END + timedelta(days=5)
            )
            session.commit()
    else:
        _refresh(
            db_session_factory,
            chain,
            start=START - timedelta(hours=1) if boundary == "start" else START,
            end=END + timedelta(hours=1) if boundary == "end" else END,
            as_of=END + timedelta(days=1) if boundary == "as_of" else None,
        )
    before = _snapshot(db_session_factory)
    plan = generator.dry_run(signal_types=CROSS)
    assert plan.created_count == 0 and plan.reused_count == 2
    assert {c.source_id for c in plan.candidates} == {s.source_id for s in first.signals}
    again = generator.generate(signal_types=CROSS)
    assert again.created_count == 0 and again.reused_count == 2
    assert {s.id for s in again.signals} == {s.id for s in first.signals}
    assert {c.observed_at for c in again.candidates} == {FACT_TIME}
    assert _snapshot(db_session_factory) == before


@pytest.mark.parametrize("invalid", ("policy", "inactive_signal", "identity"))
def test_invalid_existing_representative_does_not_block_valid_alternative(
    db_session_factory, production_policies, invalid
):
    chain = _chain(db_session_factory, production_policies)
    generator = SignalGenerator.from_production(db_session_factory)
    first = generator.generate(signal_types=CROSS)
    other = _refresh(db_session_factory, chain, end=END + timedelta(hours=1))
    with db_session_factory() as session:
        if invalid == "policy":
            session.get(
                CrossInvestorAssetSnapshot, chain[1].id
            ).opinion_analysis_version = "inactive"
        else:
            for signal in first.signals:
                row = session.get(Signal, signal.id)
                if invalid == "inactive_signal":
                    row.state = SignalState.SUPERSEDED.value
                else:
                    row.investor_id = chain[0][0].investor_id
        session.commit()
    before = _snapshot(db_session_factory)
    plan = generator.dry_run(signal_types=CROSS)
    assert plan.created_count == 2
    assert _snapshot(db_session_factory) == before
    actual = generator.generate(signal_types=CROSS)
    assert actual.created_count == 2
    assert {c.source_id for c in actual.candidates} == {other[2].id, other[3].id}
    with db_session_factory() as session:
        valid = SignalRepository(session).list_cross_investor_signals_with_valid_references()
        assert {s.id for s in valid} == {s.id for s in actual.signals}
        assert len(SignalRepository(session).list()) == 4
    assert generator.generate(signal_types=CROSS).created_count == 0


def test_different_opinion_inputs_with_same_votes_counts_and_time_are_not_merged(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    shorter = _refresh(db_session_factory, chain, start=FACT_TIME - timedelta(hours=12))
    assert chain[1].opinion_investor_count == shorter[1].opinion_investor_count == 3
    assert chain[2].directional_alignment_state == shorter[2].directional_alignment_state
    assert chain[3].consensus_state == shorter[3].consensus_state
    # Different effective Opinion history IDs: 6 versus 3, despite identical votes.
    assert chain[1].opinion_count != shorter[1].opinion_count
    result = SignalGenerator.from_production(db_session_factory).generate(signal_types=CROSS)
    assert result.created_count == 4
    assert {c.observed_at for c in result.candidates} == {FACT_TIME}
    with db_session_factory() as session:
        assert (
            len(SignalRepository(session).list_cross_investor_signals_with_valid_references()) == 4
        )


def test_real_new_effective_input_is_separate_and_old_records_remain(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    generator = SignalGenerator.from_production(db_session_factory)
    first = generator.generate(signal_types=CROSS)
    from database.models import Opinion
    from tests.integration.test_cross_snapshot_input_completeness import _attention
    from tests.integration.test_effective_thesis_signals import _shared_asset_change

    late = _shared_asset_change(
        db_session_factory,
        production_policies,
        chain[1].asset_id,
        ThesisChangeType.THESIS_CHANGED,
        FACT_TIME + timedelta(hours=1),
    )
    with db_session_factory() as session:
        _attention(session, session.get(Opinion, late.current_opinion_id), late.effective_time)
        session.commit()
    refreshed = _refresh(db_session_factory, chain)
    result = generator.generate(signal_types=CROSS)
    assert result.created_count == 2
    assert {c.source_id for c in result.candidates} == {refreshed[2].id, refreshed[3].id}
    assert {c.observed_at for c in result.candidates} == {late.effective_time}
    with db_session_factory() as session:
        assert {s.id for s in first.signals} <= {s.id for s in SignalRepository(session).list()}
        assert (
            len(SignalRepository(session).list_cross_investor_signals_with_valid_references()) == 2
        )


def test_same_evidence_across_types_and_distinct_assets_stays_separate(
    db_session_factory, production_policies
):
    first = _chain(db_session_factory, production_policies)
    second = _chain(db_session_factory, production_policies)
    result = SignalGenerator.from_production(db_session_factory).generate(signal_types=CROSS)
    assert result.created_count == 4
    assert {c.asset_id for c in result.candidates} == {first[1].asset_id, second[1].asset_id}
    assert {c.signal_type for c in result.candidates} == set(CROSS)


def test_metadata_signatures_cannot_merge_different_sources(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    shorter = _refresh(db_session_factory, chain, start=FACT_TIME - timedelta(hours=12))
    for version in (chain, shorter):
        for kind in CROSS:
            _legacy(
                db_session_factory, version, kind, metadata={"equivalence": "same-forged-value"}
            )
    before = _snapshot(db_session_factory)
    with db_session_factory() as session:
        assert (
            len(SignalRepository(session).list_cross_investor_signals_with_valid_references()) == 4
        )
    assert _snapshot(db_session_factory) == before


def test_different_attention_investors_same_counts_votes_and_time_not_merged(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    from database.repositories.attention_occurrences import AttentionOccurrenceRepository

    with db_session_factory() as session:
        for time in (FACT_TIME - timedelta(hours=36), FACT_TIME + timedelta(hours=2)):
            investor = Investor(
                name="Attention-only fixture", platform="manual", platform_user_id=uuid4().hex
            )
            session.add(investor)
            session.flush()
            opinion = _add_opinion(
                session,
                investor,
                session.get(Asset, chain[1].asset_id),
                production_policies[0].active_spec,
                time,
                EventAnalysisStatus.FAILED,
            )
            AttentionOccurrenceRepository(session).replace_for_event(
                opinion.event_id,
                "attention-occurrence-v1",
                (
                    AttentionOccurrenceCreate(
                        investor_id=investor.id,
                        asset_id=chain[1].asset_id,
                        event_id=opinion.event_id,
                        published_time=time,
                        evidence_types=(AttentionEvidenceType.EXPLICIT_MENTION,),
                        evidence=(
                            AttentionEvidence(
                                evidence_type=AttentionEvidenceType.EXPLICIT_MENTION,
                                matched_by="fixture",
                            ),
                        ),
                        attention_policy_version="attention-occurrence-v1",
                        calculated_at=END,
                    ),
                ),
            )
        session.commit()
    first = _refresh(db_session_factory, chain, end=FACT_TIME + timedelta(hours=1))
    second = _refresh(
        db_session_factory,
        chain,
        start=FACT_TIME - timedelta(hours=24),
        end=FACT_TIME + timedelta(hours=3),
    )
    assert first[1].attention_investor_count == second[1].attention_investor_count == 4
    assert first[1].opinion_investor_count == second[1].opinion_investor_count == 3
    assert first[2].directional_alignment_state == second[2].directional_alignment_state
    assert first[3].consensus_state == second[3].consensus_state
    first_investors = {c.investor_id for c in first[1].contributions if c.attention_occurrence_ids}
    second_investors = {
        c.investor_id for c in second[1].contributions if c.attention_occurrence_ids
    }
    assert first_investors != second_investors
    generator = SignalGenerator.from_production(db_session_factory)
    result = generator.generate(signal_types=CROSS)
    assert {c.source_id for c in result.candidates} >= {
        first[2].id,
        first[3].id,
        second[2].id,
        second[3].id,
    }
    assert {c.observed_at for c in result.candidates} == {FACT_TIME}


def test_batch_queries_do_not_grow_per_legacy_signal(
    db_engine, db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    for kind in CROSS:
        _legacy(db_session_factory, chain, kind)
    statements = []

    def track(_connection, _cursor, statement, *_args):
        statements.append(statement)

    def count(generation=False):
        statements.clear()
        sqlalchemy_event.listen(db_engine, "before_cursor_execute", track)
        try:
            if generation:
                SignalGenerator.from_production(db_session_factory).dry_run(signal_types=CROSS)
            else:
                with db_session_factory() as session:
                    result = SignalRepository(
                        session
                    ).list_cross_investor_signals_with_valid_references()
                    assert len(result) == 2
        finally:
            sqlalchemy_event.remove(db_engine, "before_cursor_execute", track)
        assert all(s.lstrip().upper().startswith("SELECT") for s in statements)
        return len(statements)

    assert count() == 19
    assert count(generation=True) == 21
    for _ in range(20):
        _legacy(
            db_session_factory,
            chain,
            CROSS[0],
            source_id=uuid4(),
            metadata={"equivalence": "forged-signature"},
        )
    before = _snapshot(db_session_factory)
    assert count() == 19
    assert count(generation=True) == 21
    assert _snapshot(db_session_factory) == before


def test_existing_event_links_remain_even_when_consumption_is_deduplicated(
    db_session_factory, production_policies
):
    from contracts import (
        IntelligenceEventCreate,
        IntelligenceEventEvidenceCreate,
        IntelligenceEventType,
    )
    from database.models import IntelligenceEventEvidence
    from database.repositories.intelligence_event_evidence import (
        IntelligenceEventEvidenceRepository,
    )
    from database.repositories.intelligence_events import IntelligenceEventRepository

    windows = _windows(db_session_factory, production_policies)
    signals = [_legacy(db_session_factory, version, kind) for version in windows for kind in CROSS]
    with db_session_factory() as session:
        for kind, event_type in zip(
            CROSS,
            (
                IntelligenceEventType.CROSS_INVESTOR_DISCOVERY,
                IntelligenceEventType.CONSENSUS_STATE_CHANGE,
            ),
            strict=True,
        ):
            old, _ = IntelligenceEventRepository(session).add_if_absent(
                IntelligenceEventCreate(
                    asset_id=windows[0][1].asset_id,
                    event_type=event_type,
                    first_observed_at=END,
                    last_observed_at=END,
                    metadata={"signal_count": 2},
                )
            )
            for signal in signals:
                if signal.signal_type is kind:
                    IntelligenceEventEvidenceRepository(session).add_if_absent(
                        IntelligenceEventEvidenceCreate(
                            event_id=old.id,
                            signal_id=signal.id,
                        )
                    )
        session.commit()
        links = {row.id for row in session.scalars(select(IntelligenceEventEvidence))}
        assert len(links) == 4
    aggregate = IntelligenceEventAggregator.from_production(db_session_factory)
    before = _snapshot(db_session_factory)
    plan = aggregate.dry_run()
    assert all(c.metadata["signal_count"] == 1 for c in plan.candidates)
    assert _snapshot(db_session_factory) == before
    actual = aggregate.aggregate()
    assert actual.created_evidence_count == 0
    assert all(c.metadata["signal_count"] == 1 for c in actual.candidates)
    # Existing history is not rebuilt: four links and the polluted last time stay.
    assert {e.last_observed_at for e in actual.events} == {END}
    with db_session_factory() as session:
        assert {row.id for row in session.scalars(select(IntelligenceEventEvidence))} == links
        assert len(SignalRepository(session).list()) == 4


def test_sqlite_canonical_lock_is_cooperative_and_process_scoped(db_session_factory):
    from operations.locking import OperationalRefreshLock

    with db_session_factory() as first, db_session_factory() as second:
        holder, contender = OperationalRefreshLock(first), OperationalRefreshLock(second)
        assert holder.try_acquire()
        try:
            assert not contender.try_acquire()
        finally:
            holder.release()
        assert contender.try_acquire()
        contender.release()
    # The old-duplicate fixture above proves type/source uniqueness permits
    # equivalent different sources. This is not a concurrent PostgreSQL proof.


def test_real_refresh_global_bounds_change_without_new_asset_evidence(
    db_session_factory, production_policies
):
    chain = _chain(db_session_factory, production_policies)
    asset_id = chain[1].asset_id
    refresh = OperationalRefreshService(db_session_factory)
    # Invoke only deterministic real derivation/generation stages in isolated DB;
    # never run collect, analyze, production run, recovery or maintenance.
    first = refresh._derive_cross_investor({asset_id})
    assert first["counts"]["failed"] == 0
    initial_signals = refresh._generate_signals({asset_id})
    with db_session_factory() as session:
        target = list(
            session.scalars(
                select(CrossInvestorAssetSnapshot).where(
                    CrossInvestorAssetSnapshot.asset_id == asset_id
                )
            )
        )
        prior_ids = {row.id for row in target}
        prior_contributions = target[-1].contributions
    unrelated = _chain(db_session_factory, production_policies)[0][0]
    with db_session_factory() as session:
        _add_opinion(
            session,
            session.get(Investor, unrelated.investor_id),
            session.get(Asset, unrelated.asset_id),
            production_policies[0].active_spec,
            END + timedelta(days=3),
            EventAnalysisStatus.SUCCESS,
        )
        session.commit()
    changed = refresh._derive_cross_investor({asset_id})
    assert changed["counts"]["failed"] == 0
    assert changed["counts"]["window_end"] != first["counts"]["window_end"]
    with db_session_factory() as session:
        added = list(
            session.scalars(
                select(CrossInvestorAssetSnapshot).where(
                    CrossInvestorAssetSnapshot.asset_id == asset_id,
                    CrossInvestorAssetSnapshot.id.not_in(prior_ids),
                )
            )
        )
        assert len(added) == 1
        assert added[0].contributions == prior_contributions
    result = refresh._generate_signals({asset_id})
    assert result["created"] == 0
    assert result["reused"] == initial_signals["candidates"]
    with db_session_factory() as session:
        cross_signals = [
            s for s in SignalRepository(session).list_by_asset(asset_id) if s.signal_type in CROSS
        ]
        assert len(cross_signals) == 2
        assert {s.observed_at for s in cross_signals} == {FACT_TIME}
    events = IntelligenceEventAggregator.from_production(db_session_factory).aggregate(
        asset_ids={asset_id}
    )
    assert all(
        c.metadata["signal_count"] == 1
        for c in events.candidates
        if c.event_type.value
        in {
            "CROSS_INVESTOR_DISCOVERY",
            "CONSENSUS_STATE_CHANGE",
        }
    )
