import asyncio
from pathlib import Path
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from operations.refresh import (
    CollectionStageResult,
    OperationalRefreshService,
    RefreshStage,
    RefreshStageError,
)


class NoOpRefresh(OperationalRefreshService):
    def __init__(self, observer):
        super().__init__(lambda: None, stage_observer=observer)

    def _database_counts(self):
        return {}

    def _begin_execution(self, trigger):
        return SimpleNamespace(session=None, lock=None, run_id=uuid4())

    def _finish_execution(self, execution, summary):
        return None

    async def _collect(self, **kwargs):
        return CollectionStageResult(run_id=None, stop_reason="SOURCE_NO_OP")

    async def _analyze(self, event_ids, **kwargs):
        return {"partial": False, "analysis_ids": (), "counts": {"processed": 0}}

    async def _materialize_resolution(self, event_ids, **kwargs):
        return {"partial": False, "counts": {"analyses": 0}}

    async def _derive_domain(self, event_ids, **kwargs):
        return {
            "partial": False,
            "affected_assets": set(),
            "affected_investors": set(),
            "counts": {"opinions": 0},
        }

    async def _derive_cross_investor(self, asset_ids):
        return {"partial": False, "affected_assets": set(), "counts": {"assets": 0}}

    def _generate_signals(self, asset_ids):
        return {"candidates": 0, "created": 0, "reused": 0}

    def _aggregate_events(self, asset_ids):
        return {"candidates": 0, "created": 0, "reused": 0, "event_ids": []}

    def _materialize_priorities(self, event_ids):
        return {"candidates": 0, "created": 0, "reused": 0, "priority_ids": []}

    def _materialize_feed(self, priority_ids):
        return {"candidates": 0, "created": 0, "reused": 0}

    def _apply_feed_lifecycle(self):
        return {"updated": 0, "reused": 0, "transitions": 0}

    def _verify_product(self, asset_ids, investor_ids):
        return {
            "partial": False,
            "verified_assets": [],
            "verified_investors": [],
            "failed": 0,
        }


def test_refresh_stage_ordering() -> None:
    stages = []
    summary = asyncio.run(
        NoOpRefresh(stages.append).run(
            skip_collection=False,
            analysis_concurrency=1,
            attention_concurrency=1,
        )
    )

    assert summary.result == "SUCCESS"
    assert stages == list(RefreshStage)


def test_empty_incremental_refresh_is_a_successful_no_op() -> None:
    summary = asyncio.run(NoOpRefresh(lambda stage: None).run())

    assert summary.result == "SUCCESS"
    assert summary.counts["collection"]["new_events"] == 0
    assert summary.counts["signals"]["candidates"] == 0
    assert summary.counts["events"]["candidates"] == 0
    assert summary.errors == []


def test_collection_summary_exposes_combined_feed_profile_metrics() -> None:
    run_id = uuid4()
    profile_run_id = uuid4()
    result = CollectionStageResult(
        run_id=run_id,
        run_ids=(run_id, profile_run_id),
        observed_event_ids=(uuid4(),),
        new_event_ids=(uuid4(),),
        received_items=3,
        following_feed={"original_count": 1, "repost_count": 1},
        direct_profiles={"investors_attempted": 8, "profile_only_new_raw_events": 1},
    )

    summary = OperationalRefreshService._collection_dict(result)

    assert summary["run_ids"] == [str(run_id), str(profile_run_id)]
    assert summary["following_feed"]["original_count"] == 1
    assert summary["direct_profiles"]["investors_attempted"] == 8
    assert summary["unique_new_raw_events"] == 1


def test_collection_investors_are_available_for_product_verification() -> None:
    investor_id = uuid4()

    class FakeSession:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return None

        def scalars(self, statement):
            return iter((investor_id,))

    service = OperationalRefreshService(FakeSession)

    assert service._investor_ids_for_events((uuid4(),)) == {investor_id}


def test_stage_failure_is_reported_without_claiming_success() -> None:
    stages = []

    class FailingRefresh(NoOpRefresh):
        async def _collect(self, **kwargs):
            raise RefreshStageError(
                RefreshStage.COLLECTION,
                "COLLECTION_AUTH_REQUIRED",
                "authentication is required",
            )

    summary = asyncio.run(FailingRefresh(stages.append).run())

    assert summary.result == "FAILED"
    assert stages == [RefreshStage.COLLECTION]
    assert summary.stages["COLLECTION"]["status"] == "FAILED"
    assert summary.errors[0]["code"] == "COLLECTION_AUTH_REQUIRED"


def test_individual_event_failure_does_not_hide_other_event_results() -> None:
    service = OperationalRefreshService(lambda: None)
    event_ids = (uuid4(), uuid4())

    def operation(event_id):
        if event_id == event_ids[0]:
            raise RuntimeError("one item failed")
        return event_id

    results = asyncio.run(service._bounded_event_calls(event_ids, operation, 2))

    assert isinstance(results[0], RuntimeError)
    assert results[1] == event_ids[1]


def test_skip_collection_requires_an_explicit_existing_event() -> None:
    with pytest.raises(RefreshStageError, match="requires at least one"):
        OperationalRefreshService._skip_collection(())


def test_refresh_does_not_embed_historical_cohort_counts() -> None:
    source = (Path(__file__).parents[1] / "operations" / "refresh.py").read_text(encoding="utf-8")

    for forbidden_count in ("1593", "1490", "103", "569"):
        assert forbidden_count not in source


def test_collection_stage_result_preserves_event_identity() -> None:
    raw_event_id = uuid4()
    result = CollectionStageResult(
        run_id=uuid4(),
        observed_event_ids=(raw_event_id,),
        new_event_ids=(raw_event_id,),
        new_events=1,
    )

    assert result.observed_event_ids == (raw_event_id,)
    assert isinstance(result.run_id, UUID)
