import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from collection.provenance import CollectionProvenanceCoverageService
from collectors import ManualImportAdapter
from contracts import (
    CollectionCoverageStatus,
    CollectionIngestDisposition,
    CollectionMode,
    CollectionObservationCreate,
    CollectionRequest,
    CollectionRunCreate,
    CollectionRunStatus,
    CollectionTransport,
    EventType,
    FeedPostItem,
    FeedPostKind,
)
from contracts.collection_provenance import utc_now
from database.models import CollectionObservation, CollectionRun, Investor, RawEvent
from database.repositories import (
    CollectionObservationRepository,
    CollectionRunRepository,
    RawEventRepository,
)
from database.unit_of_work import SqlAlchemyCollectionProvenanceUnitOfWork
from ingestion import FeedIngestionService
from pipeline import DataPipeline


def _create_investor(session: Session) -> Investor:
    investor = Investor(
        name=f"Provenance Investor {uuid4()}",
        platform="manual",
        platform_user_id=f"provenance-{uuid4()}",
    )
    session.add(investor)
    session.commit()
    return investor


def _create_run(
    session: Session,
    *,
    started_at: datetime | None = None,
    mode: CollectionMode = CollectionMode.MANUAL_IMPORT,
    transport: CollectionTransport = CollectionTransport.FILE,
) -> CollectionRun:
    command = CollectionRunCreate(
        source="manual",
        adapter_name="manual_import",
        collection_mode=mode,
        transport=transport,
        started_at=started_at or utc_now(),
        coverage_status=CollectionCoverageStatus.UNKNOWN,
    )
    view = CollectionRunRepository(session).create_run(command)
    session.commit()
    return session.get(CollectionRun, view.id)  # type: ignore[return-value]


def _manual_request(investor: Investor) -> CollectionRequest:
    return CollectionRequest(
        investor_id=investor.id,
        platform_user_id=investor.platform_user_id,
    )


def _manual_adapter(source_event_id: str) -> ManualImportAdapter:
    return ManualImportAdapter(
        content=f"provenance event {source_event_id}",
        published_time=datetime(2026, 9, 1, 9, 0, tzinfo=UTC),
        url=f"https://example.test/provenance/{source_event_id}",
        event_type=EventType.POST,
        raw_data={"source_event_id": source_event_id},
    )


def test_inserted_and_reused_events_record_observations_across_runs(
    db_session: Session,
) -> None:
    investor = _create_investor(db_session)
    request = _manual_request(investor)
    event_adapter = _manual_adapter("same-event")
    first_run = _create_run(db_session)

    first = asyncio.run(
        DataPipeline(
            RawEventRepository(db_session),
            db_session,
            collection_observation_repository=CollectionObservationRepository(db_session),
            collection_run_id=first_run.id,
            observed_at_factory=lambda: datetime(2026, 9, 1, 10, 0, tzinfo=UTC),
        ).run(event_adapter, request)
    )
    retry_same_run = asyncio.run(
        DataPipeline(
            RawEventRepository(db_session),
            db_session,
            collection_observation_repository=CollectionObservationRepository(db_session),
            collection_run_id=first_run.id,
            observed_at_factory=lambda: datetime(2026, 9, 1, 10, 1, tzinfo=UTC),
        ).run(event_adapter, request)
    )

    second_run = _create_run(
        db_session,
        started_at=datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
    )
    second = asyncio.run(
        DataPipeline(
            RawEventRepository(db_session),
            db_session,
            collection_observation_repository=CollectionObservationRepository(db_session),
            collection_run_id=second_run.id,
            observed_at_factory=lambda: datetime(2026, 9, 2, 10, 0, tzinfo=UTC),
        ).run(event_adapter, request)
    )

    assert first.inserted == 1
    assert retry_same_run.duplicates == 1
    assert second.duplicates == 1
    assert (
        first.events[0].event_id == retry_same_run.events[0].event_id == second.events[0].event_id
    )
    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 1

    observations = list(
        db_session.scalars(
            select(CollectionObservation).order_by(CollectionObservation.observed_at)
        )
    )
    assert len(observations) == 2
    assert observations[0].collection_run_id == first_run.id
    assert observations[0].ingest_disposition == CollectionIngestDisposition.INSERTED.value
    assert observations[1].collection_run_id == second_run.id
    assert observations[1].ingest_disposition == CollectionIngestDisposition.REUSED_EXISTING.value


def test_run_lifecycle_keeps_target_reached_coverage_unknown(db_session: Session) -> None:
    started = datetime(2026, 9, 3, 10, 0, tzinfo=UTC)
    run = _create_run(db_session, started_at=started, mode=CollectionMode.ENTITY_HISTORY)

    completed = CollectionRunRepository(db_session).finish_run(
        run.id,
        ended_at=started + timedelta(minutes=1),
        stop_reason="TARGET_REACHED",
    )
    db_session.commit()

    failed = _create_run(db_session, started_at=started + timedelta(hours=1))
    failed_view = CollectionRunRepository(db_session).fail_run(
        failed.id,
        ended_at=started + timedelta(hours=1, minutes=1),
        stop_reason="ERROR",
    )
    db_session.commit()

    aborted = _create_run(db_session, started_at=started + timedelta(hours=2))
    aborted_view = CollectionRunRepository(db_session).abort_run(
        aborted.id,
        ended_at=started + timedelta(hours=2, minutes=1),
        stop_reason="MANUAL_STOP",
    )
    db_session.commit()

    assert completed.run_status is CollectionRunStatus.COMPLETED
    assert completed.coverage_status is CollectionCoverageStatus.UNKNOWN
    assert completed.stop_reason == "TARGET_REACHED"
    assert failed_view.run_status is CollectionRunStatus.FAILED
    assert aborted_view.run_status is CollectionRunStatus.ABORTED


