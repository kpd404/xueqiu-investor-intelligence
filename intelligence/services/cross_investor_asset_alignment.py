"""Derive deterministic coverage and directional alignment from one snapshot."""

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CrossInvestorAssetAlignmentCreate,
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    DirectionalAlignmentState,
    OpinionCoverageState,
    OpinionDirection,
    build_cross_investor_alignment_input_identity,
)


class CrossInvestorAssetAlignmentIntegrityError(ValueError):
    """Raised when a source snapshot cannot support a safe alignment view."""


class CrossInvestorAssetSnapshotNotFoundError(LookupError):
    """Raised when the requested immutable source snapshot is absent."""


class SnapshotReader(Protocol):
    def get(self, snapshot_id: UUID) -> CrossInvestorAssetSnapshotView | None: ...


class AlignmentWriter(Protocol):
    def add_if_absent(
        self,
        alignment: CrossInvestorAssetAlignmentCreate,
    ) -> tuple[CrossInvestorAssetAlignmentView, bool]: ...


class CrossInvestorAssetAlignmentUnitOfWork(Protocol):
    cross_investor_asset_snapshots: SnapshotReader
    cross_investor_asset_alignments: AlignmentWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


CrossInvestorAssetAlignmentUnitOfWorkFactory = Callable[[], CrossInvestorAssetAlignmentUnitOfWork]

_BULLISH_DIRECTIONS = {
    OpinionDirection.BULLISH,
    OpinionDirection.STRONG_BULLISH,
}
_BEARISH_DIRECTIONS = {
    OpinionDirection.BEARISH,
    OpinionDirection.STRONG_BEARISH,
}


def classify_cross_investor_asset_snapshot(
    snapshot: CrossInvestorAssetSnapshotView,
) -> tuple[OpinionCoverageState, DirectionalAlignmentState]:
    """Classify one immutable snapshot without touching persistence."""

    attention_investors = {
        contribution.investor_id
        for contribution in snapshot.contributions
        if contribution.attention_occurrence_count > 0
    }
    opinion_investors = {
        contribution.investor_id
        for contribution in snapshot.contributions
        if contribution.window_opinion_count > 0
    }

    if snapshot.attention_investor_count != len(attention_investors):
        raise CrossInvestorAssetAlignmentIntegrityError(
            "source snapshot attention_investor_count does not match contribution evidence"
        )
    if snapshot.opinion_investor_count != len(opinion_investors):
        raise CrossInvestorAssetAlignmentIntegrityError(
            "source snapshot opinion_investor_count does not match contribution evidence"
        )

    unexpected_opinion_investors = opinion_investors - attention_investors
    if unexpected_opinion_investors:
        unexpected = ", ".join(
            str(investor_id) for investor_id in sorted(unexpected_opinion_investors, key=str)
        )
        raise CrossInvestorAssetAlignmentIntegrityError(
            "Opinion Investors must be a subset of Attention Investors; "
            f"unexpected investor IDs: {unexpected}"
        )

    if snapshot.attention_investor_count < 2:
        raise CrossInvestorAssetAlignmentIntegrityError(
            "CrossInvestorAssetAlignment requires at least two Attention Investors"
        )

    if not opinion_investors:
        coverage = OpinionCoverageState.NONE
    elif len(opinion_investors) < len(attention_investors):
        coverage = OpinionCoverageState.PARTIAL
    else:
        coverage = OpinionCoverageState.COMPLETE

    if len(opinion_investors) < 2:
        return coverage, DirectionalAlignmentState.INSUFFICIENT_EVIDENCE

    sides: set[str] = set()
    for contribution in snapshot.contributions:
        if contribution.investor_id not in opinion_investors:
            continue
        direction = contribution.latest_window_opinion_direction
        if direction is None:
            raise CrossInvestorAssetAlignmentIntegrityError(
                "an Opinion Investor contribution is missing latest_window_opinion_direction"
            )
        sides.add(_direction_side(direction))

    if sides == {"bullish"}:
        directional_alignment = DirectionalAlignmentState.ALIGNED_BULLISH
    elif sides == {"bearish"}:
        directional_alignment = DirectionalAlignmentState.ALIGNED_BEARISH
    elif sides == {"neutral"}:
        directional_alignment = DirectionalAlignmentState.ALIGNED_NEUTRAL
    else:
        directional_alignment = DirectionalAlignmentState.MIXED_DIRECTION
    return coverage, directional_alignment


def _direction_side(direction: OpinionDirection) -> str:
    if direction in _BULLISH_DIRECTIONS:
        return "bullish"
    if direction in _BEARISH_DIRECTIONS:
        return "bearish"
    if direction is OpinionDirection.NEUTRAL:
        return "neutral"
    raise CrossInvestorAssetAlignmentIntegrityError(
        f"unsupported latest Opinion direction: {direction}"
    )


class CrossInvestorAssetAlignmentService:
    """Persist one immutable coverage/alignment view of a source snapshot."""

    def __init__(
        self,
        unit_of_work_factory: CrossInvestorAssetAlignmentUnitOfWorkFactory,
        *,
        alignment_policy_version: str = CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._alignment_policy_version = alignment_policy_version

    def calculate(
        self,
        source_snapshot_id: UUID | CrossInvestorAssetSnapshotView,
    ) -> CrossInvestorAssetAlignmentView:
        with self._unit_of_work_factory() as unit_of_work:
            if isinstance(source_snapshot_id, CrossInvestorAssetSnapshotView):
                snapshot = source_snapshot_id
            else:
                snapshot = unit_of_work.cross_investor_asset_snapshots.get(source_snapshot_id)
                if snapshot is None:
                    raise CrossInvestorAssetSnapshotNotFoundError(
                        f"CrossInvestorAssetSnapshot not found: {source_snapshot_id}"
                    )

            coverage, directional_alignment = classify_cross_investor_asset_snapshot(snapshot)
            calculated_at = datetime.now(UTC)
            alignment = CrossInvestorAssetAlignmentCreate(
                asset_id=snapshot.asset_id,
                source_snapshot_id=snapshot.id,
                opinion_coverage_state=coverage,
                directional_alignment_state=directional_alignment,
                alignment_policy_version=self._alignment_policy_version,
                input_identity=build_cross_investor_alignment_input_identity(
                    source_snapshot_input_identity=snapshot.input_identity,
                    alignment_policy_version=self._alignment_policy_version,
                ),
                calculated_at=calculated_at,
                created_at=calculated_at,
            )
            persisted, _created = unit_of_work.cross_investor_asset_alignments.add_if_absent(
                alignment
            )
            unit_of_work.commit()
            return persisted

    def process(
        self,
        source_snapshot_id: UUID | CrossInvestorAssetSnapshotView,
    ) -> CrossInvestorAssetAlignmentView:
        """Compatibility alias for derived-artifact application callers."""

        return self.calculate(source_snapshot_id)


__all__ = [
    "CrossInvestorAssetAlignmentIntegrityError",
    "CrossInvestorAssetAlignmentService",
    "CrossInvestorAssetAlignmentUnitOfWork",
    "CrossInvestorAssetAlignmentUnitOfWorkFactory",
    "CrossInvestorAssetSnapshotNotFoundError",
    "classify_cross_investor_asset_snapshot",
]
