# Intelligence

维护 Investor × Asset 状态并执行聚合的业务逻辑层；当前阶段只保留边界。

## Observed Attention Propagation V0

ObservedAttentionPropagationService is a query-time, deterministic read
model. For each Asset and requested window it selects the first effective
AttentionOccurrence for each Investor, orders those presences by
published_time, and derives anchor-to-later observations with explicit lag
and provenance. completeness remains UNKNOWN: the result describes only
presence in the monitored sample and must not be interpreted as causality,
influence, following, source, or absence.

The service does not persist sequences, edges, scores, or rankings.

## Thesis Evolution V0

ThesisEvolutionService is a separate query-time read model for an effective
Investor × Asset Opinion timeline. It keeps the original Opinion direction
and the existing ThesisChange type independent, records
MISSING_THESIS_COMPARISON when a repeated effective Opinion has no current
comparison artifact, and keeps historical completeness UNKNOWN.

Direction changes are deterministic view-level transitions only. They do not
claim a long-term belief change, performance attribution, or investment action.

## Combined Asset Intelligence View V0

CombinedAssetIntelligenceService is a presentation-layer composition of the
existing Observed Attention, Thesis Evolution, Cross-Investor Alignment, and
Consensus read models. It adds no new semantic, score, ranking, Signal, or
persistent artifact. Its timeline is a stable presentation ordering of
traceable effective evidence; equal timestamps do not imply causality.
