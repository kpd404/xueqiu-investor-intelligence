export type Direction =
  | "BULLISH"
  | "STRONG_BULLISH"
  | "NEUTRAL"
  | "BEARISH"
  | "STRONG_BEARISH";

export type ThesisChangeType =
  | "NEW_THESIS"
  | "THESIS_REINFORCED"
  | "THESIS_EXTENDED"
  | "THESIS_CHANGED"
  | "THESIS_UNCHANGED"
  | "INSUFFICIENT_EVIDENCE";

export type EvidenceType = "OPINION" | "EXPLICIT_MENTION" | "REPOST";

export interface AssetListItem {
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  attention_investor_count: number;
  attention_occurrence_count: number;
  opinion_investor_count: number;
  opinion_count: number;
  earliest_observed_time: string | null;
  latest_evidence_time: string | null;
  temporal_span_days: number | null;
  thesis_change_count: number;
  has_repeated_thesis: boolean;
  has_thesis_changed: boolean;
  has_direction_reversal: boolean;
  attention_opinion_gap: boolean;
  latest_alignment: string | null;
  latest_consensus: string | null;
  completeness: "UNKNOWN";
  data_quality_flags: string[];
}

export interface AssetListResponse {
  items: AssetListItem[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface AttentionObservation {
  investor_id: string;
  investor_name: string;
  attention_occurrence_id: string;
  raw_event_id: string;
  published_time: string;
  evidence_types: EvidenceType[];
  lag_seconds: number | null;
  lag_hours: number | null;
  lag_days: number | null;
  first_effective_opinion_id: string | null;
  first_opinion_time: string | null;
  first_opinion_direction: Direction | null;
  latest_thesis_change_type: ThesisChangeType | null;
  latest_thesis_change_time: string | null;
}

export interface ObservedAttentionEdge {
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  earliest_observed_investor_id: string;
  earliest_observed_investor_name: string;
  later_observed_investor_id: string;
  later_observed_investor_name: string;
  earliest_time: string;
  later_time: string;
  lag_seconds: number;
  lag_hours: number;
  lag_days: number;
  earliest_evidence_types: EvidenceType[];
  later_evidence_types: EvidenceType[];
  direction_relation:
    | "SAME_DIRECTION"
    | "OPPOSITE_DIRECTION"
    | "NEUTRAL_OR_MIXED"
    | "OPINION_MISSING";
  temporal_relation: "OBSERVED_LATER" | "SIMULTANEOUS_OBSERVATION";
  earliest_attention_occurrence_id: string;
  later_attention_occurrence_id: string;
  earliest_raw_event_id: string;
  later_raw_event_id: string;
}

export interface ObservedAttentionSequence {
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  window_start: string;
  window_end: string;
  completeness: "UNKNOWN";
  investor_count: number;
  occurrence_count: number;
  first_observed: AttentionObservation;
  later_observations: AttentionObservation[];
}

export interface ThesisEvolutionEntry {
  opinion_id: string;
  raw_event_id: string;
  event_analysis_id: string;
  published_time: string;
  direction: Direction;
  strength: number;
  confidence: number;
  thesis: string[];
  catalysts: string[];
  risks: string[];
  time_horizon: string | null;
  thesis_change_id: string | null;
  thesis_change_type: ThesisChangeType | null;
  thesis_change_time: string | null;
  thesis_comparison_status:
    | "INITIAL_OPINION"
    | "COMPARISON_AVAILABLE"
    | "MISSING_THESIS_COMPARISON";
  predecessor_opinion_id: string | null;
  direction_transition:
    | "INITIAL_DIRECTION"
    | "SAME_DIRECTION"
    | "BULLISH_TO_BEARISH"
    | "BEARISH_TO_BULLISH"
    | "TO_NEUTRAL"
    | "FROM_NEUTRAL"
    | "OTHER";
  temporal_gap_from_previous: number | null;
  temporal_gap_from_previous_hours: number | null;
  temporal_gap_from_previous_days: number | null;
}

export interface ThesisEvolutionTimeline {
  investor_id: string;
  investor_name: string;
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  window_start: string;
  window_end: string;
  completeness: "UNKNOWN";
  opinion_count: number;
  thesis_change_count: number;
  missing_thesis_change_count: number;
  first_opinion_time: string;
  latest_opinion_time: string;
  entries: ThesisEvolutionEntry[];
  changed_count: number;
  extended_count: number;
  reinforced_count: number;
  reversal_count: number;
  same_direction_change_count: number;
}

export interface InvestorView {
  investor_id: string;
  investor_name: string;
  first_attention_time: string | null;
  latest_attention_time: string | null;
  attention_occurrence_count: number;
  attention_evidence_types: EvidenceType[];
  first_attention_raw_event_id: string | null;
  opinion_count: number;
  first_opinion_time: string | null;
  latest_opinion_time: string | null;
  latest_observed_direction: Direction | null;
  latest_observed_confidence: number | null;
  thesis_change_count: number;
  latest_thesis_change_type: ThesisChangeType | null;
  reversal_count: number;
  changed_count: number;
  extended_count: number;
  missing_thesis_comparison_count: number;
  thesis_timeline: ThesisEvolutionTimeline | null;
  attention_opinion_relation:
    | "OPINION_AT_FIRST_ATTENTION"
    | "OPINION_AFTER_ATTENTION"
    | "ATTENTION_WITHOUT_OPINION"
    | "OPINION_WITHOUT_PRIOR_ATTENTION"
    | "SIMULTANEOUS";
  attention_to_first_opinion_lag: number | null;
  attention_to_first_opinion_lag_hours: number | null;
  attention_to_first_opinion_lag_days: number | null;
}

export interface AttentionSummary {
  attention_investor_count: number;
  attention_occurrence_count: number;
  earliest_observed_time: string | null;
  earliest_observed_investor_id: string | null;
  earliest_observed_investor_name: string | null;
  observed_span_seconds: number | null;
  observed_span_hours: number | null;
  observed_span_days: number | null;
  temporal_edges: ObservedAttentionEdge[];
}

export interface DataQuality {
  completeness: "UNKNOWN";
  opinion_coverage: "NONE" | "PARTIAL" | "COMPLETE" | null;
  missing_thesis_comparison_count: number;
  cross_investor_evidence_available: boolean;
  unresolved_semantic_limitations: string[];
}

export interface TimelineEvent {
  published_time: string;
  investor_id: string;
  investor_name: string;
  event_type:
    | "ATTENTION_FIRST_OBSERVED"
    | "ATTENTION_OBSERVED"
    | "OPINION_OBSERVED"
    | "THESIS_CHANGE_OBSERVED";
  evidence_types: EvidenceType[];
  direction: Direction | null;
  thesis_change_type: ThesisChangeType | null;
  attention_occurrence_id: string | null;
  opinion_id: string | null;
  event_analysis_id: string | null;
  raw_event_id: string | null;
  thesis_change_id: string | null;
  predecessor_opinion_id: string | null;
}

export interface Alignment {
  directional_alignment_state: string;
  opinion_coverage_state: string;
}

export interface Consensus {
  consensus_state: string;
  opinion_coverage_state: string;
}

export interface CombinedAssetView {
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  window_start: string;
  window_end: string;
  completeness: "UNKNOWN";
  attention_summary: AttentionSummary;
  observed_attention_sequence: ObservedAttentionSequence | null;
  investor_views: InvestorView[];
  alignment: Alignment | null;
  consensus: Consensus | null;
  data_quality: DataQuality;
  event_timeline: TimelineEvent[];
}

export interface TimelineResponse {
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  window_start: string;
  window_end: string;
  completeness: "UNKNOWN";
  events: TimelineEvent[];
  missing_thesis_comparison_count: number;
  data_quality_flags: string[];
}
