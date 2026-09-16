"""Deterministic Signal candidate generation from existing artifacts."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
)
from contracts import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    ConsensusEvidenceState,
    DirectionalAlignmentState,
    EventAnalysisStatus,
    SignalCreate,
    SignalSeverity,
    SignalType,
)
from database.models.attention_occurrence import AttentionOccurrence
from database.models.cross_investor_asset_alignment import CrossInvestorAssetAlignment
from database.models.cross_investor_consensus_evidence import CrossInvestorConsensusEvidence
from database.models.event_analysis import EventAnalysis
from database.repositories.thesis_changes import ThesisChangeRepository


class SignalSourceReader(Protocol):
    def list_candidates(
        self,
        *,
        asset_ids: frozenset[UUID] | None = None,
        event_ids: frozenset[UUID] | None = None,
        signal_types: frozenset[SignalType] | None = None,
    ) -> tuple[SignalCreate, ...]: ...


class SqlAlchemySignalSourceReader:
    """Read all four source streams with bounded batch queries."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_candidates(
        self,
        *,
        asset_ids: frozenset[UUID] | None = None,
        event_ids: frozenset[UUID] | None = None,
        signal_types: frozenset[SignalType] | None = None,
    ) -> tuple[SignalCreate, ...]:
        selected = signal_types if signal_types is not None else frozenset(SignalType)
        candidates: list[SignalCreate] = []
        if SignalType.NEW_ATTENTION in selected:
            candidates.extend(self._new_attention(asset_ids=asset_ids, event_ids=event_ids))
        if SignalType.THESIS_CHANGE in selected:
            candidates.extend(self._thesis_changes(asset_ids=asset_ids, event_ids=event_ids))
        if SignalType.CROSS_INVESTOR_ALIGNMENT in selected and event_ids is None:
            candidates.extend(self._alignments(asset_ids=asset_ids))
        if SignalType.CONSENSUS_CHANGE in selected and event_ids is None:
            candidates.extend(self._consensus(asset_ids=asset_ids))

        candidates.sort(
            key=lambda value: (
                value.observed_at,
                value.signal_type.value,
                value.asset_id.int,
                value.source_id.int,
            )
        )
        identities = [(item.signal_type, item.source_id) for item in candidates]
        if len(identities) != len(set(identities)):
            raise ValueError("Signal candidate source identity is duplicated")
        return tuple(candidates)

    def _new_attention(
        self,
        *,
        asset_ids: frozenset[UUID] | None,
        event_ids: frozenset[UUID] | None,
    ) -> list[SignalCreate]:
        attention_policy = get_production_attention_policy_version()
        analysis_policy = get_production_analysis_policy().as_effective_policy()
        statement = (
            select(AttentionOccurrence)
            .outerjoin(EventAnalysis, AttentionOccurrence.analysis_id == EventAnalysis.id)
            .where(
                AttentionOccurrence.attention_policy_version == attention_policy,
                or_(
                    AttentionOccurrence.analysis_id.is_(None),
                    and_(
                        EventAnalysis.analysis_version == analysis_policy.active_analysis_version,
                        EventAnalysis.status.in_(
                            [EventAnalysisStatus.SUCCESS, EventAnalysisStatus.PARTIALLY_RESOLVED]
                        ),
                    ),
                ),
            )
            .order_by(
                AttentionOccurrence.investor_id,
                AttentionOccurrence.asset_id,
                AttentionOccurrence.published_time,
                AttentionOccurrence.id,
            )
        )
        first_by_pair: dict[tuple[UUID, UUID], AttentionOccurrence] = {}
        for occurrence in self._session.scalars(statement):
            if asset_ids is not None and occurrence.asset_id not in asset_ids:
                continue
            first_by_pair.setdefault((occurrence.investor_id, occurrence.asset_id), occurrence)
        return [
            SignalCreate(
                asset_id=occurrence.asset_id,
                investor_id=occurrence.investor_id,
                signal_type=SignalType.NEW_ATTENTION,
                severity=SignalSeverity.LOW,
                source_type="AttentionOccurrence",
                source_id=occurrence.id,
                created_at=datetime.now(UTC),
                observed_at=self._as_utc(occurrence.published_time),
                metadata={
                    "rule": "first_observed_investor_asset_attention",
                    "evidence_types": list(occurrence.evidence_types),
                },
            )
            for occurrence in first_by_pair.values()
            if event_ids is None or occurrence.event_id in event_ids
        ]

    def _thesis_changes(
        self,
        *,
        asset_ids: frozenset[UUID] | None,
        event_ids: frozenset[UUID] | None,
    ) -> list[SignalCreate]:
        policy = get_production_analysis_policy().as_effective_policy()
        comparison_version = get_production_thesis_comparison_policy().active_analysis_version
        changes = ThesisChangeRepository(self._session).list_effective(
            policy,
            comparison_version,
        )
        return [
            SignalCreate(
                asset_id=change.asset_id,
                investor_id=change.investor_id,
                signal_type=SignalType.THESIS_CHANGE,
                severity=SignalSeverity.LOW,
                source_type="ThesisChange",
                source_id=change.id,
                created_at=datetime.now(UTC),
                observed_at=self._as_utc(change.effective_time),
                metadata={
                    "change_type": change.change_type.value,
                    "current_opinion_id": str(change.current_opinion_id),
                    "previous_opinion_id": (
                        str(change.previous_opinion_id)
                        if change.previous_opinion_id is not None
                        else None
                    ),
                },
            )
            for change in changes
            if (asset_ids is None or change.asset_id in asset_ids)
            and (event_ids is None or change.current_event_id in event_ids)
        ]

    def _alignments(self, *, asset_ids: frozenset[UUID] | None) -> list[SignalCreate]:
        statement = select(CrossInvestorAssetAlignment).where(
            CrossInvestorAssetAlignment.alignment_policy_version
            == CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
            CrossInvestorAssetAlignment.directional_alignment_state
            != DirectionalAlignmentState.INSUFFICIENT_EVIDENCE.value,
        )
        if asset_ids is not None:
            statement = statement.where(CrossInvestorAssetAlignment.asset_id.in_(asset_ids))
        return [
            SignalCreate(
                asset_id=alignment.asset_id,
                signal_type=SignalType.CROSS_INVESTOR_ALIGNMENT,
                source_type="CrossInvestorAssetAlignment",
                source_id=alignment.id,
                created_at=datetime.now(UTC),
                observed_at=self._as_utc(alignment.calculated_at),
                metadata={
                    "alignment_state": alignment.directional_alignment_state,
                    "alignment_policy_version": alignment.alignment_policy_version,
                },
            )
            for alignment in self._session.scalars(statement)
        ]

    def _consensus(self, *, asset_ids: frozenset[UUID] | None) -> list[SignalCreate]:
        qualifying_states = {
            ConsensusEvidenceState.DIVERGENT.value,
            ConsensusEvidenceState.CONSENSUS_BULLISH.value,
            ConsensusEvidenceState.CONSENSUS_BEARISH.value,
            ConsensusEvidenceState.CONSENSUS_NEUTRAL.value,
        }
        statement = select(CrossInvestorConsensusEvidence).where(
            CrossInvestorConsensusEvidence.consensus_policy_version
            == CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
            CrossInvestorConsensusEvidence.consensus_state.in_(qualifying_states),
        )
        if asset_ids is not None:
            statement = statement.where(CrossInvestorConsensusEvidence.asset_id.in_(asset_ids))
        return [
            SignalCreate(
                asset_id=evidence.asset_id,
                signal_type=SignalType.CONSENSUS_CHANGE,
                source_type="CrossInvestorConsensusEvidence",
                source_id=evidence.id,
                created_at=datetime.now(UTC),
                observed_at=self._as_utc(evidence.calculated_at),
                metadata={
                    "consensus_state": evidence.consensus_state,
                    "consensus_policy_version": evidence.consensus_policy_version,
                    "opinion_investor_count": evidence.opinion_investor_count,
                },
            )
            for evidence in self._session.scalars(statement)
        ]

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["SignalSourceReader", "SqlAlchemySignalSourceReader"]
