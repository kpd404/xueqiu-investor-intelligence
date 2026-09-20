import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import App from "./App";
import type {
  AssetIntelligenceView,
  AssetListResponse,
  InvestorProductView,
  InvestorListResponse
} from "./types";

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
      temporal_span_days: 13.42,
      thesis_change_count: 4,
      has_repeated_thesis: false,
      has_thesis_changed: false,
      has_direction_reversal: false,
      attention_opinion_gap: false,
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

const productPayload: AssetIntelligenceView = {
  asset: {
    asset_id: assetId,
    name: "招商轮船",
    market: "SH",
    symbol: "601872"
  },
  review: {
    attention_class: "IMMEDIATE_REVIEW",
    reasons: ["THESIS_TRANSITION", "MULTI_INVESTOR_EXPANSION"],
    latest_observed_at: "2026-09-10T20:16:54Z"
  },
  discovery: {
    is_discoverable: true,
    discovery_reasons: ["MULTI_INVESTOR_ACTIVITY", "THESIS_ACTIVITY"],
    activity_summary: {
      investor_count: 4,
      signal_count: 5,
      event_count: 2,
      feed_count: 2
    }
  },
  current_state: {
    alignment: "MIXED_DIRECTION",
    consensus: "MIXED_WITH_NEUTRAL",
    patterns: ["MULTI_INVESTOR_EXPANSION", "THESIS_TRANSITION"]
  },
  context: {
    activity_context: {
      current_signal_count: 5,
      previous_signal_count: 0,
      change_description: "Observed signal activity is present in the current window."
    },
    investor_context: {
      current_investor_count: 4,
      previous_investor_count: 0,
      new_investors: ["investor-1", "investor-2"],
      returning_investors: []
    },
    attention_context: {
      current_attention_count: 5,
      historical_attention_count: 0,
      change_description: "Observed attention evidence is present in the current window."
    },
    thesis_context: {
      current_thesis_changes: 2,
      historical_thesis_changes: 0,
      direction_changes: ["THESIS_CHANGED"]
    },
    timeline_context: {
      first_observed_at: "2026-08-27T10:16:06Z",
      latest_observed_at: "2026-09-10T20:16:54Z",
      current_window_start: "2026-08-11T00:00:00Z",
      current_window_end: "2026-09-10T20:16:54Z",
      previous_window_start: "2026-07-12T00:00:00Z",
      previous_window_end: "2026-08-11T00:00:00Z"
    }
  },
  narrative: {
    headline: "Observed intelligence activity around 招商轮船",
    summary: "The current observed sample contains multiple evidence streams.",
    attention_summary: "The active evidence chain includes activity from 4 distinct monitored investor(s).",
    thesis_summary: "An INVESTOR_VIEW_CHANGE event is present for 招商轮船.",
    cross_investor_summary: "A CROSS_INVESTOR_DISCOVERY event is present for 招商轮船.",
    consensus_summary: "No CONSENSUS_STATE_CHANGE event is present in this active candidate."
  },
  evolution: {
    timeline_range: {
      first_observed_at: "2026-08-27T10:16:06Z",
      latest_observed_at: "2026-09-10T20:16:54Z"
    },
    step_count: 2,
    recent_steps: [
      {
        step_id: "step-1",
        observed_at: "2026-08-27T10:16:06Z",
        step_type: "INVESTOR_ATTENTION_ADDED",
        asset_id: assetId,
        investor_id: "investor-1",
        title: "Investor attention observed",
        facts: ["Signal type: NEW_ATTENTION."],
        source_refs: [{ source_type: "AttentionOccurrence", source_id: "attention-1" }]
      },
      {
        step_id: "step-2",
        observed_at: "2026-09-10T20:16:54Z",
        step_type: "THESIS_ACTIVITY",
        asset_id: assetId,
        investor_id: "investor-2",
        title: "Thesis activity observed",
        facts: ["ThesisChange type: THESIS_CHANGED."],
        source_refs: [{ source_type: "ThesisChange", source_id: "thesis-1" }]
      }
    ]
  },
  feed: {
    active_count: 2,
    states: { ACTIVE: 2 }
  },
  events: {
    active_count: 2,
    states: { ACTIVE: 2 }
  },
  data_quality: {
    historical_completeness: "UNKNOWN",
    historical_comparison_supported: false,
    absence_inference_supported: false,
    limitations: [
      "Historical completeness is UNKNOWN.",
      "Available collection provenance does not establish historical completeness.",
      "Absence inference is unsupported."
    ]
  },
  traceability_summary: {
    source_ref_count: 4,
    canonical_source_count: 2,
    source_types: ["AttentionOccurrence", "ThesisChange"],
    signal_count: 5,
    evidence_refs: [
      { source_type: "AttentionOccurrence", source_id: "attention-1" },
      { source_type: "ThesisChange", source_id: "thesis-1" }
    ]
  }
};

