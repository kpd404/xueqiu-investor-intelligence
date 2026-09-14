"""Read-only audit for CollectionRun/CollectionObservation coverage."""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.app.api.dependencies import _read_only_session  # noqa: E402
from collection.provenance import CollectionProvenanceCoverageService  # noqa: E402
from database.unit_of_work import SqlAlchemyCollectionProvenanceUnitOfWork  # noqa: E402


def main() -> int:
    service = CollectionProvenanceCoverageService(
        lambda: SqlAlchemyCollectionProvenanceUnitOfWork(_read_only_session)
    )
    coverage = service.get_coverage_summary()

    print("# Collection Provenance Coverage Audit")
    print(f"RawEvents: {coverage.total_raw_events}")
    print(f"RawEvents with reliable provenance: {coverage.with_provenance}")
    print(f"RawEvents without reliable provenance: {coverage.without_provenance}")
    print(f"Reliable provenance coverage: {coverage.provenance_coverage_percent:.4f}%")
    print(f"CollectionRuns: {coverage.collection_run_count}")
    print(f"CollectionObservations: {coverage.observation_count}")
    if coverage.buckets:
        print("Coverage by source / collection mode / coverage status:")
        for bucket in coverage.buckets:
            print(
                f"  source={bucket.source} mode={bucket.collection_mode.value} "
                f"coverage={bucket.coverage_status.value} "
                f"raw_events={bucket.raw_event_count} "
                f"observations={bucket.observation_count}"
            )
    else:
        print("Coverage buckets: none")
    print("Legacy treatment: no heuristic or probabilistic provenance backfill.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
