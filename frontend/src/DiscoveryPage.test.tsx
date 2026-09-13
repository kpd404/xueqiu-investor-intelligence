import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DiscoveryPage } from "./DiscoveryPage";
import type { AssetListItem } from "./types";

const baseAsset: AssetListItem = {
  asset_id: "asset-1",
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
  has_repeated_thesis: true,
  has_thesis_changed: true,
  has_direction_reversal: false,
  attention_opinion_gap: false,
  latest_alignment: "MIXED_DIRECTION",
  latest_consensus: "MIXED_WITH_NEUTRAL",
  completeness: "UNKNOWN",
  data_quality_flags: ["HISTORICAL_COMPLETENESS_UNKNOWN"]
};

const assets: AssetListItem[] = [
  baseAsset,
  {
    ...baseAsset,
    asset_id: "asset-hk-01787",
    asset_name: "山东黄金",
    market: "HK",
    symbol: "01787",
    attention_investor_count: 2,
    attention_occurrence_count: 16,
    opinion_investor_count: 2,
    opinion_count: 13,
    latest_alignment: "ALIGNED_BULLISH",
    latest_consensus: "INSUFFICIENT_EVIDENCE",
    has_direction_reversal: true,
    attention_opinion_gap: false
  },
  {
    ...baseAsset,
    asset_id: "asset-sh-600547",
    asset_name: "山东黄金",
    market: "SH",
    symbol: "600547",
    attention_investor_count: 3,
    attention_occurrence_count: 6,
    opinion_investor_count: 1,
    opinion_count: 1,
    latest_alignment: "INSUFFICIENT_EVIDENCE",
    latest_consensus: "INSUFFICIENT_EVIDENCE",
    has_repeated_thesis: false,
    has_thesis_changed: false,
    has_direction_reversal: false,
    attention_opinion_gap: true
  },
  {
    ...baseAsset,
    asset_id: "asset-hk-00916",
    asset_name: "龙源电力",
    market: "HK",
    symbol: "00916",
    attention_investor_count: 3,
    attention_occurrence_count: 5,
    opinion_investor_count: 3,
    opinion_count: 5,
    latest_alignment: "MIXED_DIRECTION",
    latest_consensus: "DIVERGENT",
    has_repeated_thesis: false,
    has_direction_reversal: true,
    attention_opinion_gap: false
  },
  {
    ...baseAsset,
    asset_id: "asset-hk-00902",
    asset_name: "华能国际",
    market: "HK",
    symbol: "00902",
    attention_investor_count: 2,
    attention_occurrence_count: 18,
    opinion_investor_count: 2,
    opinion_count: 18,
    latest_alignment: "MIXED_DIRECTION",
    latest_consensus: "INSUFFICIENT_EVIDENCE",
    has_direction_reversal: true,
    attention_opinion_gap: false
  },
  {
    ...baseAsset,
    asset_id: "asset-sh-600519",
    asset_name: "贵州茅台",
    market: "SH",
    symbol: "600519",
    attention_investor_count: 3,
    attention_occurrence_count: 9,
    opinion_investor_count: 1,
    opinion_count: 3,
    latest_alignment: "INSUFFICIENT_EVIDENCE",
    latest_consensus: "INSUFFICIENT_EVIDENCE",
    has_repeated_thesis: true,
    attention_opinion_gap: true
  }
];

function renderHarness(initialSearch = "") {
  const onOpenAsset = vi.fn();
  function Harness() {
    const [queryString, setQueryString] = useState(initialSearch);
    return (
      <DiscoveryPage
        assets={assets}
        loading={false}
        error={null}
        queryString={queryString}
        onOpenAsset={onOpenAsset}
        onQueryChange={setQueryString}
      />
    );
  }
  render(<Harness />);
  return onOpenAsset;
}

afterEach(() => {
  cleanup();
});

