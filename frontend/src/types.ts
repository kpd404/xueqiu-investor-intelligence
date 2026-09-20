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

export interface InvestorListItem {
  investor_id: string;
  investor_name: string;
  attention_asset_count: number;
  opinion_asset_count: number;
  repeated_opinion_asset_count: number;
  latest_observed_evidence_time: string | null;
  completeness: "UNKNOWN";
}

export interface InvestorListResponse {
  items: InvestorListItem[];
  total: number;
}

export interface InvestorAssetIntelligenceSummary {
  asset_id: string;
  asset_name: string;
  market: string;
  symbol: string;
  attention_occurrence_count: number;
  first_attention_time: string | null;
  latest_attention_time: string | null;
  attention_evidence_types: EvidenceType[];
  opinion_count: number;
  first_opinion_time: string | null;
  latest_opinion_time: string | null;
  latest_observed_direction: Direction | null;
  thesis_change_count: number;
  changed_count: number;
  extended_count: number;
  reversal_count: number;
  missing_thesis_comparison_count: number;
  attention_investor_count: number;
  opinion_investor_count: number;
  shared_attention_investor_count: number;
  shared_opinion_investor_count: number;
  latest_evidence_time: string | null;
  alignment: string | null;
  consensus: string | null;
}

export interface InvestorOverlapSummary {
  other_investor_id: string;
  other_investor_name: string;
  shared_attention_asset_count: number;
  shared_opinion_asset_count: number;
}

export interface InvestorIntelligenceDataQuality {
  completeness: "UNKNOWN";
  absence_inference_supported: false;
  collection_provenance_available: false;
  opinion_coverage: "NONE" | "PARTIAL" | "COMPLETE";
  missing_thesis_comparison_count: number;
  cross_investor_lineage_available: boolean;
  limitations: string[];
}

