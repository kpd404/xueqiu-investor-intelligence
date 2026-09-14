from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from collectors.manual import ManualImportAdapter
from collectors.xueqiu import XueqiuAdapter, XueqiuFeedAdapter
from collectors.xueqiu.investor_history import XueqiuInvestorHistoryAdapter
from contracts import (
    CollectionCoverageStatus,
    CollectionMode,
    CollectionRunCreate,
    CollectionRunStatus,
    CollectionTransport,
)
from contracts.collection_provenance import CollectionObservationCreate


def test_contracts_preserve_generic_modes_and_unknown_coverage() -> None:
    started = datetime(2026, 9, 1, tzinfo=UTC)
    run = CollectionRunCreate(
        source="xueqiu",
        adapter_name="xueqiu_profile_history_cdp",
        collection_mode=CollectionMode.ENTITY_HISTORY,
        transport=CollectionTransport.BROWSER_CDP,
        started_at=started,
        ended_at=started + timedelta(minutes=1),
        run_status=CollectionRunStatus.COMPLETED,
        stop_reason="TARGET_REACHED",
        coverage_status=CollectionCoverageStatus.UNKNOWN,
    )
    assert run.collection_mode is CollectionMode.ENTITY_HISTORY
    assert run.transport is CollectionTransport.BROWSER_CDP
    assert run.coverage_status is CollectionCoverageStatus.UNKNOWN
    assert run.stop_reason == "TARGET_REACHED"


def test_contracts_reject_invalid_lifecycle_window() -> None:
    started = datetime(2026, 9, 1, tzinfo=UTC)
    with pytest.raises(ValueError, match="ended_at"):
        CollectionRunCreate(
            source="manual",
            adapter_name="manual_import",
            started_at=started,
            ended_at=started - timedelta(seconds=1),
        )


def test_observation_command_is_idempotency_keyed_by_run_and_event() -> None:
    observation = CollectionObservationCreate(
        collection_run_id=uuid4(),
        raw_event_id=uuid4(),
        ingest_disposition="INSERTED",
        observation_sequence=0,
    )
    assert observation.observation_sequence == 0


def test_adapters_expose_source_independent_collection_metadata() -> None:
    assert ManualImportAdapter.collection_mode is CollectionMode.MANUAL_IMPORT
    assert ManualImportAdapter.transport is CollectionTransport.FILE
    assert XueqiuFeedAdapter.collection_mode is CollectionMode.FEED
    assert XueqiuFeedAdapter.transport is CollectionTransport.BROWSER_SESSION
    assert XueqiuAdapter.collection_mode is CollectionMode.ENTITY_HISTORY
    assert XueqiuInvestorHistoryAdapter.collection_mode is CollectionMode.ENTITY_HISTORY
    assert XueqiuInvestorHistoryAdapter.transport is CollectionTransport.BROWSER_CDP
