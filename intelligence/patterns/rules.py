"""Deterministic Pattern rules over the existing Context projection."""

from __future__ import annotations

from intelligence.context.schemas import IntelligenceContextView
from intelligence.patterns.schemas import (
    IntelligencePatternDataQualityType,
    IntelligencePatternEvidence,
    IntelligencePatternType,
    PatternDataQuality,
)


def detect_patterns(
    context: IntelligenceContextView,
    *,
    multi_investor_threshold: int,
) -> list[IntelligencePatternEvidence]:
    """Return fact-only pattern labels; no score or ordering is computed."""

    activity = context.activity_context
    investors = context.investor_context
    attention = context.attention_context
    thesis = context.thesis_context
    cross_state = context.cross_investor_context.current_state or ""
    historical_cross_state = context.cross_investor_context.historical_state
    patterns: list[IntelligencePatternEvidence] = []

    if activity.current_signal_count > 0 and activity.previous_signal_count == 0:
        patterns.append(
            IntelligencePatternEvidence(
                type=IntelligencePatternType.NEW_DISCOVERY,
                description=(
                    "Current-window Intelligence activity is present while the "
                    "previous window has no Signal activity."
                ),
                evidence=(
                    f"Current Signals: {activity.current_signal_count}; "
                    f"previous Signals: {activity.previous_signal_count}."
                ),
            )
        )

    if (
        activity.current_signal_count > activity.previous_signal_count
        or investors.current_investor_count > investors.previous_investor_count
    ):
        patterns.append(
            IntelligencePatternEvidence(
                type=IntelligencePatternType.ACCELERATING_ACTIVITY,
                description="Current-window activity counts are higher than the previous window.",
                evidence=(
                    f"Signals {activity.previous_signal_count} -> {activity.current_signal_count}; "
                    f"Investors {investors.previous_investor_count} -> "
                    f"{investors.current_investor_count}."
                ),
            )
        )

    if investors.current_investor_count >= multi_investor_threshold:
        patterns.append(
            IntelligencePatternEvidence(
                type=IntelligencePatternType.MULTI_INVESTOR_EXPANSION,
                description="Multiple monitored Investors appear in the current activity window.",
                evidence=(
                    f"Observed activity from {investors.current_investor_count} Investors; "
                    f"threshold: {multi_investor_threshold}."
                ),
            )
        )

    if attention.current_attention_count > 0 and attention.historical_attention_count > 0:
        if investors.returning_investors:
            patterns.append(
                IntelligencePatternEvidence(
                    type=IntelligencePatternType.RETURNING_ATTENTION,
                    description=(
                        "Investor participation is observed in both configured comparison windows."
                    ),
                    evidence=(
                        f"Returning Investor count: {len(investors.returning_investors)}; "
                        f"current attention evidence: {attention.current_attention_count}; "
                        f"previous attention evidence: {attention.historical_attention_count}."
                    ),
                )
            )

    if thesis.current_thesis_changes > 0:
        patterns.append(
            IntelligencePatternEvidence(
                type=IntelligencePatternType.THESIS_TRANSITION,
                description="Persisted ThesisChange artifacts are present in the current window.",
                evidence=(
                    f"Current ThesisChange count: {thesis.current_thesis_changes}; "
                    f"change types: {', '.join(thesis.direction_changes) or 'none'}."
                ),
            )
        )

    if (
        historical_cross_state is not None
        and cross_state != historical_cross_state
        and "consensus=CONSENSUS_" in cross_state
    ):
        patterns.append(
            IntelligencePatternEvidence(
                type=IntelligencePatternType.CONSENSUS_FORMATION,
                description=("Persisted Consensus state changed to an explicit consensus state."),
                evidence=(
                    f"Historical state: {historical_cross_state}; current state: {cross_state}."
                ),
            )
        )

    if any(
        marker in cross_state
        for marker in (
            "consensus=DIVERGENT",
            "consensus=MIXED_WITH_NEUTRAL",
            "alignment=MIXED_DIRECTION",
        )
    ):
        patterns.append(
            IntelligencePatternEvidence(
                type=IntelligencePatternType.CONSENSUS_FRAGMENTATION,
                description=(
                    "Persisted Cross-Investor state contains an explicit mixed or divergent state."
                ),
                evidence=f"Current state: {cross_state}.",
            )
        )

    return patterns


def detect_data_quality(context: IntelligenceContextView) -> list[PatternDataQuality]:
    quality: list[PatternDataQuality] = []
    if (
        context.activity_context.previous_signal_count == 0
        or context.timeline_context.first_observed_at is None
    ):
        quality.append(
            PatternDataQuality(
                type=IntelligencePatternDataQualityType.INSUFFICIENT_HISTORY,
                description=(
                    "The previous comparison window has insufficient observed activity "
                    "for a complete history comparison."
                ),
                evidence=(
                    f"Previous Signals: {context.activity_context.previous_signal_count}; "
                    "first observed at: "
                    f"{context.timeline_context.first_observed_at or 'unavailable'}."
                ),
            )
        )
    if context.cross_investor_context.historical_state is None:
        quality.append(
            PatternDataQuality(
                type=IntelligencePatternDataQualityType.HISTORICAL_COMPARISON_UNAVAILABLE,
                description="Historical Cross-Investor state is unavailable for comparison.",
                evidence=(
                    "No persisted historical Cross-Investor state is available "
                    "in the previous window."
                ),
            )
        )
    return quality


__all__ = ["detect_data_quality", "detect_patterns"]