def test_following_feed_records_reused_event_provenance(db_session: Session) -> None:
    item = FeedPostItem(
        source_event_id="feed-event",
        author_id="feed-author",
        event_type=EventType.POST,
        post_kind=FeedPostKind.ORIGINAL,
        url="https://xueqiu.com/feed-author/feed-event",
        published_time=datetime(2026, 9, 3, 12, 0, tzinfo=UTC),
        content="feed item",
        raw_data={"screen_name": "Feed Investor"},
    )
    run_a = _create_run(
        db_session,
        mode=CollectionMode.FEED,
        transport=CollectionTransport.BROWSER_SESSION,
    )
    service_a = FeedIngestionService(
        db_session,
        collection_observation_repository=CollectionObservationRepository(db_session),
        collection_run_id=run_a.id,
    )
    first = asyncio.run(service_a.ingest([item]))
    retry = asyncio.run(service_a.ingest([item]))

    run_b = _create_run(
        db_session,
        started_at=datetime(2026, 9, 4, 12, 0, tzinfo=UTC),
        mode=CollectionMode.FEED,
        transport=CollectionTransport.BROWSER_SESSION,
    )
    second = asyncio.run(
        FeedIngestionService(
            db_session,
            collection_observation_repository=CollectionObservationRepository(db_session),
            collection_run_id=run_b.id,
        ).ingest([item])
    )

    assert first.inserted_event_count == 1
    assert retry.duplicate_event_count == 1
    assert second.duplicate_event_count == 1
    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 1
    assert db_session.scalar(select(func.count()).select_from(CollectionObservation)) == 2
    dispositions = list(
        db_session.scalars(
            select(CollectionObservation.ingest_disposition).order_by(
                CollectionObservation.collection_run_id
            )
        )
    )
    assert dispositions.count(CollectionIngestDisposition.INSERTED.value) == 1
    assert dispositions.count(CollectionIngestDisposition.REUSED_EXISTING.value) == 1


def test_coverage_audit_does_not_backfill_legacy_events(
    db_session: Session,
    db_session_factory: sessionmaker[Session],
) -> None:
    investor = _create_investor(db_session)
    event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.POST,
        source="legacy",
        url="https://example.test/legacy/1",
        published_time=datetime(2026, 9, 4, tzinfo=UTC),
        content="legacy event without provenance",
        raw_data={},
        hash=uuid4().hex + uuid4().hex,
    )
    db_session.add(event)
    db_session.commit()

    service = CollectionProvenanceCoverageService(
        lambda: SqlAlchemyCollectionProvenanceUnitOfWork(db_session_factory)
    )
    coverage = service.get_coverage_summary()
    provenance = service.get_raw_event_provenance(event.id)

    assert coverage.total_raw_events == 1
    assert coverage.with_provenance == 0
    assert coverage.without_provenance == 1
    assert coverage.provenance_coverage_percent == 0
    assert coverage.collection_run_count == 0
    assert coverage.observation_count == 0
    assert provenance.provenance_available is False
    assert provenance.observations == ()


def test_raw_event_and_observation_are_atomic_on_observation_failure(
    db_session: Session,
) -> None:
    investor = _create_investor(db_session)
    run = _create_run(db_session)

    class FailingObservationWriter:
        def record_observation(self, _command: CollectionObservationCreate) -> tuple[object, bool]:
            raise RuntimeError("observation write failed")

    adapter = _manual_adapter("atomic-event")
    request = _manual_request(investor)
    with pytest.raises(RuntimeError, match="observation write failed"):
        asyncio.run(
            DataPipeline(
                RawEventRepository(db_session),
                db_session,
                collection_observation_repository=FailingObservationWriter(),  # type: ignore[arg-type]
                collection_run_id=run.id,
            ).run(adapter, request)
        )

    assert db_session.scalar(select(func.count()).select_from(RawEvent)) == 0
    assert db_session.scalar(select(func.count()).select_from(CollectionObservation)) == 0


def test_observation_is_append_only(db_session: Session) -> None:
    investor = _create_investor(db_session)
    event = RawEvent(
        investor_id=investor.id,
        event_type=EventType.POST,
        source="manual",
        url="https://example.test/immutable",
        published_time=datetime(2026, 9, 5, tzinfo=UTC),
        content="immutable event",
        raw_data={},
        hash=uuid4().hex + uuid4().hex,
    )
    db_session.add(event)
    db_session.commit()
    run = _create_run(db_session)
    repository = CollectionObservationRepository(db_session)
    observation, created = repository.record_observation(
        CollectionObservationCreate(
            collection_run_id=run.id,
            raw_event_id=event.id,
            ingest_disposition=CollectionIngestDisposition.INSERTED,
        )
    )
    db_session.commit()
    assert created is True

    entity = db_session.get(CollectionObservation, observation.id)
    assert entity is not None
    entity.source_page = "changed"
    with pytest.raises(RuntimeError, match="append-only"):
        db_session.flush()
    db_session.rollback()
