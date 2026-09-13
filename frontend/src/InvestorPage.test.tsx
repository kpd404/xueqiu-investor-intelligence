import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestorDetailPage, InvestorDiscoveryPage } from "./InvestorPage";
import type {
  InvestorAssetIntelligenceSummary,
  InvestorIntelligenceView,
  InvestorListItem
} from "./types";

const investorList: InvestorListItem[] = [
  {
    investor_id: "investor-life",
    investor_name: "人生是历练",
    attention_asset_count: 12,
    opinion_asset_count: 11,
    repeated_opinion_asset_count: 5,
    latest_observed_evidence_time: "2026-09-11T13:09:00Z",
    completeness: "UNKNOWN"
  },
  {
    investor_id: "investor-love",
    investor_name: "爱投资的小人书",
    attention_asset_count: 9,
    opinion_asset_count: 7,
    repeated_opinion_asset_count: 6,
    latest_observed_evidence_time: "2026-09-10T13:09:00Z",
    completeness: "UNKNOWN"
  }
];

const assetBase: InvestorAssetIntelligenceSummary = {
  asset_id: "asset-gold-hk",
  asset_name: "山东黄金",
  market: "HK",
  symbol: "01787",
  attention_occurrence_count: 4,
  first_attention_time: "2026-08-27T10:16:06Z",
  latest_attention_time: "2026-09-09T13:09:00Z",
  attention_evidence_types: ["OPINION", "EXPLICIT_MENTION"],
  opinion_count: 4,
  first_opinion_time: "2026-08-28T13:09:00Z",
  latest_opinion_time: "2026-09-10T13:09:00Z",
  latest_observed_direction: "BULLISH",
  thesis_change_count: 4,
  changed_count: 2,
  extended_count: 1,
  reversal_count: 1,
  missing_thesis_comparison_count: 0,
  attention_investor_count: 2,
  opinion_investor_count: 2,
  shared_attention_investor_count: 1,
  shared_opinion_investor_count: 1,
  latest_evidence_time: "2026-09-10T13:09:00Z",
  alignment: "ALIGNED_BULLISH",
  consensus: "INSUFFICIENT_EVIDENCE"
};

const assetViews: InvestorAssetIntelligenceSummary[] = [
  assetBase,
  {
    ...assetBase,
    asset_id: "asset-gold-sh",
    market: "SH",
    symbol: "600547",
    attention_occurrence_count: 1,
    first_attention_time: "2026-09-01T13:09:00Z",
    latest_attention_time: "2026-09-01T13:09:00Z",
    attention_evidence_types: ["REPOST"],
    opinion_count: 0,
    first_opinion_time: null,
    latest_opinion_time: null,
    latest_observed_direction: null,
    thesis_change_count: 0,
    changed_count: 0,
    extended_count: 0,
    reversal_count: 0,
    attention_investor_count: 3,
    opinion_investor_count: 1,
    shared_attention_investor_count: 2,
    shared_opinion_investor_count: 1,
    latest_evidence_time: "2026-09-01T13:09:00Z",
    alignment: "INSUFFICIENT_EVIDENCE",
    consensus: "INSUFFICIENT_EVIDENCE"
  },
  {
    ...assetBase,
    asset_id: "asset-huaneng",
    asset_name: "华能国际",
    market: "HK",
    symbol: "00902",
    attention_occurrence_count: 2,
    first_attention_time: "2026-09-02T13:09:00Z",
    latest_attention_time: "2026-09-08T13:09:00Z",
    opinion_count: 6,
    first_opinion_time: "2026-09-02T13:09:00Z",
    latest_opinion_time: "2026-09-08T13:09:00Z",
    latest_observed_direction: "BEARISH",
    thesis_change_count: 6,
    changed_count: 3,
    extended_count: 2,
    reversal_count: 1,
    attention_investor_count: 2,
    opinion_investor_count: 2,
    shared_attention_investor_count: 1,
    shared_opinion_investor_count: 1,
    latest_evidence_time: "2026-09-08T13:09:00Z",
    alignment: "MIXED_DIRECTION",
    consensus: "INSUFFICIENT_EVIDENCE"
  },
  {
    ...assetBase,
    asset_id: "asset-datang",
    asset_name: "大唐发电",
    market: "HK",
    symbol: "00991",
    attention_occurrence_count: 1,
    first_attention_time: "2026-09-03T13:09:00Z",
    latest_attention_time: "2026-09-07T13:09:00Z",
    opinion_count: 14,
    first_opinion_time: "2026-09-03T13:09:00Z",
    latest_opinion_time: "2026-09-07T13:09:00Z",
    thesis_change_count: 13,
    changed_count: 4,
    extended_count: 2,
    reversal_count: 0,
    missing_thesis_comparison_count: 1,
    attention_investor_count: 1,
    opinion_investor_count: 1,
    shared_attention_investor_count: 0,
    shared_opinion_investor_count: 0,
    latest_evidence_time: "2026-09-07T13:09:00Z",
    alignment: null,
    consensus: null
  }
];

