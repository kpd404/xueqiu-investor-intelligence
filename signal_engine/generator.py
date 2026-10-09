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
    EventAnalysisStatus,
    SignalCreate,
    SignalSeverity,
    SignalType,
    ThesisChangeType,
)
from database.models.attention_occurrence import AttentionOccurrence
from database.models.event_analysis import EventAnalysis
from database.models.signal import Signal
from database.repositories.thesis_changes import ThesisChangeRepository
from signal_engine.cross_investor_sources import (
    CrossInvestorReferencedEvidenceReader,
    select_effective_cross_signals,
)


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
        cross_sources = ((), (), {}, {})
        if event_ids is None and selected & {
            SignalType.CROSS_INVESTOR_ALIGNMENT,
            SignalType.CONSENSUS_CHANGE,
        }:
            cross_sources = CrossInvestorReferencedEvidenceReader(
                self._session
            ).list_with_equivalence(asset_ids=asset_ids)
        if SignalType.NEW_ATTENTION in selected:
            candidates.extend(self._new_attention(asset_ids=asset_ids, event_ids=event_ids))
        if SignalType.THESIS_CHANGE in selected:
            candidates.extend(self._thesis_changes(asset_ids=asset_ids, event_ids=event_ids))
        if SignalType.CROSS_INVESTOR_ALIGNMENT in selected and event_ids is None:
            candidates.extend(
                self._alignments(
                    asset_ids=asset_ids, sources=cross_sources[0], fact_times=cross_sources[2]
                )
            )
        if SignalType.CONSENSUS_CHANGE in selected and event_ids is None:
            candidates.extend(
                self._consensus(
                    asset_ids=asset_ids, sources=cross_sources[1], fact_times=cross_sources[2]
                )
            )

        if cross_sources[3]:
            candidates = self._select_cross_candidates(candidates, cross_sources)

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

    def _select_cross_candidates(self, candidates, source_data):
        from signal_engine.repository import SignalRepository

        keys = source_data[3]
        kinds = {kind.value for kind, _source in keys}
        assets = {
            candidate.asset_id
            for candidate in candidates
            if (candidate.signal_type, candidate.source_id) in keys
        }
        # One batch, same transaction as add_if_absent. The database's unchanged
        # unique key protects one source only, not concurrent equivalent sources.
        histories = tuple(
            SignalRepository._to_view(row)
            for row in self._session.scalars(
                select(Signal).where(Signal.signal_type.in_(kinds), Signal.asset_id.in_(assets))
            )
        )
        existing = {
            keys[(signal.signal_type, signal.source_id)]: signal
            for signal in select_effective_cross_signals(histories, source_data)
        }
        occupied = {(signal.signal_type, signal.source_id) for signal in histories}
        selected = {}
        other = []
        for candidate in sorted(candidates, key=lambda value: value.source_id.int):
            identity = (candidate.signal_type, candidate.source_id)
            key = keys.get(identity)
            if key is None:
                other.append(candidate)
                continue
            previous = existing.get(key)
            if previous is not None:
                if identity == (previous.signal_type, previous.source_id):
                    selected[key] = candidate
            elif identity not in occupied:
                # Inactive/invalid rows cannot be reactivated by add_if_absent;
                # leave them historical and choose an unoccupied valid source.
                selected.setdefault(key, candidate)
        return [*other, *selected.values()]

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
        material_change_types = {
            ThesisChangeType.THESIS_REINFORCED,
            ThesisChangeType.THESIS_EXTENDED,
            ThesisChangeType.THESIS_CHANGED,
        }
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
            if change.change_type in material_change_types
            and (asset_ids is None or change.asset_id in asset_ids)
            and (event_ids is None or change.current_event_id in event_ids)
        ]

    def _alignments(
        self, *, asset_ids: frozenset[UUID] | None, sources, fact_times
    ) -> list[SignalCreate]:
        return [
            SignalCreate(
                asset_id=alignment.asset_id,
                signal_type=SignalType.CROSS_INVESTOR_ALIGNMENT,
                source_type="CrossInvestorAssetAlignment",
                source_id=alignment.id,
                created_at=datetime.now(UTC),
                observed_at=fact_times[(SignalType.CROSS_INVESTOR_ALIGNMENT, alignment.id)],
                metadata={
                    "alignment_state": alignment.directional_alignment_state,
                    "alignment_policy_version": alignment.alignment_policy_version,
                },
            )
            for alignment in sources
        ]

    def _consensus(
        self, *, asset_ids: frozenset[UUID] | None, sources, fact_times
    ) -> list[SignalCreate]:
        return [
            SignalCreate(
                asset_id=evidence.asset_id,
                signal_type=SignalType.CONSENSUS_CHANGE,
                source_type="CrossInvestorConsensusEvidence",
                source_id=evidence.id,
                created_at=datetime.now(UTC),
                observed_at=fact_times[(SignalType.CONSENSUS_CHANGE, evidence.id)],
                metadata={
                    "consensus_state": evidence.consensus_state,
                    "consensus_policy_version": evidence.consensus_policy_version,
                    "opinion_investor_count": evidence.opinion_investor_count,
                },
            )
            for evidence in sources
        ]

    @staticmethod
    def _as_utc(value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)


__all__ = ["SignalSourceReader", "SqlAlchemySignalSourceReader"]
