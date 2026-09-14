"""Read-only collection provenance coverage and lookup services."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    CollectionObservationProvenance,
    CollectionProvenanceCoverage,
    CollectionProvenanceCoverageBucket,
    CollectionRunView,
    RawEventCollectionProvenance,
)


class CollectionProvenanceRawEventReader(Protocol):
    def count(self) -> int: ...


class CollectionProvenanceRunReader(Protocol):
    def list_runs(self) -> list[CollectionRunView]: ...


class CollectionProvenanceObservationReader(Protocol):
    def list_all(self): ...

    def list_by_raw_event(self, raw_event_id: UUID): ...


class CollectionProvenanceUnitOfWork(Protocol):
    raw_events: CollectionProvenanceRawEventReader
    collection_runs: CollectionProvenanceRunReader
    collection_observations: CollectionProvenanceObservationReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


CollectionProvenanceUnitOfWorkFactory = Callable[[], CollectionProvenanceUnitOfWork]


class CollectionProvenanceCoverageService:
    """Read collection provenance without mutating legacy or current facts."""

    def __init__(self, unit_of_work_factory: CollectionProvenanceUnitOfWorkFactory) -> None:
        self._unit_of_work_factory = unit_of_work_factory

    def get_coverage_summary(self) -> CollectionProvenanceCoverage:
        """Return RawEvent provenance coverage and source/mode buckets."""

        with self._unit_of_work_factory() as unit_of_work:
            total_raw_events = unit_of_work.raw_events.count()
            runs = unit_of_work.collection_runs.list_runs()
            observations = unit_of_work.collection_observations.list_all()
        return self._build_coverage(total_raw_events, runs, observations)

    def get_raw_event_provenance(self, raw_event_id: UUID) -> RawEventCollectionProvenance:
        """Return all CollectionRun observations for one RawEvent."""

        with self._unit_of_work_factory() as unit_of_work:
            observations = unit_of_work.collection_observations.list_by_raw_event(raw_event_id)
            runs = {
                run.id: run
                for run in unit_of_work.collection_runs.list_runs()
                if run.id in {observation.collection_run_id for observation in observations}
            }
        enriched = tuple(
            self._enrich_observation(observation, runs[observation.collection_run_id])
            for observation in observations
        )
        return RawEventCollectionProvenance(
            raw_event_id=raw_event_id,
            provenance_available=bool(enriched),
            observations=enriched,
        )

    @classmethod
    def _build_coverage(
        cls,
        total_raw_events: int,
        runs: list[CollectionRunView],
        observations: list,
    ) -> CollectionProvenanceCoverage:
        run_by_id = {run.id: run for run in runs}
        raw_event_ids = {observation.raw_event_id for observation in observations}
        with_provenance = len(raw_event_ids)
        without_provenance = total_raw_events - with_provenance
        grouped: dict[tuple[str, object, object], list] = defaultdict(list)
        for observation in observations:
            run = run_by_id[observation.collection_run_id]
            grouped[(run.source, run.collection_mode, run.coverage_status)].append(observation)
        buckets = tuple(
            CollectionProvenanceCoverageBucket(
                source=source,
                collection_mode=collection_mode,
                coverage_status=coverage_status,
                raw_event_count=len({value.raw_event_id for value in values}),
                observation_count=len(values),
            )
            for (source, collection_mode, coverage_status), values in sorted(
                grouped.items(),
                key=lambda item: (item[0][0], item[0][1].value, item[0][2].value),
            )
        )
        return CollectionProvenanceCoverage(
            total_raw_events=total_raw_events,
            with_provenance=with_provenance,
            without_provenance=without_provenance,
            provenance_coverage_percent=(
                0.0 if total_raw_events == 0 else with_provenance / total_raw_events * 100
            ),
            collection_run_count=len(runs),
            observation_count=len(observations),
            buckets=buckets,
        )

    @staticmethod
    def _enrich_observation(observation, run: CollectionRunView) -> CollectionObservationProvenance:
        return CollectionObservationProvenance(
            collection_observation_id=observation.id,
            collection_run_id=observation.collection_run_id,
            raw_event_id=observation.raw_event_id,
            observed_at=observation.observed_at,
            ingest_disposition=observation.ingest_disposition,
            observation_sequence=observation.observation_sequence,
            source_page=observation.source_page,
            source_context_json=observation.source_context_json,
            source=run.source,
            adapter_name=run.adapter_name,
            collection_mode=run.collection_mode,
            transport=run.transport,
            run_status=run.run_status,
            stop_reason=run.stop_reason,
            coverage_status=run.coverage_status,
        )


__all__ = [
    "CollectionProvenanceCoverageService",
    "CollectionProvenanceUnitOfWork",
    "CollectionProvenanceUnitOfWorkFactory",
]