export interface InvestorIntelligenceView {
  investor_id: string;
  investor_name: string;
  window_start: string;
  window_end: string;
  completeness: "UNKNOWN";
  first_observed_evidence_time: string | null;
  latest_observed_evidence_time: string | null;
  attention_asset_count: number;
  opinion_asset_count: number;
  repeated_opinion_asset_count: number;
  thesis_changed_asset_count: number;
  direction_reversal_asset_count: number;
  shared_attention_asset_count: number;
  shared_opinion_asset_count: number;
  asset_views: InvestorAssetIntelligenceSummary[];
  overlap_summaries: InvestorOverlapSummary[];
  data_quality: InvestorIntelligenceDataQuality;
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

export type AttentionClass =
  | "IMMEDIATE_REVIEW"
  | "ACTIVE_REVIEW"
  | "BACKGROUND_MONITORING"
  | "LIMITED_CONTEXT";

export interface ProductAssetIdentity {
  asset_id: string;
  name: string;
  market: string;
  symbol: string;
}

export interface ProductReviewView {
  attention_class: AttentionClass;
  reasons: string[];
  latest_observed_at: string | null;
}

export interface ProductDiscoveryView {
  is_discoverable: boolean;
  discovery_reasons: string[];
  activity_summary: {
    investor_count: number;
    signal_count: number;
    event_count: number;
    feed_count: number;
  } | null;
}

export interface ProductContextView {
  activity_context: {
    current_signal_count: number;
    previous_signal_count: number;
    change_description: string;
  };
  investor_context: {
    current_investor_count: number;
    previous_investor_count: number;
    new_investors: string[];
    returning_investors: string[];
  };
  attention_context: {
    current_attention_count: number;
    historical_attention_count: number;
    change_description: string;
  };
  thesis_context: {
    current_thesis_changes: number;
    historical_thesis_changes: number;
    direction_changes: string[];
  };
  timeline_context: {
    first_observed_at: string | null;
    latest_observed_at: string | null;
    current_window_start: string;
    current_window_end: string;
    previous_window_start: string;
    previous_window_end: string;
  };
}

export interface ProductNarrativeView {
  headline: string;
  summary: string;
  attention_summary: string;
  thesis_summary: string;
  cross_investor_summary: string;
  consensus_summary: string;
}

export interface ProductEvolutionStep {
  step_id: string;
  observed_at: string;
  step_type: string;
  asset_id: string;
  investor_id: string | null;
  title: string;
  facts: string[];
  source_refs: Array<{ source_type: string; source_id: string }>;
}

export interface ProductEvolutionView {
  timeline_range: {
    first_observed_at: string | null;
    latest_observed_at: string | null;
  };
  step_count: number;
  recent_steps: ProductEvolutionStep[];
}

export interface ProductLifecycleSummary {
  active_count: number;
  states: Record<string, number>;
}

export interface ProductDataQualityView {
  historical_completeness: "UNKNOWN";
  historical_comparison_supported: false;
  absence_inference_supported: false;
  limitations: string[];
}

export interface ProductTraceabilitySummary {
  source_ref_count: number;
  canonical_source_count: number;
  source_types: string[];
  signal_count: number;
  evidence_refs: Array<{ source_type: string; source_id: string }>;
}

export interface AssetIntelligenceView {
  asset: ProductAssetIdentity;
  review: ProductReviewView;
  discovery: ProductDiscoveryView;
  current_state: {
    alignment: string | null;
    consensus: string | null;
    patterns: string[];
  };
  context: ProductContextView;
  narrative: ProductNarrativeView;
  evolution: ProductEvolutionView;
  feed: ProductLifecycleSummary;
  events: ProductLifecycleSummary;
  data_quality: ProductDataQualityView;
  traceability_summary: ProductTraceabilitySummary;
}

export interface InvestorProductIdentity {
  investor_id: string;
  name: string;
  source_platform: string;
  source_user_id: string;
}

export interface InvestorProductAssetIdentity {
  asset_id: string;
  name: string;
  market: string;
  symbol: string;
}

export interface InvestorProductAttention {
  occurrence_count: number;
  first_observed_at: string | null;
  latest_observed_at: string | null;
  evidence_types: EvidenceType[];
}

export interface InvestorProductOpinion {
  opinion_count: number;
  latest_direction: Direction | null;
  latest_opinion_at: string | null;
  latest_opinion_id: string | null;
}

export interface InvestorProductThesis {
  thesis_change_count: number;
  latest_change_type: ThesisChangeType | null;
  latest_change_at: string | null;
  latest_thesis_change_id: string | null;
}

export interface InvestorProductRelationship {
  has_attention: boolean;
  has_opinion: boolean;
  attention_only: boolean;
}

export interface InvestorProductTraceability {
  attention_occurrence_ids: string[];
  raw_event_ids: string[];
  opinion_ids: string[];
  thesis_change_ids: string[];
}

export interface InvestorAssetIntelligenceProductView {
  asset: InvestorProductAssetIdentity;
  attention: InvestorProductAttention;
  opinion: InvestorProductOpinion;
  thesis: InvestorProductThesis;
  relationship: InvestorProductRelationship;
  latest_observed_at: string | null;
  traceability: InvestorProductTraceability;
}

export interface InvestorProductSummary {
  observed_asset_count: number;
  opinion_asset_count: number;
  thesis_change_count: number;
  attention_occurrence_count: number;
  opinion_count: number;
  latest_observed_at: string | null;
}

export interface InvestorProductCoverage {
  observed_assets: InvestorProductAssetIdentity[];
  opinion_assets: InvestorProductAssetIdentity[];
  attention_only_assets: InvestorProductAssetIdentity[];
}

export type InvestorProductActivityType =
  | "ATTENTION_OBSERVED"
  | "OPINION_RECORDED"
  | "THESIS_CHANGE_OBSERVED";

export interface InvestorProductActivityEvent {
  observed_at: string;
  event_type: InvestorProductActivityType;
  asset: InvestorProductAssetIdentity;
  source_refs: Array<[string, string]>;
}

export interface InvestorProductDataQuality {
  historical_completeness: "UNKNOWN";
  historical_comparison_supported: false;
  absence_inference_supported: false;
  limitations: string[];
}

export interface InvestorProductTraceabilitySummary {
  attention_occurrence_ref_count: number;
  raw_event_ref_count: number;
  opinion_ref_count: number;
  thesis_change_ref_count: number;
  activity_source_ref_count: number;
}

export interface InvestorProductView {
  investor: InvestorProductIdentity;
  window_start: string;
  window_end: string;
  summary: InvestorProductSummary;
  coverage: InvestorProductCoverage;
  asset_views: InvestorAssetIntelligenceProductView[];
  recent_activity: InvestorProductActivityEvent[];
  data_quality: InvestorProductDataQuality;
  traceability_summary: InvestorProductTraceabilitySummary;
}

export type OperationalStatusLevel =
  | "HEALTHY"
  | "ACTION_REQUIRED"
  | "SOURCE_LIMITED"
  | "STALE"
  | "UNKNOWN";

export type OperationalFreshness = "FRESH" | "STALE" | "UNKNOWN";

export interface OperationalStatusResponse {
  status: OperationalStatusLevel;
  freshness: OperationalFreshness;
  freshness_age_seconds: number | null;
  last_refresh_started_at: string | null;
  last_refresh_finished_at: string | null;
  last_successful_refresh_at: string | null;
  latest_status: "RUNNING" | "SUCCESS" | "PARTIAL_FAILURE" | "FAILED" | "SKIPPED_ALREADY_RUNNING" | null;
  latest_trigger: "MANUAL" | "SCHEDULED" | null;
  latest_failure_stage: string | null;
  latest_failure_code: string | null;
  next_expected_refresh_at: string | null;
  cdp_requirement: string;
}

export interface IntelligenceFeedInvestor {
  investor_id: string;
  name: string;
}

export interface IntelligenceFeedItem {
  id: string;
  priority_id: string;
  asset: {
    asset_id: string;
    name: string;
    market: string;
    symbol: string;
  };
  event_type:
    | "ASSET_ACTIVITY_SPIKE"
    | "INVESTOR_VIEW_CHANGE"
    | "CROSS_INVESTOR_DISCOVERY"
    | "CONSENSUS_STATE_CHANGE";
  priority_level: "LOW" | "MEDIUM" | "HIGH";
  reason:
    | "MULTI_INVESTOR_ATTENTION"
    | "THESIS_ACCELERATION"
    | "CROSS_INVESTOR_DISCOVERY"
    | "CONSENSUS_STATE_CHANGE";
  title: string;
  context: Record<string, unknown>;
  investors: IntelligenceFeedInvestor[];
  state: "NEW" | "ACTIVE" | "STALE" | "RESOLVED";
  observed_at: string;
  created_at: string;
}

export interface IntelligenceFeedListResponse {
  items: IntelligenceFeedItem[];
  total: number;
  limit: number;
  has_more: boolean;
}
