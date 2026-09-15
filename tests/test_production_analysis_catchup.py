from uuid import uuid4

from scripts.run_production_analysis_catchup import missing_event_ids


def test_missing_cohort_ignores_analysis_and_provenance_multiplicity() -> None:
    first = uuid4()
    second = uuid4()
    third = uuid4()

    assert missing_event_ids(
        (first, second, third),
        (first, first, second),
    ) == (third,)
