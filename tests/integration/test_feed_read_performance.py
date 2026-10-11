"""Read performance guards using real effective sources and historical windows."""

from datetime import timedelta
from time import perf_counter

import pytest
from sqlalchemy import event

from signal_engine.cross_investor_sources import CrossInvestorReferencedEvidenceReader
from tests.integration.test_cross_signal_source_chains import (
    CROSS,
    _chain,
)
from tests.integration.test_cross_signal_source_chains import (
    production_policies as production_policies,
)
from tests.integration.test_cross_snapshot_input_completeness import _refresh
from tests.integration.test_effective_thesis_feed_query import _snapshot


@pytest.mark.parametrize("windows", [1, 12, 100])
def test_linked_scope_matches_full_validation_and_does_not_write(
    db_session_factory, production_policies, windows, record_property
):
    chain = _chain(db_session_factory, production_policies)
    asset = chain[1].asset_id
    for offset in range(1, windows):
        _refresh(db_session_factory, chain, end=chain[1].window_end + timedelta(days=offset))
    before = _snapshot(db_session_factory)
    with db_session_factory() as session:
        reader = CrossInvestorReferencedEvidenceReader(session)
        start = perf_counter()
        full = reader.list_with_votes(asset_ids={asset})
        elapsed_full = perf_counter() - start
        statements = []

        def observe(conn, cursor, statement, parameters, context, many):
            statements.append(statement)

        event.listen(session.bind, "before_cursor_execute", observe)
        try:
            start = perf_counter()
            limited = reader.list_with_votes(
                asset_ids={asset}, source_keys={(CROSS[0], chain[2].id), (CROSS[1], chain[3].id)}
            )
            elapsed_limited = perf_counter() - start
        finally:
            event.remove(session.bind, "before_cursor_execute", observe)
        assert limited[0] == tuple(v for v in full[0] if v.id == chain[2].id)
        assert limited[1] == tuple(v for v in full[1] if v.id == chain[3].id)
        for field in range(2, 5):
            assert limited[field] == {
                key: value
                for key, value in full[field].items()
                if key in {(CROSS[0], chain[2].id), (CROSS[1], chain[3].id)}
            }
        # Unlinked windows are never prepared. This bound is invariant to their count.
        assert len(statements) < 20
        record_property("windows", windows)
        record_property("full_seconds", elapsed_full)
        record_property("linked_seconds", elapsed_limited)
        record_property("linked_queries", len(statements))
    assert _snapshot(db_session_factory) == before


def test_memo_is_request_local_not_policy_or_source_cache(db_session_factory, production_policies):
    from contracts import EventAnalysisStatus
    from database.models import EventAnalysis, Opinion

    chain = _chain(db_session_factory, production_policies)
    with db_session_factory() as session:
        reader = CrossInvestorReferencedEvidenceReader(session)
        assert reader.list_with_votes(asset_ids={chain[1].asset_id})[0]
        opinion = session.get(Opinion, chain[0][0].current_opinion_id)
        session.get(EventAnalysis, opinion.analysis_id).status = EventAnalysisStatus.FAILED
        session.flush()
        assert not reader.list_with_votes(asset_ids={chain[1].asset_id})[0]
        session.rollback()
