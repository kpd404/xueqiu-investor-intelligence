import asyncio
from uuid import uuid4

from contracts import AnalysisProcessingError, EventAnalysisStatus
from pipeline import AnalysisBackfillRunner, AnalysisRecoveryCandidate, AnalysisRecoveryRunner


def test_analysis_recovery_runner_only_attempts_active_failed_candidates() -> None:
    failed_event = uuid4()
    successful_event = uuid4()
    no_opinion_event = uuid4()
    missing_event = uuid4()
    calls = []

    async def processor(event_id):
        calls.append(event_id)
        if event_id == failed_event:
            raise AnalysisProcessingError("temporary", retryable=True, error_code="TIMEOUT")

    summary = asyncio.run(
        AnalysisRecoveryRunner(processor, batch_size=2, max_concurrency=2).run(
            (
                AnalysisRecoveryCandidate(missing_event, None),
                AnalysisRecoveryCandidate(no_opinion_event, EventAnalysisStatus.NO_OPINION),
                AnalysisRecoveryCandidate(failed_event, EventAnalysisStatus.FAILED),
                AnalysisRecoveryCandidate(successful_event, EventAnalysisStatus.SUCCESS),
            )
        )
    )

    assert calls == [failed_event]
    assert summary.attempted == 1
    assert summary.success == 0
    assert summary.failed == 1
    assert summary.reused == 2
    assert summary.skipped_missing == 1
    assert summary.failure_codes == (("TIMEOUT", 1),)


def test_analysis_recovery_runner_bounds_each_provider_batch_and_concurrency() -> None:
    event_ids = tuple(uuid4() for _ in range(5))
    active = 0
    max_active = 0
    calls = []

    async def processor(event_id):
        nonlocal active, max_active
        calls.append(event_id)
        active += 1
        max_active = max(max_active, active)
        await asyncio.sleep(0)
        active -= 1

    summary = asyncio.run(
        AnalysisRecoveryRunner(processor, batch_size=2, max_concurrency=2).run(
            tuple(
                AnalysisRecoveryCandidate(event_id, EventAnalysisStatus.FAILED)
                for event_id in event_ids
            )
        )
    )

    assert summary.attempted == len(event_ids)
    assert summary.success == len(event_ids)
    assert summary.failed == 0
    assert max_active <= 2
    assert set(calls) == set(event_ids)


def test_analysis_backfill_runner_only_attempts_missing_analysis_rows() -> None:
    missing_event = uuid4()
    success_event = uuid4()
    failed_event = uuid4()
    calls = []
    progress = []

    async def processor(event_id):
        calls.append(event_id)

    summary = asyncio.run(
        AnalysisBackfillRunner(processor, batch_size=1, max_concurrency=1).run(
            (
                AnalysisRecoveryCandidate(missing_event, None),
                AnalysisRecoveryCandidate(success_event, EventAnalysisStatus.SUCCESS),
                AnalysisRecoveryCandidate(failed_event, EventAnalysisStatus.FAILED),
            ),
            progress_callback=progress.append,
        )
    )

    assert calls == [missing_event]
    assert summary.attempted == 1
    assert summary.success == 1
    assert summary.reused == 1
    assert summary.skipped_failed == 1
    assert summary.skipped_missing == 0
    assert progress[-1].processed == 1
    assert progress[-1].remaining == 0