const detail: InvestorIntelligenceView = {
  investor_id: "investor-life",
  investor_name: "人生是历练",
  window_start: "2026-08-27T10:16:06Z",
  window_end: "2026-09-11T13:09:00Z",
  completeness: "UNKNOWN",
  first_observed_evidence_time: "2026-08-27T10:16:06Z",
  latest_observed_evidence_time: "2026-09-10T13:09:00Z",
  attention_asset_count: 4,
  opinion_asset_count: 3,
  repeated_opinion_asset_count: 3,
  thesis_changed_asset_count: 3,
  direction_reversal_asset_count: 2,
  shared_attention_asset_count: 3,
  shared_opinion_asset_count: 2,
  asset_views: assetViews,
  overlap_summaries: [
    {
      other_investor_id: "investor-shen",
      other_investor_name: "沈阳城",
      shared_attention_asset_count: 3,
      shared_opinion_asset_count: 2
    },
    {
      other_investor_id: "investor-captain",
      other_investor_name: "Captain-Nemo船长",
      shared_attention_asset_count: 1,
      shared_opinion_asset_count: 1
    }
  ],
  data_quality: {
    completeness: "UNKNOWN",
    absence_inference_supported: false,
    collection_provenance_available: false,
    opinion_coverage: "PARTIAL",
    missing_thesis_comparison_count: 1,
    cross_investor_lineage_available: true,
    limitations: [
      "HISTORICAL_COMPLETENESS_UNKNOWN",
      "ABSENCE_INFERENCE_UNSUPPORTED",
      "COLLECTION_PROVENANCE_UNAVAILABLE",
      "LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY",
      "MISSING_THESIS_COMPARISON"
    ]
  }
};

afterEach(cleanup);

function renderInvestorDiscoveryHarness(initialQuery = "") {
  const onOpen = vi.fn();
  const onQuery = vi.fn();
  function Harness() {
    const [queryString, setQueryString] = useState(initialQuery);
    return (
      <InvestorDiscoveryPage
        investors={investorList}
        loading={false}
        error={null}
        queryString={queryString}
        onOpenInvestor={onOpen}
        onQueryChange={(value) => {
          onQuery(value);
          setQueryString(value);
        }}
      />
    );
  }
  render(<Harness />);
  return { onOpen, onQuery };
}

function renderInvestorDetailHarness(initialQuery = "") {
  const onAsset = vi.fn();
  const onInvestor = vi.fn();
  const onQuery = vi.fn();
  function Harness() {
    const [queryString, setQueryString] = useState(initialQuery);
    return (
      <InvestorDetailPage
        view={detail}
        queryString={queryString}
        onOpenAsset={onAsset}
        onOpenInvestor={onInvestor}
        onQueryChange={(value) => {
          onQuery(value);
          setQueryString(value);
        }}
      />
    );
  }
  render(<Harness />);
  return { onAsset, onInvestor, onQuery };
}