const cnoocProduct: AssetIntelligenceView = {
  ...productPayload,
  asset: {
    asset_id: "asset-hk-00883",
    name: "中国海洋石油",
    market: "HK",
    symbol: "00883"
  },
  review: {
    attention_class: "BACKGROUND_MONITORING",
    reasons: ["HISTORICAL_INTELLIGENCE"],
    latest_observed_at: "2026-09-10T09:32:37Z"
  },
  discovery: {
    is_discoverable: false,
    discovery_reasons: [],
    activity_summary: null
  },
  current_state: {
    alignment: null,
    consensus: null,
    patterns: []
  },
  narrative: {
    headline: "No active intelligence activity observed for 中国海洋石油",
    summary: "Historical observed Intelligence remains available.",
    attention_summary: "Historical Attention evidence is visible in Evolution.",
    thesis_summary: "Historical Thesis evidence is visible in Evolution.",
    cross_investor_summary: "No active cross-investor evidence is present.",
    consensus_summary: "No current Consensus evidence is present."
  },
  evolution: {
    timeline_range: {
      first_observed_at: "2026-09-10T09:32:37Z",
      latest_observed_at: "2026-09-10T09:32:37Z"
    },
    step_count: 2,
    recent_steps: productPayload.evolution.recent_steps
  },
  feed: { active_count: 0, states: {} },
  events: { active_count: 1, states: { ACTIVE: 1 } },
  traceability_summary: {
    source_ref_count: 6,
    canonical_source_count: 3,
    source_types: ["AttentionOccurrence", "ThesisChange", "RawEvent"],
    signal_count: 2,
    evidence_refs: [
      { source_type: "AttentionOccurrence", source_id: "attention-1" },
      { source_type: "ThesisChange", source_id: "thesis-1" }
    ]
  }
};

const moutaiProduct: AssetIntelligenceView = {
  ...productPayload,
  asset: { asset_id: "asset-sh-600519", name: "贵州茅台", market: "SH", symbol: "600519" },
  current_state: {
    alignment: "MIXED_DIRECTION",
    consensus: "INSUFFICIENT_EVIDENCE",
    patterns: ["MULTI_INVESTOR_EXPANSION", "THESIS_TRANSITION", "CONSENSUS_FRAGMENTATION"]
  }
};

const investorList: InvestorListResponse = {
  items: [
    {
      investor_id: "investor-1",
      investor_name: "Investor One",
      attention_asset_count: 1,
      opinion_asset_count: 1,
      repeated_opinion_asset_count: 0,
      latest_observed_evidence_time: "2026-08-27T10:16:06Z",
      completeness: "UNKNOWN"
    },
    {
      investor_id: "investor-2",
      investor_name: "Investor Two",
      attention_asset_count: 1,
      opinion_asset_count: 0,
      repeated_opinion_asset_count: 0,
      latest_observed_evidence_time: "2026-09-10T20:16:54Z",
      completeness: "UNKNOWN"
    }
  ],
  total: 2
};