describe("Asset Discovery V0", () => {
  it("renders observed Assets and keeps the default order name-based", () => {
    renderHarness();

    expect(screen.getByRole("heading", { name: "Asset Discovery" })).toBeInTheDocument();
    expect(document.querySelector(".discovery-result-bar")).toHaveTextContent("6");
    expect(document.querySelector(".discovery-result-bar > div:first-child span")).toHaveTextContent(
      "observed Assets"
    );
    expect(screen.getByRole("heading", { name: "招商轮船" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open 招商轮船 SH:601872" })).toBeInTheDocument();
    expect(screen.getByText("Historical completeness: UNKNOWN")).toBeInTheDocument();
  });

  it("searches by name and symbol while keeping A/H listings separate", () => {
    renderHarness();
    const search = screen.getByRole("searchbox", { name: "Search observed Assets" });

    fireEvent.change(search, { target: { value: "山东黄金" } });
    expect(screen.getAllByRole("heading", { name: "山东黄金" })).toHaveLength(2);
    expect(screen.getByRole("button", { name: "Open 山东黄金 HK:01787" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open 山东黄金 SH:600547" })).toBeInTheDocument();

    fireEvent.change(search, { target: { value: "600547" } });
    expect(screen.getByRole("button", { name: "Open 山东黄金 SH:600547" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Open 山东黄金 HK:01787" })).not.toBeInTheDocument();
  });

  it("supports market, breadth, disagreement, gap, and thesis filters", () => {
    renderHarness();

    fireEvent.change(screen.getByLabelText("Market"), { target: { value: "HK" } });
    expect(screen.queryByRole("button", { name: "Open 招商轮船 SH:601872" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open 龙源电力 HK:00916" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.change(screen.getByLabelText("Attention breadth"), { target: { value: "3" } });
    expect(screen.getByRole("button", { name: "Open 龙源电力 HK:00916" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open 山东黄金 SH:600547" })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Direction Disagreement" }));
    expect(screen.getByText("DIVERGENT")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.click(screen.getByRole("button", { name: "Attention > Opinion" }));
    expect(screen.getByRole("button", { name: "Open 山东黄金 SH:600547" })).toBeInTheDocument();
    expect(screen.getByText("贵州茅台")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "All" }));
    fireEvent.click(screen.getByRole("button", { name: "Repeated Thesis" }));
    expect(screen.getAllByText("REPEATED THESIS").length).toBeGreaterThan(0);
  });

  it("sorts by a selected observed fact and navigates to detail", () => {
    const onOpenAsset = renderHarness();
    fireEvent.change(screen.getByLabelText("Sort by"), { target: { value: "attention" } });

    const headings = screen.getAllByRole("heading", { level: 2 });
    expect(headings[0]).toHaveTextContent("招商轮船");

    fireEvent.click(screen.getByRole("button", { name: "Open 龙源电力 HK:00916" }));
    expect(onOpenAsset).toHaveBeenCalledWith("asset-hk-00916");
  });

  it("shows zero results, invalid URL values, loading, and API error states", () => {
    renderHarness("?market=NOPE&page=bad");
    expect(screen.getByRole("status")).toHaveTextContent("invalid");

    fireEvent.change(screen.getByRole("searchbox", { name: "Search observed Assets" }), {
      target: { value: "not-an-asset" }
    });
    expect(screen.getByText("No assets match these evidence filters.")).toBeInTheDocument();

    const { unmount } = render(
      <DiscoveryPage
        assets={[]}
        loading={true}
        error={null}
        queryString=""
        onOpenAsset={vi.fn()}
        onQueryChange={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Loading Asset Discovery")).toBeInTheDocument();
    unmount();

    render(
      <DiscoveryPage
        assets={[]}
        loading={false}
        error={new Error("offline")}
        queryString=""
        onOpenAsset={vi.fn()}
        onQueryChange={vi.fn()}
      />
    );
    expect(screen.getByText("API unavailable")).toBeInTheDocument();
  });
});
