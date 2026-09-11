"""Derive deterministic Consensus/Divergence evidence from existing artifacts."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
    ConsensusInvestorContribution,
    CrossInvestorAssetAlignmentView,
    CrossInvestorAssetSnapshotView,
    CrossInvestorConsensusEvidenceCreate,
    CrossInvestorConsensusEvidenceView,
    OpinionDirection,
    build_cross_investor_consensus_input_identity,
    classify_consensus_evidence_state,
)
from intelligence.services.cross_investor_asset_alignment import (
    classify_cross_investor_asset_snapshot,
)


class CrossInvestorConsensusEvidenceIntegrityError(ValueError):
    """Raised when source Snapshot/Alignment provenance is inconsistent."""


class CrossInvestorConsensusSnapshotNotFoundError(LookupError):
    """Raised when the requested source Snapshot is absent."""


class CrossInvestorConsensusAlignmentNotFoundError(LookupError):
    """Raised when the requested source Alignment is absent."""


class SnapshotReader(Protocol):
    def get(self, snapshot_id: UUID) -> CrossInvestorAssetSnapshotView | None: ...


class AlignmentReader(Protocol):
    def get(self, alignment_id: UUID) -> CrossInvestorAssetAlignmentView | None: ...

    def list_by_source_snapshot(
        self,
        source_snapshot_id: UUID,
    ) -> list[CrossInvestorAssetAlignmentView]: ...


class EvidenceWriter(Protocol):
    def add_if_absent(
        self,
        evidence: CrossInvestorConsensusEvidenceCreate,
    ) -> tuple[CrossInvestorConsensusEvidenceView, bool]: ...


class CrossInvestorConsensusEvidenceUnitOfWork(Protocol):
    cross_investor_asset_snapshots: SnapshotReader
    cross_investor_asset_alignments: AlignmentReader
    cross_investor_consensus_evidences: EvidenceWriter

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...

    def commit(self) -> None: ...


CrossInvestorConsensusEvidenceUnitOfWorkFactory = Callable[
    [],
    CrossInvestorConsensusEvidenceUnitOfWork,
]


_BULLISH_DIRECTIONS = {
    OpinionDirection.BULLISH,
    OpinionDirection.STRONG_BULLISH,
}
_BEARISH_DIRECTIONS = {
    OpinionDirection.BEARISH,
    OpinionDirection.STRONG_BEARISH,
}


def build_cross_investor_consensus_evidence(
    snapshot: CrossInvestorAssetSnapshotView,
    alignment: CrossInvestorAssetAlignmentView,
    *,
    consensus_policy_version: str,
    calculated_at: datetime,
) -> CrossInvestorConsensusEvidenceCreate:
    """Build one evidence command from exactly one Snapshot and Alignment."""

    if snapshot.cross_investor_policy_version != CROSS_INVESTOR_POLICY_VERSION:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Consensus evidence requires a v2 CrossInvestorAssetSnapshot"
        )
    if alignment.asset_id != snapshot.asset_id:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "source Snapshot and Alignment must belong to the same Asset"
        )
    if alignment.source_snapshot_id != snapshot.id:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Alignment must reference the source Snapshot"
        )
    if alignment.alignment_policy_version != CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Consensus evidence requires the active Alignment v1 policy"
        )

    expected_coverage, expected_alignment = classify_cross_investor_asset_snapshot(snapshot)
    if alignment.opinion_coverage_state is not expected_coverage:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Alignment coverage does not match source Snapshot contributions"
        )
    if alignment.directional_alignment_state is not expected_alignment:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Alignment direction does not match source Snapshot contributions"
        )

    attention_contributions = [
        contribution
        for contribution in snapshot.contributions
        if contribution.attention_occurrence_count > 0
    ]
    attention_investor_ids = {contribution.investor_id for contribution in attention_contributions}
    if snapshot.attention_investor_count != len(attention_investor_ids):
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Snapshot attention count does not match contributions"
        )
    if snapshot.attention_occurrence_count != sum(
        contribution.attention_occurrence_count for contribution in attention_contributions
    ):
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Snapshot attention occurrence count does not match contributions"
        )

    opinion_contributions = [
        contribution
        for contribution in attention_contributions
        if contribution.window_opinion_count > 0
    ]
    opinion_investor_ids = {contribution.investor_id for contribution in opinion_contributions}
    if snapshot.opinion_investor_count != len(opinion_investor_ids):
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Snapshot Opinion Investor count does not match contributions"
        )
    if not opinion_investor_ids <= attention_investor_ids:
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Opinion Investors must be a subset of Attention Investors"
        )
    if snapshot.opinion_count != sum(
        contribution.window_opinion_count for contribution in opinion_contributions
    ):
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Snapshot Opinion count does not match contributions"
        )

    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    latest_opinions: list[ConsensusInvestorContribution] = []
    for contribution in sorted(opinion_contributions, key=lambda value: value.investor_id.int):
        direction = contribution.latest_window_opinion_direction
        opinion_id = contribution.latest_window_opinion_id
        if direction is None or opinion_id is None:
            raise CrossInvestorConsensusEvidenceIntegrityError(
                "Opinion contribution must include latest Opinion ID and direction"
            )
        if opinion_id not in contribution.window_opinion_ids:
            raise CrossInvestorConsensusEvidenceIntegrityError(
                "latest Opinion must be present in the source contribution"
            )
        if direction in _BULLISH_DIRECTIONS:
            bullish_count += 1
        elif direction in _BEARISH_DIRECTIONS:
            bearish_count += 1
        elif direction is OpinionDirection.NEUTRAL:
            neutral_count += 1
        else:
            raise CrossInvestorConsensusEvidenceIntegrityError(
                f"unsupported Opinion direction: {direction}"
            )
        latest_opinions.append(
            ConsensusInvestorContribution(
                investor_id=contribution.investor_id,
                window_opinion_count=contribution.window_opinion_count,
                latest_opinion_id=opinion_id,
                latest_opinion_direction=direction,
            )
        )

    if (
        snapshot.bullish_investor_count,
        snapshot.bearish_investor_count,
        snapshot.neutral_investor_count,
    ) != (bullish_count, bearish_count, neutral_count):
        raise CrossInvestorConsensusEvidenceIntegrityError(
            "Snapshot direction counts do not match latest Opinion contributions"
        )

    consensus_state = classify_consensus_evidence_state(
        opinion_investor_count=snapshot.opinion_investor_count,
        bullish_investor_count=bullish_count,
        bearish_investor_count=bearish_count,
        neutral_investor_count=neutral_count,
        consensus_policy_version=consensus_policy_version,
    )

    return CrossInvestorConsensusEvidenceCreate(
        asset_id=snapshot.asset_id,
        source_snapshot_id=snapshot.id,
        source_alignment_id=alignment.id,
        attention_investor_count=snapshot.attention_investor_count,
        opinion_investor_count=snapshot.opinion_investor_count,
        bullish_investor_count=bullish_count,
        bearish_investor_count=bearish_count,
        neutral_investor_count=neutral_count,
        opinion_coverage_state=alignment.opinion_coverage_state,
        consensus_state=consensus_state,
        contributing_investor_ids=tuple(
            sorted(attention_investor_ids, key=lambda value: value.int)
        ),
        latest_opinions=tuple(latest_opinions),
        consensus_policy_version=consensus_policy_version,
        input_identity=build_cross_investor_consensus_input_identity(
            source_snapshot_input_identity=snapshot.input_identity,
            source_alignment_input_identity=alignment.input_identity,
            consensus_policy_version=consensus_policy_version,
        ),
        calculated_at=calculated_at,
        created_at=calculated_at,
    )


class CrossInvestorConsensusEvidenceService:
    """Persist one immutable Consensus/Divergence evidence artifact."""

    def __init__(
        self,
        unit_of_work_factory: CrossInvestorConsensusEvidenceUnitOfWorkFactory,
        *,
        consensus_policy_version: str = CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
        alignment_policy_version: str = CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    ) -> None:
        self._unit_of_work_factory = unit_of_work_factory
        self._consensus_policy_version = consensus_policy_version
        self._alignment_policy_version = alignment_policy_version

    def calculate(
        self,
        source_snapshot_id: UUID | CrossInvestorAssetSnapshotView,
        source_alignment_id: UUID | CrossInvestorAssetAlignmentView | None = None,
    ) -> CrossInvestorConsensusEvidenceView:
        with self._unit_of_work_factory() as unit_of_work:
            if isinstance(source_snapshot_id, CrossInvestorAssetSnapshotView):
                snapshot = source_snapshot_id
            else:
                snapshot = unit_of_work.cross_investor_asset_snapshots.get(source_snapshot_id)
                if snapshot is None:
                    raise CrossInvestorConsensusSnapshotNotFoundError(
                        f"CrossInvestorAssetSnapshot not found: {source_snapshot_id}"
                    )

            if isinstance(source_alignment_id, CrossInvestorAssetAlignmentView):
                alignment = source_alignment_id
            elif source_alignment_id is not None:
                alignment = unit_of_work.cross_investor_asset_alignments.get(source_alignment_id)
                if alignment is None:
                    raise CrossInvestorConsensusAlignmentNotFoundError(
                        f"CrossInvestorAssetAlignment not found: {source_alignment_id}"
                    )
            else:
                source_alignments = (
                    unit_of_work.cross_investor_asset_alignments.list_by_source_snapshot(
                        snapshot.id
                    )
                )
                candidates = [
                    item
                    for item in source_alignments
                    if item.alignment_policy_version == self._alignment_policy_version
                ]
                if len(candidates) != 1:
                    raise CrossInvestorConsensusAlignmentNotFoundError(
                        "exactly one active Alignment is required for the source Snapshot"
                    )
                alignment = candidates[0]

            calculated_at = datetime.now(UTC)
            evidence = build_cross_investor_consensus_evidence(
                snapshot,
                alignment,
                consensus_policy_version=self._consensus_policy_version,
                calculated_at=calculated_at,
            )
            persisted, _created = unit_of_work.cross_investor_consensus_evidences.add_if_absent(
                evidence
            )
            unit_of_work.commit()
            return persisted

    def process(
        self,
        source_snapshot_id: UUID | CrossInvestorAssetSnapshotView,
        source_alignment_id: UUID | CrossInvestorAssetAlignmentView | None = None,
    ) -> CrossInvestorConsensusEvidenceView:
        return self.calculate(source_snapshot_id, source_alignment_id)


__all__ = [
    "CrossInvestorConsensusAlignmentNotFoundError",
    "CrossInvestorConsensusEvidenceIntegrityError",
    "CrossInvestorConsensusEvidenceService",
    "CrossInvestorConsensusEvidenceUnitOfWork",
    "CrossInvestorConsensusEvidenceUnitOfWorkFactory",
    "CrossInvestorConsensusSnapshotNotFoundError",
    "build_cross_investor_consensus_evidence",
]
