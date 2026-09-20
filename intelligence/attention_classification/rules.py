"""Centralized deterministic rules for Attention Classification V0."""

from __future__ import annotations

from dataclasses import dataclass, field

from contracts import (
    IntelligenceAttentionClass,
    IntelligenceAttentionReason,
)


@dataclass(frozen=True, slots=True)
class AttentionClassificationFacts:
    """Normalized facts consumed by the Classification rule set."""

    active_event_types: frozenset[str] = field(default_factory=frozenset)
    active_priority_levels: frozenset[str] = field(default_factory=frozenset)
    active_event_count: int = 0
    active_priority_count: int = 0
    active_feed_count: int = 0
    discovery_candidate_present: bool = False
    pattern_types: frozenset[str] = field(default_factory=frozenset)
    current_alignment: str | None = None
    current_consensus: str | None = None
    historical_artifact_count: int = 0

    @property
    def has_active_intelligence(self) -> bool:
        return bool(self.active_feed_count or self.discovery_candidate_present)

    @property
    def has_historical_intelligence(self) -> bool:
        return self.historical_artifact_count > 0


@dataclass(frozen=True, slots=True)
class AttentionClassificationDecision:
    """Pure rule output before evidence and limitation projection."""

    attention_class: IntelligenceAttentionClass
    reasons: tuple[IntelligenceAttentionReason, ...]


_IMMEDIATE_REASON_ORDER = (
    IntelligenceAttentionReason.CONSENSUS_STATE_CHANGE,
    IntelligenceAttentionReason.CONSENSUS_FRAGMENTATION,
    IntelligenceAttentionReason.MULTI_INVESTOR_EXPANSION,
    IntelligenceAttentionReason.THESIS_TRANSITION,
    IntelligenceAttentionReason.HIGH_PRIORITY_EVIDENCE,
)


def classify_attention(facts: AttentionClassificationFacts) -> AttentionClassificationDecision:
    """Apply the explicit V0 precedence without counts-as-absence inference.

    Immediate review is triggered only by explicit change evidence already
    materialized by upstream Intelligence layers.  A zero previous-window
    count is intentionally not an input to these rules.
    """

    immediate_reasons: list[IntelligenceAttentionReason] = []
    if "CONSENSUS_STATE_CHANGE" in facts.active_event_types:
        immediate_reasons.append(IntelligenceAttentionReason.CONSENSUS_STATE_CHANGE)
    if "CONSENSUS_FRAGMENTATION" in facts.pattern_types:
        immediate_reasons.append(IntelligenceAttentionReason.CONSENSUS_FRAGMENTATION)
    if "MULTI_INVESTOR_EXPANSION" in facts.pattern_types:
        immediate_reasons.append(IntelligenceAttentionReason.MULTI_INVESTOR_EXPANSION)
    if "THESIS_TRANSITION" in facts.pattern_types:
        immediate_reasons.append(IntelligenceAttentionReason.THESIS_TRANSITION)
    if "HIGH" in facts.active_priority_levels:
        immediate_reasons.append(IntelligenceAttentionReason.HIGH_PRIORITY_EVIDENCE)

    ordered_immediate = tuple(
        reason for reason in _IMMEDIATE_REASON_ORDER if reason in immediate_reasons
    )
    if ordered_immediate:
        return AttentionClassificationDecision(
            attention_class=IntelligenceAttentionClass.IMMEDIATE_REVIEW,
            reasons=ordered_immediate,
        )
    if facts.has_active_intelligence:
        return AttentionClassificationDecision(
            attention_class=IntelligenceAttentionClass.ACTIVE_REVIEW,
            reasons=(IntelligenceAttentionReason.ACTIVE_INTELLIGENCE,),
        )
    if facts.has_historical_intelligence:
        return AttentionClassificationDecision(
            attention_class=IntelligenceAttentionClass.BACKGROUND_MONITORING,
            reasons=(IntelligenceAttentionReason.HISTORICAL_INTELLIGENCE,),
        )
    return AttentionClassificationDecision(
        attention_class=IntelligenceAttentionClass.LIMITED_CONTEXT,
        reasons=(IntelligenceAttentionReason.LIMITED_CONTEXT,),
    )


__all__ = [
    "AttentionClassificationDecision",
    "AttentionClassificationFacts",
    "classify_attention",
]
