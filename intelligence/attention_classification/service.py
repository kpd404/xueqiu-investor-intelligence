"""Read-only query service for deterministic Attention Classification V0."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import datetime
from types import TracebackType
from typing import Protocol, Self
from uuid import UUID

from contracts import (
    FeedState,
    IntelligenceAttentionAssetIdentity,
    IntelligenceAttentionClassificationView,
    IntelligenceAttentionEvidenceRef,
    IntelligenceAttentionEvidenceSummary,
    IntelligenceEventState,
)
from intelligence.attention_classification.rules import (
    AttentionClassificationFacts,
    classify_attention,
)
from intelligence.discovery.service import (
    DiscoveryAssetNotFoundError,
    IntelligenceDiscoveryService,
)
from intelligence.evolution.service import IntelligenceEvolutionService
from intelligence.read_scope import AssetIntelligenceReadScope


class _ListReader(Protocol):
    def list(self): ...


class _ScopeListReader:
    def __init__(self, values: tuple[object, ...]) -> None:
        self._values = values

    def list(self) -> tuple[object, ...]:
        return self._values


class _ScopeClassificationUoW:
    def __init__(self, scope: AssetIntelligenceReadScope) -> None:
        self.intelligence_events = _ScopeListReader(scope.events)
        self.intelligence_event_priorities = _ScopeListReader(scope.priorities)
        self.intelligence_feed_items = _ScopeListReader(scope.feed_items)
        self.intelligence_event_evidence = _ScopeListReader(scope.event_evidence)
        self.signals = _ScopeListReader(scope.signals)


class IntelligenceAttentionClassificationUoW(Protocol):
    """Rollback-only repositories needed for one classification read."""

    intelligence_events: _ListReader
    intelligence_event_priorities: _ListReader
    intelligence_feed_items: _ListReader
    intelligence_event_evidence: _ListReader
    signals: _ListReader

    def __enter__(self) -> Self: ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None: ...


IntelligenceAttentionClassificationUoWFactory = Callable[[], IntelligenceAttentionClassificationUoW]


class IntelligenceAttentionClassificationService:
    """Compose existing read-side layers without creating a new artifact."""

    def __init__(
        self,
        discovery_service: IntelligenceDiscoveryService,
        evolution_service: IntelligenceEvolutionService,
        unit_of_work_factory: IntelligenceAttentionClassificationUoWFactory,
    ) -> None:
        self._discovery_service = discovery_service
        self._evolution_service = evolution_service
        self._unit_of_work_factory = unit_of_work_factory

    @classmethod
    def from_production(
        cls,
        session_factory: Callable[[], object],
    ) -> IntelligenceAttentionClassificationService:
        from database.unit_of_work import SqlAlchemyIntelligenceAttentionClassificationUnitOfWork

        return cls(
            IntelligenceDiscoveryService.from_production(session_factory),
            IntelligenceEvolutionService.from_production(session_factory),
            lambda: SqlAlchemyIntelligenceAttentionClassificationUnitOfWork(session_factory),
        )

    def get_asset_attention_classification(
        self,
        asset_id: UUID,
    ) -> IntelligenceAttentionClassificationView:
        candidate = self._discovery_service.get_candidate_by_asset(asset_id)
        asset = (
            candidate.asset
            if candidate is not None
            else self._discovery_service.get_asset_identity(asset_id)
        )
        evolution = self._evolution_service.get_asset_evolution(asset_id)
        if evolution.asset.asset_id != asset_id:
            raise ValueError("Evolution asset identity mismatch")

        with self._unit_of_work_factory() as unit_of_work:
            return self._project(unit_of_work, asset, candidate, evolution)

    def get_scope_attention_classification(
        self,
        scope: AssetIntelligenceReadScope,
        candidate: object | None,
        evolution: object,
    ) -> IntelligenceAttentionClassificationView:
        return self._project(
            _ScopeClassificationUoW(scope),
            scope.asset,
            candidate,
            evolution,
        )

    def _project(
        self,
        unit_of_work: IntelligenceAttentionClassificationUoW,
        asset: object,
        candidate: object | None,
        evolution: object,
    ) -> IntelligenceAttentionClassificationView:
        events = {event.id: event for event in unit_of_work.intelligence_events.list()}
        priorities = {
            priority.id: priority for priority in unit_of_work.intelligence_event_priorities.list()
        }
        feeds = tuple(unit_of_work.intelligence_feed_items.list())
        signals = {signal.id: signal for signal in unit_of_work.signals.list()}
        links_by_event: dict[UUID, list[object]] = defaultdict(list)
        for link in unit_of_work.intelligence_event_evidence.list():
            links_by_event[link.event_id].append(link)

        active_events = tuple(
            sorted(
                (
                    event
                    for event in events.values()
                    if event.asset_id == asset.asset_id
                    and event.state is IntelligenceEventState.ACTIVE
                ),
                key=lambda event: (event.last_observed_at, event.event_type.value, event.id.int),
            )
        )
        active_event_ids = {event.id for event in active_events}
        active_priorities = tuple(
            sorted(
                (
                    priority
                    for priority in priorities.values()
                    if priority.event_id in active_event_ids
                ),
                key=lambda priority: (
                    priority.created_at,
                    priority.priority_level.value,
                    priority.id.int,
                ),
            )
        )
        active_feeds = tuple(
            sorted(
                (
                    feed
                    for feed in feeds
                    if feed.asset_id == asset.asset_id and feed.state is FeedState.ACTIVE
                ),
                key=lambda feed: (feed.observed_at, feed.event_type.value, feed.id.int),
            )
        )

        evidence_refs: dict[tuple[str, UUID], IntelligenceAttentionEvidenceRef] = {}
        review_event_types: set[str] = set()
        review_priority_levels: set[str] = set()
        review_priority_ids: set[UUID] = set()

        def add_ref(source_type: str, source_id: UUID) -> None:
            evidence_refs.setdefault(
                (source_type, source_id),
                IntelligenceAttentionEvidenceRef(source_type=source_type, source_id=source_id),
            )

        for event in active_events:
            add_ref("IntelligenceEvent", event.id)
            self._add_event_evidence(
                event,
                links_by_event.get(event.id, ()),
                signals,
                add_ref,
            )
        for priority in active_priorities:
            event = events.get(priority.event_id)
            if event is None:
                raise ValueError(f"Priority has no IntelligenceEvent: {priority.id}")
            if event.asset_id != asset.asset_id:
                raise ValueError(f"Priority asset mismatch: {priority.id}")
            add_ref("IntelligenceEventPriority", priority.id)
        for feed in active_feeds:
            priority = priorities.get(feed.priority_id)
            if priority is None:
                raise ValueError(f"FeedItem has no Priority: {feed.id}")
            event = events.get(priority.event_id)
            if event is None:
                raise ValueError(f"Priority has no IntelligenceEvent: {priority.id}")
            if event.asset_id != asset.asset_id or feed.asset_id != event.asset_id:
                raise ValueError(f"FeedItem asset mismatch: {feed.id}")
            if feed.event_type != event.event_type or feed.reason != priority.reason:
                raise ValueError(f"FeedItem semantic identity mismatch: {feed.id}")
            event_links = links_by_event.get(event.id, ())
            if len(event_links) != priority.evidence_count:
                raise ValueError(f"Priority evidence count mismatch: {priority.id}")
            add_ref("IntelligenceFeedItem", feed.id)
            add_ref("IntelligenceEventPriority", priority.id)
            add_ref("IntelligenceEvent", event.id)
            self._add_event_evidence(event, event_links, signals, add_ref)
            review_event_types.add(event.event_type.value)
            review_priority_levels.add(priority.priority_level.value)
            review_priority_ids.add(priority.id)

        for step in evolution.timeline:
            if step.asset_id != asset.asset_id:
                raise ValueError(f"Evolution step asset mismatch: {step.step_id}")
            for source_ref in step.source_refs:
                add_ref(source_ref.source_type, source_ref.source_id)

        current_patterns = tuple(sorted(set(evolution.current_state.patterns)))
        current_alignment = evolution.current_state.alignment_state
        current_consensus = evolution.current_state.consensus_state
        facts = AttentionClassificationFacts(
            active_event_types=frozenset(review_event_types),
            active_priority_levels=frozenset(review_priority_levels),
            active_event_count=len(active_events),
            active_priority_count=len(review_priority_ids),
            active_feed_count=len(active_feeds),
            discovery_candidate_present=candidate is not None,
            pattern_types=frozenset(current_patterns),
            current_alignment=current_alignment,
            current_consensus=current_consensus,
            historical_artifact_count=len(evolution.timeline),
        )
        decision = classify_attention(facts)
        ordered_refs = tuple(
            sorted(
                evidence_refs.values(),
                key=lambda ref: (ref.source_type, ref.source_id.int),
            )
        )
        limitations = self._limitations(
            evolution=evolution,
            candidate_present=candidate is not None,
            active_event_count=len(active_events),
            active_feed_count=len(active_feeds),
            current_patterns=current_patterns,
            current_alignment=current_alignment,
            current_consensus=current_consensus,
            historical_artifact_count=len(evolution.timeline),
        )
        latest_observed_at = self._latest_observed_at(
            candidate=candidate,
            evolution=evolution,
            events=active_events,
            feeds=active_feeds,
        )
        return IntelligenceAttentionClassificationView(
            asset=IntelligenceAttentionAssetIdentity(
                asset_id=asset.asset_id,
                name=asset.name,
                market=asset.market,
                symbol=asset.symbol,
            ),
            attention_class=decision.attention_class,
            reasons=decision.reasons,
            evidence_summary=IntelligenceAttentionEvidenceSummary(
                active_event_count=len(active_events),
                active_priority_count=len(review_priority_ids),
                active_feed_count=len(active_feeds),
                historical_artifact_count=len(evolution.timeline),
                discovery_candidate_present=candidate is not None,
                evidence_ref_count=len(ordered_refs),
            ),
            evidence_refs=ordered_refs,
            current_patterns=current_patterns,
            current_alignment=current_alignment,
            current_consensus=current_consensus,
            latest_observed_at=latest_observed_at,
            limitations=limitations,
        )

    @staticmethod
    def _add_event_evidence(event, links, signals, add_ref) -> None:
        for link in links:
            signal = signals.get(link.signal_id)
            if signal is None:
                raise ValueError(f"Signal not found for Event evidence: {link.id}")
            if signal.asset_id != event.asset_id:
                raise ValueError(f"Signal asset mismatch: {link.id}")
            add_ref("Signal", signal.id)
            add_ref(signal.source_type, signal.source_id)

    @staticmethod
    def _limitations(
        *,
        evolution,
        candidate_present: bool,
        active_event_count: int,
        active_feed_count: int,
        current_patterns: tuple[str, ...],
        current_alignment: str | None,
        current_consensus: str | None,
        historical_artifact_count: int,
    ) -> tuple[str, ...]:
        limitations = list(evolution.limitations)
        if not any("Historical completeness is UNKNOWN" in item for item in limitations):
            limitations.append("Historical completeness is UNKNOWN.")
        if not candidate_present:
            if historical_artifact_count:
                limitations.append(
                    "No ACTIVE DiscoveryCandidate is available; historical artifacts remain "
                    "visible in this projection."
                )
            else:
                limitations.append(
                    "No ACTIVE DiscoveryCandidate or canonical historical artifact is available."
                )
        if active_event_count and not active_feed_count:
            limitations.append(
                "An unresolved ACTIVE IntelligenceEvent lifecycle row exists without an ACTIVE "
                "FeedItem; Event ACTIVE is not interpreted as current activity."
            )
        if current_consensus == "INSUFFICIENT_EVIDENCE":
            limitations.append(
                "Consensus is INSUFFICIENT_EVIDENCE; this expresses insufficient consensus "
                "coverage, not absence of consensus or absence of Intelligence."
            )
        if current_alignment == "INSUFFICIENT_EVIDENCE":
            limitations.append(
                "Directional alignment is INSUFFICIENT_EVIDENCE; no alignment direction is "
                "inferred."
            )
        if {"NEW_DISCOVERY", "ACCELERATING_ACTIVITY"}.intersection(current_patterns):
            limitations.append(
                "Historical completeness is UNKNOWN; absence-sensitive Pattern output is not "
                "used as Attention Classification evidence."
            )
        if historical_artifact_count and not active_event_count and not active_feed_count:
            limitations.append(
                "Current active review evidence is unavailable; this classification does not "
                "infer cooling, dormancy, or reactivation."
            )
        return tuple(dict.fromkeys(limitations))

    @staticmethod
    def _latest_observed_at(*, candidate, evolution, events, feeds) -> datetime | None:
        values = [
            evolution.timeline_range.latest_observed_at,
            candidate.timeline.latest_observed_at if candidate is not None else None,
            *(event.last_observed_at for event in events),
            *(feed.observed_at for feed in feeds),
        ]
        observed = [value for value in values if value is not None]
        return max(observed) if observed else None


__all__ = [
    "DiscoveryAssetNotFoundError",
    "IntelligenceAttentionClassificationService",
    "IntelligenceAttentionClassificationUoW",
]