const investorProductPayload: InvestorProductView = {
  investor: {
    investor_id: "investor-life",
    name: "纳履而去",
    source_platform: "xueqiu",
    source_user_id: "investor-life"
  },
  window_start: "2026-08-11T00:00:00Z",
  window_end: "2026-09-10T20:16:54Z",
  summary: {
    observed_asset_count: 3,
    opinion_asset_count: 2,
    thesis_change_count: 3,
    attention_occurrence_count: 6,
    opinion_count: 3,
    latest_observed_at: "2026-09-10T20:16:54Z"
  },
  coverage: {
    observed_assets: [
      { asset_id: "asset-zijin-sh", name: "紫金矿业", market: "SH", symbol: "601899" },
      { asset_id: "asset-gold-hk", name: "山东黄金", market: "HK", symbol: "01787" },
      { asset_id: "asset-gold-sh", name: "山东黄金", market: "SH", symbol: "600547" }
    ],
    opinion_assets: [
      { asset_id: "asset-zijin-sh", name: "紫金矿业", market: "SH", symbol: "601899" },
      { asset_id: "asset-gold-hk", name: "山东黄金", market: "HK", symbol: "01787" }
    ],
    attention_only_assets: [
      { asset_id: "asset-gold-sh", name: "山东黄金", market: "SH", symbol: "600547" }
    ]
  },
  asset_views: [
    {
      asset: { asset_id: "asset-zijin-sh", name: "紫金矿业", market: "SH", symbol: "601899" },
      attention: {
        occurrence_count: 3,
        first_observed_at: "2026-08-22T10:00:00Z",
        latest_observed_at: "2026-09-10T20:16:54Z",
        evidence_types: ["OPINION"]
      },
      opinion: {
        opinion_count: 2,
        latest_direction: "BULLISH",
        latest_opinion_at: "2026-09-10T20:16:54Z",
        latest_opinion_id: "opinion-zijin-2"
      },
      thesis: {
        thesis_change_count: 2,
        latest_change_type: "THESIS_CHANGED",
        latest_change_at: "2026-09-10T20:16:54Z",
        latest_thesis_change_id: "thesis-zijin-2"
      },
      relationship: { has_attention: true, has_opinion: true, attention_only: false },
      latest_observed_at: "2026-09-10T20:16:54Z",
      traceability: {
        attention_occurrence_ids: ["attention-zijin-1"],
        raw_event_ids: ["raw-zijin-1"],
        opinion_ids: ["opinion-zijin-1", "opinion-zijin-2"],
        thesis_change_ids: ["thesis-zijin-1", "thesis-zijin-2"]
      }
    },
    {
      asset: { asset_id: "asset-gold-hk", name: "山东黄金", market: "HK", symbol: "01787" },
      attention: {
        occurrence_count: 2,
        first_observed_at: "2026-08-23T10:00:00Z",
        latest_observed_at: "2026-09-08T20:16:54Z",
        evidence_types: ["EXPLICIT_MENTION"]
      },
      opinion: {
        opinion_count: 1,
        latest_direction: "NEUTRAL",
        latest_opinion_at: "2026-09-08T20:16:54Z",
        latest_opinion_id: "opinion-gold-hk"
      },
      thesis: {
        thesis_change_count: 1,
        latest_change_type: "THESIS_REINFORCED",
        latest_change_at: "2026-09-08T20:16:54Z",
        latest_thesis_change_id: "thesis-gold-hk"
      },
      relationship: { has_attention: true, has_opinion: true, attention_only: false },
      latest_observed_at: "2026-09-08T20:16:54Z",
      traceability: {
        attention_occurrence_ids: ["attention-gold-hk"],
        raw_event_ids: ["raw-gold-hk"],
        opinion_ids: ["opinion-gold-hk"],
        thesis_change_ids: ["thesis-gold-hk"]
      }
    },
    {
      asset: { asset_id: "asset-gold-sh", name: "山东黄金", market: "SH", symbol: "600547" },
      attention: {
        occurrence_count: 1,
        first_observed_at: "2026-09-01T10:00:00Z",
        latest_observed_at: "2026-09-01T10:00:00Z",
        evidence_types: ["EXPLICIT_MENTION"]
      },
      opinion: {
        opinion_count: 0,
        latest_direction: null,
        latest_opinion_at: null,
        latest_opinion_id: null
      },
      thesis: {
        thesis_change_count: 0,
        latest_change_type: null,
        latest_change_at: null,
        latest_thesis_change_id: null
      },
      relationship: { has_attention: true, has_opinion: false, attention_only: true },
      latest_observed_at: "2026-09-01T10:00:00Z",
      traceability: {
        attention_occurrence_ids: ["attention-gold-sh"],
        raw_event_ids: ["raw-gold-sh"],
        opinion_ids: [],
        thesis_change_ids: []
      }
    }
  ],
  recent_activity: [
    {
      observed_at: "2026-08-22T10:00:00Z",
      event_type: "ATTENTION_OBSERVED",
      asset: { asset_id: "asset-zijin-sh", name: "紫金矿业", market: "SH", symbol: "601899" },
      source_refs: [["AttentionOccurrence", "attention-zijin-1"], ["RawEvent", "raw-zijin-1"]]
    },
    {
      observed_at: "2026-09-10T20:16:54Z",
      event_type: "THESIS_CHANGE_OBSERVED",
      asset: { asset_id: "asset-zijin-sh", name: "紫金矿业", market: "SH", symbol: "601899" },
      source_refs: [["ThesisChange", "thesis-zijin-2"], ["RawEvent", "raw-zijin-1"]]
    }
  ],
  data_quality: {
    historical_completeness: "UNKNOWN",
    historical_comparison_supported: false,
    absence_inference_supported: false,
    limitations: [
      "Historical completeness is UNKNOWN.",
      "Available collection provenance does not establish historical completeness.",
      "Historical comparison is unsupported.",
      "Absence inference is unsupported."
    ]
  },
  traceability_summary: {
    attention_occurrence_ref_count: 3,
    raw_event_ref_count: 3,
    opinion_ref_count: 3,
    thesis_change_ref_count: 3,
    activity_source_ref_count: 4
  }
};

