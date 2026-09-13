import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./OverviewPage";
import type { AssetListItem } from "./types";

const baseAsset: AssetListItem = {
  asset_id: "asset-dragon",
  asset_name: "龙源电力",
  market: "HK",
  symbol: "00916",
  attention_investor_count: 3,
  attention_occurrence_count: 5,
  opinion_investor_count: 3,
  opinion_count: 5,
  earliest_observed_time: "2026-08-27T10:16:06Z",
  latest_evidence_time: "2026-09-10T20:16:54Z",
  temporal_span_days: 13.42,
  thesis_change_count: 5,
  has_repeated_thesis: false,
  has_thesis_changed: true,
  has_direction_reversal: true,
  attention_opinion_gap: false,
  latest_alignment: "MIXED_DIRECTION",
  latest_consensus: "DIVERGENT",
  completeness: "UNKNOWN",
  data_quality_flags: ["HISTORICAL_COMPLETENESS_UNKNOWN"]
};

const assets: AssetListItem[] = [
  baseAsset,
  {
    ...baseAsset,
    asset_id: "asset-huaneng",
    asset_name: "华能国际",
    market: "HK",
    symbol: "00902",
    attention_investor_count: 2,
    attention_occurrence_count: 18,
    opinion_investor_count: 2,
    opinion_count: 18,
    latest_evidence_time: "2026-09-09T20:16:54Z",
    has_repeated_thesis: true,
    latest_consensus: "INSUFFICIENT_EVIDENCE"
  },
  {
    ...baseAsset,
    asset_id: "asset-moutai",
    asset_name: "贵州茅台",
    market: "SH",
    symbol: "600519",
    attention_investor_count: 3,
    opinion_investor_count: 1,
    opinion_count: 3,
    latest_evidence_time: "2026-09-08T20:16:54Z",
    has_repeated_thesis: true,
    has_thesis_changed: false,
    has_direction_reversal: false,
    attention_opinion_gap: true,
    latest_alignment: "INSUFFICIENT_EVIDENCE",
    latest_consensus: "INSUFFICIENT_EVIDENCE"
  },
  {
    ...baseAsset,
    asset_id: "asset-gold-hk",
    asset_name: "山东黄金",
    market: "HK",
    symbol: "01787",
    attention_investor_count: 2,
    opinion_investor_count: 2,
    opinion_count: 13,
    latest_evidence_time: "2026-09-07T20:16:54Z",
    has_repeated_thesis: true,
    attention_opinion_gap: false,
    latest_alignment: "ALIGNED_BULLISH",
    latest_consensus: "INSUFFICIENT_EVIDENCE"
  },
  {
    ...baseAsset,
    asset_id: "asset-gold-sh",
    asset_name: "山东黄金",
    market: "SH",
    symbol: "600547",
    attention_investor_count: 3,
    opinion_investor_count: 1,
    opinion_count: 1,
    latest_evidence_time: "2026-09-06T20:16:54Z",
    has_repeated_thesis: false,
    has_thesis_changed: false,
    has_direction_reversal: false,
    attention_opinion_gap: true,
    latest_alignment: "INSUFFICIENT_EVIDENCE",
    latest_consensus: "INSUFFICIENT_EVIDENCE"
  },
  {
    ...baseAsset,
    asset_id: "asset-datang",
    asset_name: "大唐发电",
    market: "HK",
    symbol: "00991",
    attention_investor_count: 1,
    opinion_investor_count: 1,
    opinion_count: 14,
    latest_evidence_time: "2026-09-05T20:16:54Z",
    has_repeated_thesis: true,
    has_direction_reversal: false,
    attention_opinion_gap: false,
    data_quality_flags: ["HISTORICAL_COMPLETENESS_UNKNOWN", "MISSING_THESIS_COMPARISON"]
  }
];

afterEach(cleanup);

describe("Observed Intelligence Overview V0", () => {
  it("loads universe facts, patterns, latest observed ordering, and data boundary", () => {
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
      />
    );

    expect(screen.getByRole("heading", { name: "Observed Intelligence Overview" })).toBeInTheDocument();
    expect(screen.getByText("Historical completeness: UNKNOWN")).toBeInTheDocument();
    expect(document.querySelector(".overview-summary")).toHaveTextContent("6");
    expect(screen.getAllByText("More monitored Investors have Attention evidence than structured Opinion evidence.").length).toBeGreaterThan(0);
    expect(screen.queryByText("presence/order evidence supported", { exact: false })).not.toBeInTheDocument();
    const latestRows = Array.from(document.querySelectorAll(".latest-rows .overview-asset-row"));
    expect(latestRows[0]).toHaveTextContent("龙源电力");
    expect(screen.getAllByRole("button", { name: "Open 龙源电力 HK:00916" }).length).toBeGreaterThan(0);
  });

  it("links evidence patterns to Discovery and Assets to detail", () => {
    const onOpenAsset = vi.fn();
    const onOpenDiscovery = vi.fn();
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={onOpenAsset}
        onOpenDiscovery={onOpenDiscovery}
      />
    );

    fireEvent.click(screen.getByRole("button", { name: "Explore Shared Attention" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("attention=2");
    fireEvent.click(screen.getByRole("button", { name: "Explore Direction Disagreement" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("cross=disagreement");
    fireEvent.click(screen.getByRole("button", { name: "Explore Attention > Opinion" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("gap=attention_gt_opinion");
    fireEvent.click(screen.getByRole("button", { name: "Explore Repeated Thesis" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("thesis=repeated");

    fireEvent.click(screen.getAllByRole("button", { name: "Open 龙源电力 HK:00916" })[0]);
    expect(onOpenAsset).toHaveBeenCalledWith("asset-dragon");
    fireEvent.click(screen.getAllByRole("button", { name: /大唐发电.*HK:00991/ })[0]);
    expect(onOpenAsset).toHaveBeenCalledWith("asset-datang");
  });

  it("keeps DIVERGENT, Attention > Opinion, and missing comparison facts explicit", () => {
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
      />
    );

    expect(screen.getAllByText("DIVERGENT").length).toBeGreaterThan(0);
    expect(screen.getAllByText("ATTENTION > OPINION").length).toBeGreaterThan(0);
    expect(screen.getByText("Missing Thesis Comparison · 1")).toBeInTheDocument();
    const body = document.body.textContent?.toLowerCase() ?? "";
    for (const prohibited of ["trending", "hot", "rising", "cooling", "momentum", "most important", "best idea", "opportunity", "recommended"]) {
      expect(body).not.toContain(prohibited);
    }
  });

  it("renders loading and API error states without inventing evidence", () => {
    render(
      <OverviewPage
        assets={[]}
        loading={true}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
      />
    );
    expect(screen.getByLabelText("Loading Observed Intelligence Overview")).toBeInTheDocument();

    cleanup();
    render(
      <OverviewPage
        assets={[]}
        loading={false}
        error={new Error("offline")}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
      />
    );
    expect(screen.getByText("API unavailable")).toBeInTheDocument();
    expect(screen.queryByText("No interest")).not.toBeInTheDocument();
  });
});
