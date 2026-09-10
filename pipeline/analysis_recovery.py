"""Bounded recovery orchestration for active failed EventAnalysis rows."""

from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from uuid import UUID

from contracts import EventAnalysisStatus


@dataclass(frozen=True, slots=True)
class AnalysisRecoveryCandidate:
    """One RawEvent and the status of its active analysis identity."""

    event_id: UUID
    status: EventAnalysisStatus | None


@dataclass(frozen=True, slots=True)
class AnalysisRecoveryProgress:
    """Progress emitted after each bounded provider batch."""

    processed: int
    remaining: int
    success: int
    failed: int
    reused: int
    skipped_missing: int
    skipped_failed: int

    def as_dict(self) -> dict[str, int]:
        return {
            "processed": self.processed,
            "remaining": self.remaining,
            "success": self.success,
            "failed": self.failed,
            "reused": self.reused,
            "skipped_missing": self.skipped_missing,
            "skipped_failed": self.skipped_failed,
        }


@dataclass(frozen=True, slots=True)
class AnalysisRecoverySummary:
    """Operational counters for one bounded recovery run."""

    attempted: int
    success: int
    failed: int
    reused: int
    skipped_missing: int
    attempted_event_ids: tuple[UUID, ...]
    success_event_ids: tuple[UUID, ...]
    failed_event_ids: tuple[UUID, ...]
    failure_codes: tuple[tuple[str, int], ...]
    skipped_failed: int = 0

    def as_dict(self) -> dict[str, object]:
        """Return a JSON-safe operational summary."""

        return {
            "attempted": self.attempted,
            "success": self.success,
            "failed": self.failed,
            "reused": self.reused,
            "skipped_missing": self.skipped_missing,
            "skipped_failed": self.skipped_failed,
            "attempted_event_ids": [str(value) for value in self.attempted_event_ids],
            "success_event_ids": [str(value) for value in self.success_event_ids],
            "failed_event_ids": [str(value) for value in self.failed_event_ids],
            "failure_codes": dict(self.failure_codes),
        }


AnalysisProcessor = Callable[[UUID], Awaitable[object]]


class AnalysisRecoveryRunner:
    """Run one bounded analysis target set with explicit status selection."""

    def __init__(
        self,
        processor: AnalysisProcessor,
        *,
        batch_size: int = 10,
        max_concurrency: int = 6,
        target_status: EventAnalysisStatus | None = EventAnalysisStatus.FAILED,
    ) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be at least 1")
        if max_concurrency < 1:
            raise ValueError("max_concurrency must be at least 1")
        self._processor = processor
        self._batch_size = batch_size
        self._max_concurrency = max_concurrency
        # None means an absent active Analysis; FAILED is the default recovery
        # target retained for the 2F.2.5 workflow.
        self._target_status = target_status

    async def run(
        self,
        candidates: Sequence[AnalysisRecoveryCandidate],
        *,
        progress_callback: Callable[[AnalysisRecoveryProgress], None] | None = None,
    ) -> AnalysisRecoverySummary:
        ordered = sorted(candidates, key=lambda value: value.event_id.int)
        if self._target_status is None:
            to_attempt = [item for item in ordered if item.status is None]
            skipped_missing = 0
            skipped_failed = sum(item.status is EventAnalysisStatus.FAILED for item in ordered)
        else:
            to_attempt = [item for item in ordered if item.status is self._target_status]
            skipped_missing = sum(item.status is None for item in ordered)
            skipped_failed = 0
        reused = sum(
            item.status is not None and item.status is not EventAnalysisStatus.FAILED
            for item in ordered
        )

        attempted_event_ids = tuple(item.event_id for item in to_attempt)
        success_event_ids: list[UUID] = []
        failed_event_ids: list[UUID] = []
        failure_codes: Counter[str] = Counter()
        for start in range(0, len(to_attempt), self._batch_size):
            batch = to_attempt[start : start + self._batch_size]
            results = await self._run_batch(batch)
            for candidate, error in results:
                if error is None:
                    success_event_ids.append(candidate.event_id)
                    continue
                failed_event_ids.append(candidate.event_id)
                failure_codes[self._failure_code(error)] += 1
            if progress_callback is not None:
                progress_callback(
                    AnalysisRecoveryProgress(
                        processed=len(success_event_ids) + len(failed_event_ids),
                        remaining=len(to_attempt) - len(success_event_ids) - len(failed_event_ids),
                        success=len(success_event_ids),
                        failed=len(failed_event_ids),
                        reused=reused,
                        skipped_missing=skipped_missing,
                        skipped_failed=skipped_failed,
                    )
                )

        return AnalysisRecoverySummary(
            attempted=len(attempted_event_ids),
            success=len(success_event_ids),
            failed=len(failed_event_ids),
            reused=reused,
            skipped_missing=skipped_missing,
            attempted_event_ids=attempted_event_ids,
            success_event_ids=tuple(success_event_ids),
            failed_event_ids=tuple(failed_event_ids),
            failure_codes=tuple(sorted(failure_codes.items())),
            skipped_failed=skipped_failed,
        )

    async def _run_batch(
        self,
        batch: Sequence[AnalysisRecoveryCandidate],
    ) -> list[tuple[AnalysisRecoveryCandidate, Exception | None]]:
        semaphore = asyncio.Semaphore(self._max_concurrency)

        async def process_one(
            candidate: AnalysisRecoveryCandidate,
        ) -> tuple[AnalysisRecoveryCandidate, Exception | None]:
            async with semaphore:
                try:
                    await self._processor(candidate.event_id)
                except Exception as exc:
                    return candidate, exc
                return candidate, None

        return list(await asyncio.gather(*(process_one(item) for item in batch)))

    @staticmethod
    def _failure_code(error: Exception) -> str:
        value = getattr(error, "error_code", None) or getattr(error, "code", None)
        if hasattr(value, "value"):
            value = value.value
        return str(value or type(error).__name__)


class AnalysisBackfillRunner(AnalysisRecoveryRunner):
    """Backfill only RawEvents missing the active Analysis identity."""

    def __init__(
        self,
        processor: AnalysisProcessor,
        *,
        batch_size: int = 10,
        max_concurrency: int = 6,
    ) -> None:
        super().__init__(
            processor,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            target_status=None,
        )