const emptyInvestorProductPayload: InvestorProductView = {
  ...investorProductPayload,
  investor: {
    investor_id: "investor-empty",
    name: "Forever",
    source_platform: "xueqiu",
    source_user_id: "empty-investor"
  },
  summary: {
    observed_asset_count: 0,
    opinion_asset_count: 0,
    thesis_change_count: 0,
    attention_occurrence_count: 0,
    opinion_count: 0,
    latest_observed_at: null
  },
  coverage: { observed_assets: [], opinion_assets: [], attention_only_assets: [] },
  asset_views: [],
  recent_activity: [],
  traceability_summary: {
    attention_occurrence_ref_count: 0,
    raw_event_ref_count: 0,
    opinion_ref_count: 0,
    thesis_change_ref_count: 0,
    activity_source_ref_count: 0
  }
};

function mockApi(product: AssetIntelligenceView = productPayload) {
  return vi.fn().mockImplementation((input: RequestInfo | URL) => {
    const url = String(input);
    if (url === "/api/v1/intelligence/investors") {
      return Promise.resolve({ ok: true, status: 200, json: async () => investorList });
    }
    if (url.includes("/api/intelligence/investors/") && url.endsWith("/view")) {
      const payload = url.includes("investor-empty")
        ? emptyInvestorProductPayload
        : investorProductPayload;
      return Promise.resolve({ ok: true, status: 200, json: async () => payload });
    }
    if (url.includes("/api/intelligence/assets/") && url.endsWith("/view")) {
      const payload = url.includes("asset-hk-00883")
        ? cnoocProduct
        : url.includes("asset-sh-600519")
          ? moutaiProduct
          : product;
      return Promise.resolve({ ok: true, status: 200, json: async () => payload });
    }
    if (url.includes("/api/v1/intelligence/assets?")) {
      return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
    }
    return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
  });
}

