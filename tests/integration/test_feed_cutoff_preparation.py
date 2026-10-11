"""Shared portfolio cutoff selection: real adjacency, no cached max-cutoff result."""

from datetime import timedelta

import pytest
from sqlalchemy import event

from contracts import OpinionDirection, PortfolioSnapshotBatchDTO
from database.repositories.portfolio_actions import PortfolioActionRepository
from database.repositories.portfolio_snapshots import PortfolioSnapshotBatchRepository
from tests.integration.test_opinion_action_consistency import (
    CURRENT_TIME,
    PREVIOUS_TIME,
    _seed_case,
)


def test_batch_cutoffs_match_real_selector_and_late_adjacency(db_session_factory):
    investor, asset, opinion, action = _seed_case(
        db_session_factory,
        direction=OpinionDirection.BULLISH,
        previous_weight=10,
        current_weight=20,
    )
    with db_session_factory() as session:
        portfolio = PortfolioActionRepository(session).get(action).portfolio_id
    cutoffs = [PREVIOUS_TIME, CURRENT_TIME, CURRENT_TIME + timedelta(days=1)]
    with db_session_factory() as session:
        repo = PortfolioActionRepository(session)
        prepared = repo.prepare_cutoffs({asset: cutoffs})
        for cutoff in cutoffs:
            assert prepared.list_effective_by_asset(
                asset, as_of=cutoff
            ) == repo.list_effective_by_asset(asset, as_of=cutoff)
        assert not prepared.list_effective_by_asset(asset, as_of=PREVIOUS_TIME)
        assert prepared.list_effective_by_asset(asset, as_of=CURRENT_TIME)
    with db_session_factory() as session:
        PortfolioSnapshotBatchRepository(session).get_or_create(
            PortfolioSnapshotBatchDTO(
                portfolio_id=portfolio,
                snapshot_time=PREVIOUS_TIME + timedelta(hours=1),
                source="manual",
                external_id="late-middle-batch",
            )
        )
        session.commit()
    with db_session_factory() as session:
        repo = PortfolioActionRepository(session)
        prepared = repo.prepare_cutoffs({asset: cutoffs})
        for cutoff in cutoffs:
            assert (
                prepared.list_effective_by_asset(asset, as_of=cutoff)
                == repo.list_effective_by_asset(asset, as_of=cutoff)
                == []
            )


def test_empty_many_assets_cutoffs_are_one_read(db_session_factory, db_engine):
    from uuid import uuid4

    statements = []

    def observe(conn, cursor, statement, *args):
        statements.append(statement)

    event.listen(db_engine, "before_cursor_execute", observe)
    try:
        with db_session_factory() as session:
            scopes = {
                uuid4(): [CURRENT_TIME + timedelta(days=i) for i in range(100)] for _ in range(20)
            }
            prepared = PortfolioActionRepository(session).prepare_cutoffs(scopes)
            for asset, cutoffs in scopes.items():
                for cutoff in cutoffs:
                    assert prepared.list_effective_by_asset(asset, as_of=cutoff) == []
        assert len(statements) == 1 and statements[0].lstrip().upper().startswith("SELECT")
    finally:
        event.remove(db_engine, "before_cursor_execute", observe)


@pytest.mark.parametrize("asset_count,cutoff_count", [(1, 1), (1, 20), (5, 20)])
def test_nonempty_scale_matches_each_cutoff(
    db_session_factory, db_engine, asset_count, cutoff_count, record_property
):
    from time import perf_counter

    assets = []
    for _ in range(asset_count):
        _, asset, *_ = _seed_case(
            db_session_factory,
            direction=OpinionDirection.BULLISH,
            previous_weight=10,
            current_weight=20,
        )
        assets.append(asset)
    cutoffs = [CURRENT_TIME + timedelta(hours=i) for i in range(cutoff_count)]
    scopes = {asset: cutoffs for asset in assets}
    statements = []

    def observe(conn, cursor, statement, *args):
        statements.append(statement)

    with db_session_factory() as session:
        repo = PortfolioActionRepository(session)
        event.listen(db_engine, "before_cursor_execute", observe)
        start = perf_counter()
        try:
            prepared = repo.prepare_cutoffs(scopes)
        finally:
            event.remove(db_engine, "before_cursor_execute", observe)
        preparation = perf_counter() - start
        assert len(statements) == 2
        start = perf_counter()
        for asset in assets:
            for cutoff in cutoffs:
                assert prepared.list_effective_by_asset(
                    asset, as_of=cutoff
                ) == repo.list_effective_by_asset(asset, as_of=cutoff)
        record_property("assets", asset_count)
        record_property("cutoffs", cutoff_count)
        record_property("batch_queries", len(statements))
        record_property("batch_seconds", preparation)
        record_property("comparison_seconds", perf_counter() - start)
        record_property("base_rows", asset_count * 3)
