import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type { AssetListResponse, CombinedAssetView, TimelineResponse } from "./types";

const assetId = "asset-sh-601872";

const listPayload: AssetListResponse = {
  items: [
    {
      asset_id: assetId,
      asset_name: "招商轮船",
      market: "SH",
      symbol: "601872",
      attention_investor_count: 4,
      attention_occurrence_count: 5,
      opinion_investor_count: 4,
      opinion_count: 4,
      earliest_observed_time: "2026-08-27T10:16:06Z",
      latest_evidence_time: "2026-09-10T20:16:54Z",
      latest_alignment: "MIXED_DIRECTION",
      latest_consensus: "MIXED_WITH_NEUTRAL",
      completeness: "UNKNOWN",
      data_quality_flags: ["HISTORICAL_COMPLETENESS_UNKNOWN"]
    }
  ],
  total: 1,
  limit: 100,
  offset: 0,
  has_more: false
};

const detailPayload = {
  asset_id: assetId,
  asset_name: "招商轮船",
  market: "SH",
  symbol: "601872",
  window_start: "2026-08-27T10:16:06Z",
  window_end: "2026-09-10T20:16:54Z",
  completeness: "UNKNOWN",
  attention_summary: {
    attention_investor_count: 4,
    attention_occurrence_count: 5,
    earliest_observed_time: "2026-08-27T10:16:06Z",
    earliest_observed_investor_id: "investor-1",
    earliest_observed_investor_name: "笨笨的投资者2",
    observed_span_seconds: 1159488,
    observed_span_hours: 322.08,
    observed_span_days: 13.42,
    temporal_edges: []
  },
  observed_attention_sequence: {
    asset_id: assetId,
    asset_name: "招商轮船",
    market: "SH",
    symbol: "601872",
    window_start: "2026-08-27T10:16:06Z",
    window_end: "2026-09-10T20:16:54Z",
    completeness: "UNKNOWN",
    investor_count: 4,
    occurrence_count: 5,
    first_observed: {
      investor_id: "investor-1",
      investor_name: "笨笨的投资者2",
      attention_occurrence_id: "attention-1",
      raw_event_id: "raw-1",
      published_time: "2026-08-27T10:16:06Z",
      evidence_types: ["EXPLICIT_MENTION"],
      lag_seconds: null,
      lag_hours: null,
      lag_days: null,
      first_effective_opinion_id: null,
      first_opinion_time: null,
      first_opinion_direction: null,
      latest_thesis_change_type: null,
      latest_thesis_change_time: null
    },
    later_observations: [
      {
        investor_id: "investor-2",
        investor_name: "沈阳城",
        attention_occurrence_id: "attention-2",
        raw_event_id: "raw-2",
        published_time: "2026-09-02T07:01:02Z",
        evidence_types: ["OPINION", "EXPLICIT_MENTION"],
        lag_seconds: 506000,
        lag_hours: 121.6,
        lag_days: 5.86,
        first_effective_opinion_id: "opinion-2",
        first_opinion_time: "2026-09-02T07:01:02Z",
        first_opinion_direction: "NEUTRAL",
        latest_thesis_change_type: "NEW_THESIS",
        latest_thesis_change_time: "2026-09-02T07:01:02Z"
      },
      {
        investor_id: "investor-3",
        investor_name: "Captain-Nemo船长",
        attention_occurrence_id: "attention-3",
        raw_event_id: "raw-3",
        published_time: "2026-09-05T02:07:48Z",
        evidence_types: ["OPINION", "EXPLICIT_MENTION"],
        lag_seconds: 748000,
        lag_hours: 207.84,
        lag_days: 8.66,
        first_effective_opinion_id: "opinion-3",
        first_opinion_time: "2026-09-05T02:07:48Z",
        first_opinion_direction: "NEUTRAL",
        latest_thesis_change_type: "NEW_THESIS",
        latest_thesis_change_time: "2026-09-05T02:07:48Z"
      },
      {
        investor_id: "investor-4",
        investor_name: "看好股市的新人",
        attention_occurrence_id: "attention-4",
        raw_event_id: "raw-4",
        published_time: "2026-09-09T20:16:54Z",
        evidence_types: ["OPINION", "EXPLICIT_MENTION"],
        lag_seconds: 1150000,
        lag_hours: 322.08,
        lag_days: 13.42,
        first_effective_opinion_id: "opinion-4",
        first_opinion_time: "2026-09-09T20:16:54Z",
        first_opinion_direction: "NEUTRAL",
        latest_thesis_change_type: "NEW_THESIS",
        latest_thesis_change_time: "2026-09-09T20:16:54Z"
      }
    ]
  },
  investor_views: [
    {
      investor_id: "investor-1",
      investor_name: "笨笨的投资者2",
      first_attention_time: "2026-08-27T10:16:06Z",
      latest_attention_time: "2026-09-01T12:16:14Z",
      attention_occurrence_count: 2,
      attention_evidence_types: ["OPINION", "EXPLICIT_MENTION"],
      first_attention_raw_event_id: "raw-1",
      opinion_count: 1,
      first_opinion_time: "2026-09-01T12:16:14Z",
      latest_opinion_time: "2026-09-01T12:16:14Z",
      latest_observed_direction: "BULLISH",
      latest_observed_confidence: 0.88,
      thesis_change_count: 1,
      latest_thesis_change_type: "NEW_THESIS",
      reversal_count: 0,
      changed_count: 0,
      extended_count: 0,
      missing_thesis_comparison_count: 0,
      thesis_timeline: null,
      attention_opinion_relation: "OPINION_AFTER_ATTENTION",
      attention_to_first_opinion_lag: 435608,
      attention_to_first_opinion_lag_hours: 121.0,
      attention_to_first_opinion_lag_days: 5.04
    }
  ],
  alignment: {
    directional_alignment_state: "MIXED_DIRECTION",
    opinion_coverage_state: "COMPLETE"
  },
  consensus: {
    consensus_state: "MIXED_WITH_NEUTRAL",
    opinion_coverage_state: "COMPLETE"
  },
  data_quality: {
    completeness: "UNKNOWN",
    opinion_coverage: "COMPLETE",
    missing_thesis_comparison_count: 0,
    cross_investor_evidence_available: true,
    unresolved_semantic_limitations: [
      "HISTORICAL_COMPLETENESS_UNKNOWN",
      "ABSENCE_INFERENCE_UNSUPPORTED"
    ]
  },
  event_timeline: [
    {
      published_time: "2026-08-27T10:16:06Z",
      investor_id: "investor-1",
      investor_name: "笨笨的投资者2",
      event_type: "ATTENTION_FIRST_OBSERVED",
      evidence_types: ["EXPLICIT_MENTION"],
      direction: null,
      thesis_change_type: null,
      attention_occurrence_id: "attention-1",
      opinion_id: null,
      event_analysis_id: null,
      raw_event_id: "raw-1",
      thesis_change_id: null,
      predecessor_opinion_id: null
    }
  ]
} as unknown as CombinedAssetView;

