"""Deterministic query-time Intelligence Evolution timeline builder."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import UTC, datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import NAMESPACE_URL, UUID, uuid5

from config import (
    get_production_analysis_policy,
    get_production_thesis_comparison_policy,
)
from contracts import (
    IntelligenceEventType,
    SignalType,
)
from intelligence.context.schemas import IntelligenceContextView
from intelligence.context.service import IntelligenceContextService
from intelligence.discovery.service import (
    DiscoveryAssetNotFoundError,
    IntelligenceDiscoveryService,
)
from intelligence.evolution.schemas import (
    EvolutionAssetIdentity,
    EvolutionCurrentState,
    EvolutionSourceRef,
    EvolutionStep,
    EvolutionStepType,
    EvolutionTimelineRange,
    IntelligenceEvolutionView,
)
from intelligence.patterns.schemas import IntelligencePatternView
from intelligence.patterns.service import IntelligencePatternService
from intelligence.read_scope import AssetIntelligenceReadScope
from intelligence.schemas.discovery import IntelligenceDiscoveryCandidate


class EvolutionReader(Protocol):
    def list(self): ...


class _ScopeReader:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def list(self) -> tuple[object, ...]:
        return self._values


class _ScopeThesisReader:
    def __init__(self, scope: AssetIntelligenceReadScope) -> None:
        self._scope = scope

    def list_effective_by_asset(self, asset_id, policy, comparison_version, *, as_of=None):
        if asset_id != self._scope.asset.asset_id:
            return []
        return list(self._scope.thesis_changes)


class _ScopeCrossReader:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def list_by_asset(self, asset_id):
        return [item for item in self._values if item.asset_id == asset_id]


class _ScopeEvolutionUoW:
    def __init__(self, scope: AssetIntelligenceReadScope) -> None:
        self.intelligence_feed_items = _ScopeReader(scope.feed_items)
        self.intelligence_event_priorities = _ScopeReader(scope.priorities)
        self.intelligence_events = _ScopeReader(scope.events)
        self.intelligence_event_evidence = _ScopeReader(scope.event_evidence)
        self.signals = _ScopeReader(scope.signals)
        self.thesis_changes = _ScopeThesisReader(scope)
        self.cross_investor_asset_snapshots = _ScopeCrossReader(scope.snapshots)
        self.cross_investor_asset_alignments = _ScopeCrossReader(scope.alignments)
        self.cross_investor_consensus_evidences = _ScopeCrossReader(scope.consensus_evidences)


class EvolutionThesisReader(Protocol):
    def list_effective_by_asset(
        self,
        asset_id: UUID,
        policy: object,
        comparison_version: str,
        *,
        as_of: datetime | None = None,
    ) -> list: ...


class EvolutionCrossReader(Protocol):
    def list_by_asset(self, asset_id: UUID) -> list: ...


class IntelligenceEvolutionUoW(Protocol):
    intelligence_feed_items: EvolutionReader
    intelligence_event_priorities: EvolutionReader
    intelligence_events: EvolutionReader
    intelligence_event_evidence: EvolutionReader
    signals: EvolutionReader
    thesis_changes: EvolutionThesisReader
    cross_investor_asset_snapshots: EvolutionCrossReader
    cross_investor_asset_alignments: EvolutionCrossReader
    cross_investor_consensus_evidences: EvolutionCrossReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


IntelligenceEvolutionUoWFactory = Callable[[], IntelligenceEvolutionUoW]


class IntelligenceEvolutionService:
    """Build ordered evolution steps from persisted evidence only."""

    def __init__(
        self,
        discovery_service: IntelligenceDiscoveryService,
        context_service: IntelligenceContextService,
        pattern_service: IntelligencePatternService,
        unit_of_work_factory: IntelligenceEvolutionUoWFactory,
    ) -> None:
        self._discovery_service = discovery_service
        self._context_service = context_service
        self._pattern_service = pattern_service
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(cls, session_factory: Callable[[], object]) -> IntelligenceEvolutionService:
        from database.unit_of_work import SqlAlchemyIntelligenceFeedUnitOfWork

        return cls(
            IntelligenceDiscoveryService.from_production(session_factory),
            IntelligenceContextService.from_production(session_factory),
            IntelligencePatternService.from_production(session_factory),
            lambda: SqlAlchemyIntelligenceFeedUnitOfWork(session_factory),
        )

    def get_asset_evolution(self, asset_id: UUID) -> IntelligenceEvolutionView:
        candidate = self._discovery_service.get_candidate_by_asset(asset_id)
        if candidate is None:
            identity = self._discovery_service.get_asset_identity(asset_id)
            context = self._context_service.get_asset_context(asset_id)
            pattern = self._pattern_service.get_context_patterns(context)
            return self._build_for_asset(
                asset_id,
                EvolutionAssetIdentity(
                    asset_id=identity.asset_id,
                    name=identity.name,
                    market=identity.market,
                    symbol=identity.symbol,
                ),
                context,
                pattern,
            )
        return self.get_candidate_evolution(candidate)

    def get_candidate_evolution(
        self,
        candidate: IntelligenceDiscoveryCandidate,
    ) -> IntelligenceEvolutionView:
        context = self._context_service.get_candidate_context(candidate)
        pattern = self._pattern_service.get_context_patterns(context)
        return self._build_for_asset(
            candidate.asset.asset_id,
            EvolutionAssetIdentity(
                asset_id=candidate.asset.asset_id,
                name=candidate.asset.name,
                market=candidate.asset.market,
                symbol=candidate.asset.symbol,
            ),
            context,
            pattern,
        )

    def get_scope_evolution(
        self,
        scope: AssetIntelligenceReadScope,
        context: IntelligenceContextView,
        pattern: IntelligencePatternView,
    ) -> IntelligenceEvolutionView:
        return self._project(
            _ScopeEvolutionUoW(scope),
            scope.asset.asset_id,
            EvolutionAssetIdentity(
                asset_id=scope.asset.asset_id,
                name=scope.asset.name,
                market=scope.asset.market,
                symbol=scope.asset.symbol,
            ),
            context,
            pattern,
        )

    def batch_get_evolution(
        self,
        asset_ids: Iterable[UUID] | None = None,
    ) -> tuple[IntelligenceEvolutionView, ...]:
        if asset_ids is None:
            candidates = self._discovery_service.get_candidates(limit=100).items
        else:
            requested = tuple(dict.fromkeys(asset_ids))
            all_candidates = {
                candidate.asset.asset_id: candidate
                for candidate in self._discovery_service.get_candidates(limit=100).items
            }
            candidates = tuple(
                all_candidates[asset_id] for asset_id in requested if asset_id in all_candidates
            )
        contexts = self._context_service.batch_get_context(candidates)
        patterns = tuple(
            self._pattern_service.get_context_patterns(context) for context in contexts
        )
        identities = {
            candidate.asset.asset_id: EvolutionAssetIdentity(
                asset_id=candidate.asset.asset_id,
                name=candidate.asset.name,
                market=candidate.asset.market,
                symbol=candidate.asset.symbol,
            )
            for candidate in candidates
        }
        with self._unit_of_work_factory() as unit_of_work:
            return tuple(
                self._project(
                    unit_of_work,
                    candidate.asset.asset_id,
                    identities[candidate.asset.asset_id],
                    context,
                    pattern,
                )
                for candidate, context, pattern in zip(candidates, contexts, patterns, strict=True)
            )

    def _build_for_asset(
        self,
        asset_id: UUID,
        identity: EvolutionAssetIdentity,
        context: IntelligenceContextView,
        pattern: IntelligencePatternView,
    ) -> IntelligenceEvolutionView:
        with self._unit_of_work_factory() as unit_of_work:
            return self._project(unit_of_work, asset_id, identity, context, pattern)

    def _project(
        self,
        unit_of_work: IntelligenceEvolutionUoW,
        asset_id: UUID,
        identity: EvolutionAssetIdentity,
        context: IntelligenceContextView,
        pattern: IntelligencePatternView,
    ) -> IntelligenceEvolutionView:
        steps = self._merge_and_order_steps(
            self._build_attention_steps(unit_of_work, asset_id),
            self._build_thesis_steps(unit_of_work, asset_id),
            self._build_event_steps(unit_of_work, asset_id),
            self._build_cross_investor_steps(unit_of_work, asset_id),
        )
        timeline_range = EvolutionTimelineRange(
            first_observed_at=(
                steps[0].observed_at if steps else context.timeline_context.first_observed_at
            ),
            latest_observed_at=(
                steps[-1].observed_at if steps else context.timeline_context.latest_observed_at
            ),
        )
        limitations = list(context.limitations)
        limitations.extend(item.description for item in pattern.data_quality)
        if not steps:
            limitations.append("No canonical EvolutionStep source is available for this Asset.")
        return IntelligenceEvolutionView(
            asset=identity,
            timeline=steps,
            current_state=EvolutionCurrentState(
                patterns=[item.type.value for item in pattern.patterns],
                alignment_state=self._state_part(
                    context.cross_investor_context.current_state,
                    "alignment",
                ),
                consensus_state=self._state_part(
                    context.cross_investor_context.current_state,
                    "consensus",
                ),
            ),
            timeline_range=timeline_range,
            limitations=list(dict.fromkeys(limitations)),
        )

    def _build_attention_steps(
        self,
        unit_of_work: IntelligenceEvolutionUoW,
        asset_id: UUID,
    ) -> list[EvolutionStep]:
        signals = [
            signal
            for signal in unit_of_work.signals.list()
            if signal.asset_id == asset_id and signal.signal_type == SignalType.NEW_ATTENTION
        ]
        return [
            self._step(
                asset_id=asset_id,
                observed_at=signal.observed_at,
                step_type=EvolutionStepType.INVESTOR_ATTENTION_ADDED,
                investor_id=signal.investor_id,
                title="Investor attention observed",
                facts=["Signal type: NEW_ATTENTION."],
                source_refs=[
                    EvolutionSourceRef(source_type="Signal", source_id=signal.id),
                    EvolutionSourceRef(source_type=signal.source_type, source_id=signal.source_id),
                ],
            )
            for signal in signals
        ]

    def _build_thesis_steps(
        self,
        unit_of_work: IntelligenceEvolutionUoW,
        asset_id: UUID,
    ) -> list[EvolutionStep]:
        policy = get_production_analysis_policy().as_effective_policy()
        comparison_version = get_production_thesis_comparison_policy().active_analysis_version
        changes = unit_of_work.thesis_changes.list_effective_by_asset(
            asset_id,
            policy,
            comparison_version,
        )
        return [
            self._step(
                asset_id=asset_id,
                observed_at=change.effective_time,
                step_type=EvolutionStepType.THESIS_ACTIVITY,
                investor_id=change.investor_id,
                title="Thesis activity observed",
                facts=[f"ThesisChange type: {change.change_type.value}."],
                source_refs=[
                    EvolutionSourceRef(source_type="ThesisChange", source_id=change.id),
                    EvolutionSourceRef(source_type="RawEvent", source_id=change.current_event_id),
                ],
            )
            for change in changes
        ]

    def _build_event_steps(
        self,
        unit_of_work: IntelligenceEvolutionUoW,
        asset_id: UUID,
    ) -> list[EvolutionStep]:
        priorities = {item.id: item for item in unit_of_work.intelligence_event_priorities.list()}
        events = [
            item for item in unit_of_work.intelligence_events.list() if item.asset_id == asset_id
        ]
        steps: list[EvolutionStep] = []
        for event in events:
            if event.event_type != IntelligenceEventType.ASSET_ACTIVITY_SPIKE:
                continue
            priority = next(
                (item for item in priorities.values() if item.event_id == event.id),
                None,
            )
            facts = [f"Event type: {event.event_type.value}."]
            refs = [EvolutionSourceRef(source_type="IntelligenceEvent", source_id=event.id)]
            if priority is not None:
                facts.append(f"Priority reason: {priority.reason.value}.")
                refs.append(EvolutionSourceRef(source_type="Priority", source_id=priority.id))
            steps.append(
                self._step(
                    asset_id=asset_id,
                    observed_at=event.last_observed_at,
                    step_type=EvolutionStepType.MULTI_INVESTOR_EXPANSION,
                    title="Multi-investor activity observed",
                    facts=facts,
                    source_refs=refs,
                )
            )
        return steps

    def _build_cross_investor_steps(
        self,
        unit_of_work: IntelligenceEvolutionUoW,
        asset_id: UUID,
    ) -> list[EvolutionStep]:
        snapshots = unit_of_work.cross_investor_asset_snapshots.list_by_asset(asset_id)
        snapshot_by_id = {item.id: item for item in snapshots}
        steps: list[EvolutionStep] = []
        for alignment in unit_of_work.cross_investor_asset_alignments.list_by_asset(asset_id):
            snapshot = snapshot_by_id.get(alignment.source_snapshot_id)
            if snapshot is None:
                raise ValueError(f"Alignment snapshot source is missing: {alignment.id}")
            steps.append(
                self._step(
                    asset_id=asset_id,
                    observed_at=snapshot.window_end,
                    step_type=EvolutionStepType.CROSS_INVESTOR_STATE,
                    title="Cross-investor state observed",
                    facts=[f"Alignment state: {alignment.directional_alignment_state.value}."],
                    source_refs=[
                        EvolutionSourceRef(
                            source_type="CrossInvestorAssetAlignment", source_id=alignment.id
                        ),
                        EvolutionSourceRef(
                            source_type="CrossInvestorAssetSnapshot", source_id=snapshot.id
                        ),
                    ],
                )
            )
        for evidence in unit_of_work.cross_investor_consensus_evidences.list_by_asset(asset_id):
            snapshot = snapshot_by_id.get(evidence.source_snapshot_id)
            if snapshot is None:
                raise ValueError(f"Consensus snapshot source is missing: {evidence.id}")
            steps.append(
                self._step(
                    asset_id=asset_id,
                    observed_at=snapshot.window_end,
                    step_type=EvolutionStepType.CONSENSUS_STATE,
                    title="Consensus state observed",
                    facts=[f"Consensus state: {evidence.consensus_state.value}."],
                    source_refs=[
                        EvolutionSourceRef(
                            source_type="CrossInvestorConsensusEvidence",
                            source_id=evidence.id,
                        ),
                        EvolutionSourceRef(
                            source_type="CrossInvestorAssetSnapshot", source_id=snapshot.id
                        ),
                    ],
                )
            )
        return steps

    @classmethod
    def _step(
        cls,
        *,
        asset_id: UUID,
        observed_at: datetime,
        step_type: EvolutionStepType,
        title: str,
        facts: list[str],
        source_refs: list[EvolutionSourceRef],
        investor_id: UUID | None = None,
    ) -> EvolutionStep:
        source_identity = ";".join(f"{ref.source_type}:{ref.source_id}" for ref in source_refs)
        step_id = uuid5(
            NAMESPACE_URL,
            f"intelligence-evolution:{asset_id}:{step_type.value}:{source_identity}",
        )
        return EvolutionStep(
            step_id=step_id,
            observed_at=_normalize_time(observed_at),
            step_type=step_type,
            asset_id=asset_id,
            investor_id=investor_id,
            title=title,
            facts=facts,
            source_refs=source_refs,
        )

    @classmethod
    def _merge_and_order_steps(cls, *groups: list[EvolutionStep]) -> list[EvolutionStep]:
        unique: dict[tuple[EvolutionStepType, str, UUID], EvolutionStep] = {}
        for group in groups:
            for step in group:
                canonical = step.source_refs[0]
                key = (step.step_type, canonical.source_type, canonical.source_id)
                unique.setdefault(key, step)
        return sorted(
            unique.values(),
            key=lambda step: (
                step.observed_at,
                step.step_type.value,
                step.source_refs[0].source_type,
                step.source_refs[0].source_id.int,
                step.step_id.int,
            ),
        )

    @staticmethod
    def _state_part(state: str | None, prefix: str) -> str | None:
        if state is None:
            return None
        marker = f"{prefix}="
        for part in state.split("; "):
            if part.startswith(marker):
                return part.removeprefix(marker)
        return None


def _normalize_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = ["DiscoveryAssetNotFoundError", "IntelligenceEvolutionService"]