describe("Investor Intelligence V0", () => {
  it("loads the selector, searches Investors, and opens the selected view", () => {
    const { onOpen, onQuery } = renderInvestorDiscoveryHarness();

    expect(screen.getByRole("heading", { name: "Investor Intelligence" })).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "Search Investor name" }), {
      target: { value: "爱投资" }
    });
    expect(screen.getByRole("button", { name: "Open Investor 爱投资的小人书" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open Investor 人生是历练" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Open Investor 爱投资的小人书" }));
    expect(onOpen).toHaveBeenCalledWith("investor-love");
    expect(onQuery).toHaveBeenCalledWith("q=%E7%88%B1%E6%8A%95%E8%B5%84");
  });

  it("renders breadth, Asset evidence, Thesis gap, and listing identity", () => {
    const onAsset = vi.fn();
    render(
      <InvestorDetailPage
        view={detail}
        queryString=""
        onOpenAsset={onAsset}
        onOpenInvestor={vi.fn()}
        onQueryChange={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "人生是历练" })).toBeInTheDocument();
    expect(screen.getAllByText("Historical completeness: UNKNOWN").length).toBeGreaterThan(0);
    expect(document.querySelector(".investor-breadth-content")).toHaveTextContent("4 Assets");
    expect(document.querySelector(".investor-breadth-content")).toHaveTextContent("3 Assets");
    expect(screen.getByRole("button", { name: "Open Asset 山东黄金 HK:01787" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open Asset 山东黄金 SH:600547" })).toBeInTheDocument();
    expect(screen.getByText("1 comparison unavailable")).toBeInTheDocument();
    expect(screen.getAllByText("BULLISH").length).toBeGreaterThan(0);
    expect(document.body.textContent).not.toContain("Current belief");
    fireEvent.click(screen.getByRole("button", { name: "Open Asset 山东黄金 HK:01787" }));
    expect(onAsset).toHaveBeenCalledWith("asset-gold-hk");
  });

  it("supports Asset filters, sorting, overlap sorting, and URL state", () => {
    const { onQuery } = renderInvestorDetailHarness();

    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "opinion" } });
    expect(screen.queryByRole("button", { name: "Open Asset 山东黄金 SH:600547" })).not.toBeInTheDocument();
    expect(onQuery).toHaveBeenCalledWith("filter=opinion");
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "attention" } });
    expect(screen.getByRole("button", { name: "Open Asset 山东黄金 SH:600547" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "repeated" } });
    expect(screen.getByRole("button", { name: "Open Asset 大唐发电 HK:00991" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "changed" } });
    expect(screen.getByRole("button", { name: "Open Asset 大唐发电 HK:00991" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "shared_attention" } });
    expect(screen.getByRole("button", { name: "Open Asset 山东黄金 SH:600547" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "reversal" } });
    expect(screen.getByRole("button", { name: "Open Asset 山东黄金 HK:01787" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "opinion" } });
    expect(onQuery).toHaveBeenCalledWith("filter=reversal&sort=opinion");
    fireEvent.change(screen.getByLabelText("Filter"), { target: { value: "shared_opinion" } });
    expect(screen.getByRole("button", { name: "Open Asset 山东黄金 HK:01787" })).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "latest" } });
    fireEvent.change(screen.getByLabelText("Overlap sort"), { target: { value: "attention" } });
    expect(onQuery).toHaveBeenCalledWith("filter=shared_opinion&overlap_sort=attention");
    expect(screen.getByRole("button", { name: "Open Investor 沈阳城" })).toBeInTheDocument();
  });

  it("renders loading, 404/error states, and never invents current holdings", () => {
    render(
      <InvestorDiscoveryPage
        investors={[]}
        loading={true}
        error={null}
        queryString=""
        onOpenInvestor={vi.fn()}
        onQueryChange={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Loading Investor Intelligence")).toBeInTheDocument();

    cleanup();
    render(
      <InvestorDiscoveryPage
        investors={[]}
        loading={false}
        error={new Error("offline")}
        queryString=""
        onOpenInvestor={vi.fn()}
        onQueryChange={vi.fn()}
      />
    );
    expect(screen.getByText("API unavailable")).toBeInTheDocument();
    expect(screen.queryByText("Current holdings")).not.toBeInTheDocument();
  });
});