const timelinePayload: TimelineResponse = {
  asset_id: assetId,
  asset_name: "招商轮船",
  market: "SH",
  symbol: "601872",
  window_start: "2026-08-27T10:16:06Z",
  window_end: "2026-09-10T20:16:54Z",
  completeness: "UNKNOWN",
  events: detailPayload.event_timeline,
  missing_thesis_comparison_count: 0,
  data_quality_flags: ["HISTORICAL_COMPLETENESS_UNKNOWN"]
};

function mockSuccessfulApi() {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url.endsWith("/timeline")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => timelinePayload });
    }
    if (url.endsWith("/assets/" + assetId)) {
      return Promise.resolve({ ok: true, status: 200, json: async () => detailPayload });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
  });
}

beforeEach(() => {
  window.history.replaceState({}, "", "/assets/" + assetId);
  vi.restoreAllMocks();
});

describe("Asset Intelligence Page V0", () => {
  it("loads the real API shape and presents the observed sequence", async () => {
    const fetchMock = mockSuccessfulApi();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "招商轮船" })).toBeInTheDocument();
    expect(screen.getByText("Historical completeness: UNKNOWN")).toBeInTheDocument();
    expect(screen.getByText("沈阳城")).toBeInTheDocument();
    expect(screen.getByText("Captain-Nemo船长")).toBeInTheDocument();
    expect(screen.getAllByText("OBSERVED LATER")).toHaveLength(3);
    expect(screen.getByText("DIRECTIONAL ALIGNMENT")).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/intelligence/assets/" + assetId,
      expect.any(Object)
    );
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/intelligence/assets/" + assetId + "/timeline",
      expect.any(Object)
    );
  });

  it("shows loading and a calm API error state", async () => {
    let rejectRequest: ((reason?: unknown) => void) | undefined;
    const pending = new Promise<never>((_, reject) => {
      rejectRequest = reject;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));

    render(<App />);
    expect(screen.getByText("Syncing evidence…")).toBeInTheDocument();

    rejectRequest?.(new Error("backend unavailable"));
    await waitFor(() => expect(screen.getByText("API unavailable")).toBeInTheDocument());
  });
});