beforeEach(() => {
  window.history.replaceState({}, "", "/assets/" + assetId);
  vi.restoreAllMocks();
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("Asset Intelligence Product View V0", () => {
  it("loads one unified Product View request for Asset Detail", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "招商轮船" })).toBeInTheDocument();
    expect(screen.getByText("REVIEW PRIORITY")).toBeInTheDocument();
    expect(screen.getByText("Immediate review")).toBeInTheDocument();
    expect(screen.getByText("Directional Alignment")).toBeInTheDocument();
    expect(screen.getByText("MIXED DIRECTION")).toBeInTheDocument();
    expect(screen.getByText("Consensus Evidence")).toBeInTheDocument();
    expect(screen.getByText("Recent Evolution")).toBeInTheDocument();
    expect(screen.getByText("Investor observed · Investor One")).toBeInTheDocument();
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/view"))
    ).toHaveLength(1);
    expect(fetchMock).not.toHaveBeenCalledWith(
      "/api/v1/intelligence/assets/" + assetId,
      expect.any(Object)
    );
  });

  it("keeps Discovery collection loading independent from Product View", async () => {
    window.history.replaceState({}, "", "/assets");
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);
    expect(await screen.findByRole("heading", { name: "Asset Discovery" })).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/view"))).toHaveLength(0);

    fireEvent.click(screen.getByRole("button", { name: "Open 招商轮船 SH:601872" }));
    expect(window.location.pathname).toBe("/assets/" + assetId);
    expect(await screen.findByText("REVIEW PRIORITY")).toBeInTheDocument();
    expect(fetchMock.mock.calls.filter(([input]) => String(input).endsWith("/view"))).toHaveLength(1);
  });

  it("keeps Alignment and Consensus visually independent for 贵州茅台", async () => {
    const fetchMock = mockApi(moutaiProduct);
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "贵州茅台" })).toBeInTheDocument();
    expect(screen.getByText("MIXED DIRECTION")).toBeInTheDocument();
    expect(screen.getByText("INSUFFICIENT EVIDENCE")).toBeInTheDocument();
    expect(screen.queryByText("DIVERGENT")).not.toBeInTheDocument();
  });

  it("shows historical Intelligence without Discovery for 中国海洋石油", async () => {
    const fetchMock = mockApi(cnoocProduct);
    window.history.replaceState({}, "", "/assets/asset-hk-00883");
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "中国海洋石油" })).toBeInTheDocument();
    expect(screen.getByText("Background monitoring")).toBeInTheDocument();
    expect(screen.getByText("Historical Intelligence is available.")).toBeInTheDocument();
    expect(screen.getByText("Feed lifecycle")).toBeInTheDocument();
    expect(screen.getByText("Event lifecycle")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE · 1")).toBeInTheDocument();
    expect(screen.getByText("ACTIVE here describes lifecycle/presentation state only. It does not mean investors are discussing this Asset now.")).toBeInTheDocument();
    expect(screen.queryByText("No Intelligence")).not.toBeInTheDocument();
  });

  it("handles Product View loading, network failure, and 404", async () => {
    let rejectRequest: ((reason?: unknown) => void) | undefined;
    const pending = new Promise<never>((_, reject) => {
      rejectRequest = reject;
    });
    vi.stubGlobal("fetch", vi.fn().mockReturnValue(pending));
    render(<App />);
    expect(screen.getByText("Syncing evidence…")).toBeInTheDocument();
    rejectRequest?.(new Error("backend unavailable"));
    await waitFor(() => expect(screen.getByText("API unavailable")).toBeInTheDocument());

    cleanup();
    window.history.replaceState({}, "", "/assets/" + assetId);
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        if (String(input).endsWith("/view")) {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({ detail: "asset intelligence view not found" })
          });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
      })
    );
    render(<App />);
    expect(await screen.findByText("No Asset Intelligence evidence")).toBeInTheDocument();
  });

  it("preserves listing identity in the Asset Detail route", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);
    expect(await screen.findByRole("heading", { name: "招商轮船" })).toBeInTheDocument();
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/intelligence/assets/" + assetId + "/view",
      expect.any(Object)
    );
  });

  it("loads one Investor Product View request without Investor-to-Asset Product View N+1", async () => {
    window.history.replaceState({}, "", "/investors/investor-life");
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    expect(await screen.findByRole("heading", { name: "纳履而去" })).toBeInTheDocument();
    expect(screen.getByText("Observed Attention is distinct from persisted Opinion.")).toBeInTheDocument();
    expect(screen.getByText("Attention-only assets")).toBeInTheDocument();
    expect(screen.getByText("BULLISH")).toBeInTheDocument();
    expect(screen.getAllByText("CHANGED").length).toBeGreaterThan(0);
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/intelligence/investors/investor-life/view")
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).includes("/api/intelligence/assets/") && String(input).endsWith("/view"))
    ).toHaveLength(0);
    expect(document.body.textContent).not.toMatch(/score|ranking|recommend|buy|sell/i);
  });

  it("keeps same-name A/H assets isolated by asset_id", async () => {
    window.history.replaceState({}, "", "/investors/investor-life");
    vi.stubGlobal("fetch", mockApi());

    render(<App />);

    expect(await screen.findByRole("heading", { name: "纳履而去" })).toBeInTheDocument();
    expect(screen.getAllByText("HK:01787").length).toBeGreaterThan(0);
    expect(screen.getAllByText("SH:600547").length).toBeGreaterThan(0);
    expect(screen.getAllByRole("link", { name: /山东黄金/ }).length).toBeGreaterThanOrEqual(2);
  });

  it("renders an unknown Investor as a read-only 404 state", async () => {
    window.history.replaceState({}, "", "/investors/unknown-investor");
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/intelligence/investors/unknown-investor/view") {
          return Promise.resolve({
            ok: false,
            status: 404,
            json: async () => ({ detail: "investor intelligence view not found" })
          });
        }
        if (url === "/api/v1/intelligence/investors") {
          return Promise.resolve({ ok: true, status: 200, json: async () => investorList });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
      })
    );

    render(<App />);

    expect(await screen.findByText("No observed Investor evidence")).toBeInTheDocument();
    expect(screen.queryByText("No Intelligence")).not.toBeInTheDocument();
  });

  it("navigates Asset to Investor by investor_id without prefetching another Asset view", async () => {
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const investorLink = await screen.findByRole("link", {
      name: "Open Investor Investor One"
    });
    expect(investorLink).toHaveAttribute("href", "/investors/investor-1");
    act(() => fireEvent.click(investorLink));
    expect(await screen.findByRole("heading", { name: "纳履而去" })).toBeInTheDocument();

    expect(window.location.pathname).toBe("/investors/investor-1");
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/intelligence/investors/investor-1/view")
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).includes("/api/intelligence/assets/") && String(input).endsWith("/view"))
    ).toHaveLength(1);
  });

  it("navigates Investor to Asset with an asset_id anchor and supports back route state", async () => {
    window.history.replaceState({}, "", "/investors/investor-life");
    const fetchMock = mockApi();
    vi.stubGlobal("fetch", fetchMock);

    render(<App />);

    const assetLinks = await screen.findAllByRole("link", {
      name: "Open Asset 紫金矿业 SH:601899"
    });
    expect(assetLinks[0]).toHaveAttribute("href", "/assets/asset-zijin-sh");
    act(() => fireEvent.click(assetLinks[0]));
    expect(await screen.findByRole("heading", { name: "招商轮船" })).toBeInTheDocument();

    expect(window.location.pathname).toBe("/assets/asset-zijin-sh");
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input) === "/api/intelligence/assets/asset-zijin-sh/view")
    ).toHaveLength(1);
    expect(
      fetchMock.mock.calls.filter(([input]) => String(input).includes("/api/intelligence/investors/") && String(input).endsWith("/view"))
    ).toHaveLength(1);

    act(() => {
      window.history.pushState({}, "", "/investors/investor-life");
      window.dispatchEvent(new PopStateEvent("popstate"));
    });
    expect(await screen.findByRole("heading", { name: "纳履而去" })).toBeInTheDocument();
  });

  it("renders an existing empty Investor as collected-records empty state", async () => {
    window.history.replaceState({}, "", "/investors/investor-empty");
    vi.stubGlobal("fetch", mockApi());

    render(<App />);

    expect(await screen.findByRole("heading", { name: "Forever" })).toBeInTheDocument();
    expect(screen.getByText("No intelligence evidence is available for this Investor in the currently collected records.")).toBeInTheDocument();
    expect(screen.getByText("Historical completeness is UNKNOWN; this state does not establish historical absence.")).toBeInTheDocument();
    expect(screen.queryByText("No investor")).not.toBeInTheDocument();
    expect(screen.queryByText("API unavailable")).not.toBeInTheDocument();
  });

  it("falls back to a short Investor ID when the catalog cannot resolve a name", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation((input: RequestInfo | URL) => {
        const url = String(input);
        if (url === "/api/v1/intelligence/investors") {
          return Promise.resolve({ ok: true, status: 200, json: async () => ({ items: [], total: 0 }) });
        }
        if (url.includes("/api/intelligence/assets/") && url.endsWith("/view")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => productPayload });
        }
        if (url.includes("/api/v1/intelligence/assets?")) {
          return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
        }
        return Promise.resolve({ ok: true, status: 200, json: async () => listPayload });
      })
    );

    render(<App />);

    const fallbackLinks = await screen.findAllByRole("link", { name: /Open Investor Investor ID investor/ });
    expect(fallbackLinks.some((link) => link.getAttribute("href") === "/investors/investor-1")).toBe(true);
  });
});
