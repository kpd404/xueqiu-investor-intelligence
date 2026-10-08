"""Read-only validation of referenced evidence, not snapshot input completeness."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from config import (
    get_production_analysis_policy,
    get_production_attention_policy_version,
    get_production_thesis_comparison_policy,
)
from contracts import (
    CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
    CROSS_INVESTOR_POLICY_VERSION,
    ConsensusEvidenceState,
    DirectionalAlignmentState,
)
from contracts.consistency import CONSISTENCY_POLICY_VERSION
from contracts.cross_investor import (
    build_cross_investor_alignment_input_identity,
    build_cross_investor_input_identity,
)
from database.models import (
    CrossInvestorAssetAlignment,
    CrossInvestorAssetSnapshot,
    CrossInvestorConsensusEvidence,
    EventAnalysis,
    Opinion,
    RawEvent,
)
from database.repositories.attention_occurrences import AttentionOccurrenceRepository
from database.repositories.cross_investor_asset_alignments import (
    CrossInvestorAssetAlignmentRepository,
)
from database.repositories.cross_investor_asset_snapshots import (
    CrossInvestorAssetSnapshotRepository,
)
from database.repositories.cross_investor_consensus_evidences import (
    CrossInvestorConsensusEvidenceRepository,
)
from database.repositories.investor_action_consistency import InvestorActionConsistencyRepository
from database.repositories.opinions import OpinionRepository
from database.repositories.portfolio import PortfolioRepository
from database.repositories.portfolio_actions import PortfolioActionRepository
from database.repositories.thesis_changes import ThesisChangeRepository
from intelligence.services.cross_investor_asset_alignment import (
    classify_cross_investor_asset_snapshot,
)
from intelligence.services.cross_investor_consensus_evidence import (
    build_cross_investor_consensus_evidence,
)


class CrossInvestorReferencedEvidenceReader:
    """Validate explicit policies and existing references, grouped by asset/cutoff.

    New unreferenced facts do not invalidate a snapshot here. This deliberately
    does not select newest windows/versions, repair timestamps, or deduplicate facts.
    """

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _views(rows, repository):
        result = {}
        for row in rows:
            try:
                result[row.id] = repository._to_view(row)
            except ValueError:
                # One malformed historical artifact must not become a fallback
                # or prevent independent valid source chains from being read.
                continue
        return result

    def list_with_valid_references(self, *, asset_ids=None):
        alignments, consensus, _times = self.list_with_fact_times(asset_ids=asset_ids)
        return alignments, consensus

    def list_with_fact_times(self, *, asset_ids=None):
        """Return qualified source views plus times of their actual direction votes."""
        policy = get_production_analysis_policy().as_effective_policy()
        thesis_version = get_production_thesis_comparison_policy().active_analysis_version
        attention_version = get_production_attention_policy_version()
        statements = [
            select(CrossInvestorAssetSnapshot),
            select(CrossInvestorAssetAlignment),
            select(CrossInvestorConsensusEvidence),
        ]
        if asset_ids is not None:
            statements = [
                statement.where(model.asset_id.in_(asset_ids))
                for statement, model in zip(
                    statements,
                    (
                        CrossInvestorAssetSnapshot,
                        CrossInvestorAssetAlignment,
                        CrossInvestorConsensusEvidence,
                    ),
                    strict=True,
                )
            ]
        snapshots = self._views(
            self._session.scalars(statements[0]), CrossInvestorAssetSnapshotRepository
        )
        alignments = self._views(
            self._session.scalars(statements[1]), CrossInvestorAssetAlignmentRepository
        )
        consensus = self._views(
            self._session.scalars(statements[2]), CrossInvestorConsensusEvidenceRepository
        )
        scopes = {}
        valid_snapshots = {}
        snapshot_fact_times = {}
        for snapshot in snapshots.values():
            if (
                snapshot.cross_investor_policy_version != CROSS_INVESTOR_POLICY_VERSION
                or snapshot.opinion_analysis_version != policy.active_analysis_version
                or snapshot.attention_policy_version != attention_version
                or snapshot.thesis_comparison_version != thesis_version
                or snapshot.consistency_policy_version != CONSISTENCY_POLICY_VERSION
            ):
                continue
            scope = (snapshot.asset_id, snapshot.window_end)
            if scope not in scopes:
                scopes[scope] = self._load_scope(
                    snapshot,
                    policy,
                    attention_version,
                    thesis_version,
                    any(
                        value.asset_id == snapshot.asset_id
                        and value.window_end == snapshot.window_end
                        and any(
                            c.portfolio_action_ids or c.consistency_ids for c in value.contributions
                        )
                        for value in snapshots.values()
                    ),
                )
            try:
                if self._snapshot_references_match(snapshot, scopes[scope]):
                    valid_snapshots[snapshot.id] = snapshot
                    # Every latest Opinion below has already been identity/time
                    # checked against the effective Opinion -> RawEvent read.
                    # Newer non-voting artifacts never enter this time basis.
                    opinions = scopes[scope][0]
                    votes = [
                        opinions[value.latest_window_opinion_id].published_time
                        for value in snapshot.contributions
                        if value.window_opinion_count > 0
                    ]
                    if votes:
                        snapshot_fact_times[snapshot.id] = max(votes)
            except ValueError:
                continue
        valid_alignments = {}
        for alignment in alignments.values():
            snapshot = valid_snapshots.get(alignment.source_snapshot_id)
            if snapshot is None or alignment.asset_id != snapshot.asset_id:
                continue
            if alignment.alignment_policy_version != CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION:
                continue
            if alignment.input_identity != build_cross_investor_alignment_input_identity(
                source_snapshot_input_identity=snapshot.input_identity,
                alignment_policy_version=CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION,
            ):
                continue
            try:
                expected = classify_cross_investor_asset_snapshot(snapshot)
            except ValueError:
                continue
            if expected != (
                alignment.opinion_coverage_state,
                alignment.directional_alignment_state,
            ):
                continue
            try:
                # Reuse the existing pure integrity/classification path; do not
                # copy direction counts or consensus algorithms into the reader.
                build_cross_investor_consensus_evidence(
                    snapshot,
                    alignment,
                    consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
                    calculated_at=alignment.calculated_at,
                )
            except ValueError:
                continue
            valid_alignments[alignment.id] = alignment
        valid_consensus = {}
        for value in consensus.values():
            snapshot = valid_snapshots.get(value.source_snapshot_id)
            alignment = valid_alignments.get(value.source_alignment_id)
            if (
                snapshot is None
                or alignment is None
                or value.consensus_policy_version != CROSS_INVESTOR_CONSENSUS_POLICY_VERSION
            ):
                continue
            if alignment.source_snapshot_id != snapshot.id or value.asset_id != snapshot.asset_id:
                continue
            try:
                expected = build_cross_investor_consensus_evidence(
                    snapshot,
                    alignment,
                    consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION,
                    calculated_at=value.calculated_at,
                )
            except ValueError:
                continue
            fields = type(expected).model_fields.keys() - {"calculated_at", "created_at"}
            if any(getattr(value, field) != getattr(expected, field) for field in fields):
                continue
            valid_consensus[value.id] = value
        qualifying = {
            ConsensusEvidenceState.DIVERGENT,
            ConsensusEvidenceState.CONSENSUS_BULLISH,
            ConsensusEvidenceState.CONSENSUS_BEARISH,
            ConsensusEvidenceState.CONSENSUS_NEUTRAL,
        }
        from contracts import SignalType

        qualified_alignments = tuple(
            value
            for value in valid_alignments.values()
            if value.directional_alignment_state
            is not DirectionalAlignmentState.INSUFFICIENT_EVIDENCE
            and value.source_snapshot_id in snapshot_fact_times
        )
        qualified_consensus = tuple(
            value
            for value in valid_consensus.values()
            if value.consensus_state in qualifying
            and value.source_snapshot_id in snapshot_fact_times
        )
        fact_times = {
            (SignalType.CROSS_INVESTOR_ALIGNMENT, value.id): snapshot_fact_times[
                value.source_snapshot_id
            ]
            for value in qualified_alignments
        }
        fact_times.update(
            {
                (SignalType.CONSENSUS_CHANGE, value.id): snapshot_fact_times[
                    value.source_snapshot_id
                ]
                for value in qualified_consensus
            }
        )
        return qualified_alignments, qualified_consensus, fact_times

    def _load_scope(
        self, snapshot, policy, attention_version, thesis_version, portfolio_references
    ):
        asset_id, end = snapshot.asset_id, snapshot.window_end
        opinions = OpinionRepository(self._session).list_effective_timeline_by_asset(
            asset_id, policy, as_of=end
        )
        attention = AttentionOccurrenceRepository(self._session).list_effective_by_asset(
            asset_id, policy, attention_version, as_of=end
        )
        thesis = ThesisChangeRepository(self._session).list_effective_by_asset(
            asset_id, policy, thesis_version, as_of=end
        )
        rows = self._session.execute(
            select(Opinion, EventAnalysis, RawEvent)
            .join(EventAnalysis, Opinion.analysis_id == EventAnalysis.id)
            .join(RawEvent, Opinion.event_id == RawEvent.id)
            .where(Opinion.asset_id == asset_id, RawEvent.published_time <= end)
        ).all()
        valid_identity = {
            opinion.id: opinion
            for opinion, analysis, raw in rows
            if analysis.event_id == raw.id and opinion.investor_id == raw.investor_id
        }
        raw = {
            row.id: row
            for row in self._session.scalars(select(RawEvent).where(RawEvent.published_time <= end))
        }
        actions, consistency, owners = {}, {}, {}
        if portfolio_references:
            actions = {
                item.id: item
                for item in PortfolioActionRepository(self._session).list_effective_by_asset(
                    asset_id, as_of=end
                )
            }
            consistency = {
                item.id: item
                for item in InvestorActionConsistencyRepository(
                    self._session
                ).list_effective_by_asset(
                    asset_id,
                    policy,
                    consistency_policy_version=CONSISTENCY_POLICY_VERSION,
                    as_of=end,
                )
            }
            owners = {
                item.id: item.investor_id for item in PortfolioRepository(self._session).list()
            }
        return (
            {item.opinion_id: item for item in opinions if item.opinion_id in valid_identity},
            {item.id: item for item in attention},
            {item.id: item for item in thesis},
            valid_identity,
            raw,
            actions,
            consistency,
            owners,
        )

    @staticmethod
    def _snapshot_references_match(snapshot, scope):
        opinions, attention, thesis, opinion_rows, raw, actions, consistency, owners = scope
        start, end = snapshot.window_start, snapshot.window_end
        attention_ids, opinion_ids, thesis_ids, action_ids, consistency_ids, dependencies = (
            [],
            [],
            [],
            [],
            [],
            [],
        )

        def within(item, investor_id, timestamp):
            return (
                item.asset_id == snapshot.asset_id
                and item.investor_id == investor_id
                and start <= timestamp <= end
            )

        def attention_identity(item, investor):
            fact = raw.get(item.event_id)
            if fact is None or fact.investor_id != investor:
                return False
            published = fact.published_time
            if published.tzinfo is None:
                from datetime import UTC

                published = published.replace(tzinfo=UTC)
            if published != item.published_time:
                return False
            if item.opinion_id is not None:
                opinion = opinions.get(item.opinion_id)
                stored = opinion_rows.get(item.opinion_id)
                if (
                    opinion is None
                    or stored is None
                    or opinion.event_id != item.event_id
                    or stored.analysis_id != item.analysis_id
                ):
                    return False
            return True

        for contribution in snapshot.contributions:
            investor = contribution.investor_id
            for identity in contribution.attention_occurrence_ids:
                item = attention.get(identity)
                if item is None or not within(item, investor, item.published_time):
                    return False
                if not attention_identity(item, investor):
                    return False
                attention_ids.append(identity)
            first_id = contribution.first_attention_occurrence_id
            if contribution.attention_occurrence_ids and first_id is None:
                return False
            if first_id is not None:
                first = attention.get(first_id)
                if (
                    first is None
                    or first.asset_id != snapshot.asset_id
                    or first.investor_id != investor
                    or first.published_time != contribution.first_attention_published_time
                ):
                    return False
                if not attention_identity(first, investor):
                    return False
                if contribution.attention_occurrence_ids:
                    dependencies.append((investor, first_id, first.published_time))
            referenced = []
            for identity in contribution.window_opinion_ids:
                item = opinions.get(identity)
                if item is None or not within(item, investor, item.published_time):
                    return False
                referenced.append(item)
                opinion_ids.append(identity)
            if referenced:
                latest = max(
                    referenced,
                    key=lambda item: (item.published_time, item.event_id.int, item.opinion_id.int),
                )
                if (latest.opinion_id, latest.direction, latest.published_time) != (
                    contribution.latest_window_opinion_id,
                    contribution.latest_window_opinion_direction,
                    contribution.latest_window_opinion_time,
                ):
                    return False
            elif (
                contribution.latest_window_opinion_id is not None
                or contribution.latest_window_opinion_direction is not None
                or contribution.latest_window_opinion_time is not None
            ):
                return False
            if len(contribution.thesis_change_ids) != len(contribution.thesis_change_types):
                return False
            for identity, kind in zip(
                contribution.thesis_change_ids, contribution.thesis_change_types, strict=True
            ):
                item = thesis.get(identity)
                if (
                    item is None
                    or not within(item, investor, item.effective_time)
                    or item.change_type != kind
                ):
                    return False
                current = opinions.get(item.current_opinion_id)
                if current is None or current.published_time != item.effective_time:
                    return False
                if item.previous_opinion_id is not None:
                    previous = opinions.get(item.previous_opinion_id)
                    if (
                        previous is None
                        or previous.investor_id != investor
                        or previous.asset_id != snapshot.asset_id
                        or previous.event_id != item.previous_event_id
                    ):
                        return False
                thesis_ids.append(identity)
            if len(contribution.portfolio_action_ids) != len(contribution.portfolio_action_types):
                return False
            for identity, kind in zip(
                contribution.portfolio_action_ids, contribution.portfolio_action_types, strict=True
            ):
                item = actions.get(identity)
                if (
                    item is None
                    or item.asset_id != snapshot.asset_id
                    or owners.get(item.portfolio_id) != investor
                    or not start <= item.effective_time <= end
                    or item.action_type != kind
                ):
                    return False
                action_ids.append(identity)
            if len(contribution.consistency_ids) != len(contribution.consistency_types):
                return False
            for identity, kind in zip(
                contribution.consistency_ids, contribution.consistency_types, strict=True
            ):
                item = consistency.get(identity)
                if (
                    item is None
                    or not within(item, investor, item.effective_time)
                    or item.consistency_type != kind
                    or item.opinion_analysis_version != snapshot.opinion_analysis_version
                ):
                    return False
                consistency_ids.append(identity)
        if any(
            len(values) != len(set(values))
            for values in (attention_ids, opinion_ids, thesis_ids, action_ids, consistency_ids)
        ):
            return False
        if (
            len(attention_ids),
            len(opinion_ids),
            len(thesis_ids),
            len(action_ids),
            len(consistency_ids),
        ) != (
            snapshot.attention_occurrence_count,
            snapshot.opinion_count,
            snapshot.thesis_change_count,
            snapshot.portfolio_action_count,
            snapshot.consistency_count,
        ):
            return False
        identity = build_cross_investor_input_identity(
            asset_id=snapshot.asset_id,
            as_of=snapshot.as_of,
            window_start=start,
            window_end=end,
            opinion_analysis_version=snapshot.opinion_analysis_version,
            attention_policy_version=snapshot.attention_policy_version,
            thesis_comparison_version=snapshot.thesis_comparison_version,
            consistency_policy_version=snapshot.consistency_policy_version,
            cross_investor_policy_version=snapshot.cross_investor_policy_version,
            attention_occurrence_ids=tuple(attention_ids),
            opinion_ids=tuple(opinion_ids),
            thesis_change_ids=tuple(thesis_ids),
            portfolio_action_ids=tuple(action_ids),
            consistency_ids=tuple(consistency_ids),
            first_attention_dependencies=tuple(dependencies),
        )
        return identity == snapshot.input_identity
