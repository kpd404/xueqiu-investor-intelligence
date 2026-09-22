import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { OverviewPage } from "./OverviewPage";
import type { AssetListItem, IntelligenceFeedItem, OperationalStatusResponse } from "./types";

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

const recentItem: IntelligenceFeedItem = {
  id: "feed-1",
  priority_id: "priority-1",
  asset: {
    asset_id: "asset-dragon",
    name: "龙源电力",
    market: "HK",
    symbol: "00916"
  },
  event_type: "ASSET_ACTIVITY_SPIKE",
  priority_level: "HIGH",
  reason: "MULTI_INVESTOR_ATTENTION",
  title: "Multiple investors started paying attention",
  context: { investor_count: 2, signal_count: 3, source_count: 3 },
  investors: [
    { investor_id: "investor-a", name: "Investor A" },
    { investor_id: "investor-b", name: "Investor B" }
  ],
  state: "ACTIVE",
  observed_at: "2026-09-20T08:00:00Z",
  created_at: "2026-09-20T08:01:00Z"
};

const healthyStatus: OperationalStatusResponse = {
  status: "HEALTHY",
  freshness: "FRESH",
  freshness_age_seconds: 600,
  last_refresh_started_at: "2026-09-20T08:00:00Z",
  last_refresh_finished_at: "2026-09-20T08:01:00Z",
  last_successful_refresh_at: "2026-09-20T08:01:00Z",
  latest_status: "SUCCESS",
  latest_trigger: "SCHEDULED",
  latest_failure_stage: null,
  latest_failure_code: null,
  next_expected_refresh_at: "2026-09-20T09:01:00Z",
  cdp_requirement: "AUTHENTICATED_EDGE_CDP_REQUIRED"
};

afterEach(cleanup);

describe("已观察情报概览 V0", () => {
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

    expect(screen.getByRole("heading", { name: "已观察情报概览" })).toBeInTheDocument();
    expect(screen.getByText("历史完整性：未知")).toBeInTheDocument();
    expect(document.querySelector(".overview-summary")).toHaveTextContent("6");
    expect(screen.getAllByText("关注动态覆盖的受监测投资者多于形成结构化观点的投资者。").length).toBeGreaterThan(0);
    expect(screen.queryByText("presence/order evidence supported", { exact: false })).not.toBeInTheDocument();
    const latestRows = Array.from(document.querySelectorAll(".latest-rows .overview-asset-row"));
    expect(latestRows[0]).toHaveTextContent("龙源电力");
    expect(screen.getAllByRole("button", { name: "打开 龙源电力 HK:00916" }).length).toBeGreaterThan(0);
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

    fireEvent.click(screen.getByRole("button", { name: "查看 共同关注" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("attention=2");
    fireEvent.click(screen.getByRole("button", { name: "前往标的发现 →" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("cross=disagreement");
    fireEvent.click(screen.getByRole("button", { name: "查看全部关注动态 > 观点 →" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("gap=attention_gt_opinion");
    fireEvent.click(screen.getByRole("button", { name: "查看重复投资逻辑 →" }));
    expect(onOpenDiscovery).toHaveBeenCalledWith("thesis=repeated");

    fireEvent.click(screen.getAllByRole("button", { name: "打开 龙源电力 HK:00916" })[0]);
    expect(onOpenAsset).toHaveBeenCalledWith("asset-dragon");
    fireEvent.click(screen.getAllByRole("button", { name: /大唐发电.*HK:00991/ })[0]);
    expect(onOpenAsset).toHaveBeenCalledWith("asset-datang");
  });

  it("keeps 观点分化, 关注动态 > 观点, and missing comparison facts explicit", () => {
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
      />
    );

    expect(screen.getAllByText("观点分化").length).toBeGreaterThan(0);
    expect(screen.getAllByText("关注动态 > 观点").length).toBeGreaterThan(0);
    expect(screen.getByText("缺少投资逻辑对比 · 1")).toBeInTheDocument();
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
    expect(screen.getByLabelText("正在加载已观察情报概览")).toBeInTheDocument();

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
    expect(screen.getByText("API 暂不可用")).toBeInTheDocument();
    expect(screen.queryByText("No interest")).not.toBeInTheDocument();
  });

  it("surfaces recent FeedItem facts with Asset and Investor navigation", () => {
    const onOpenAsset = vi.fn();
    const onOpenInvestor = vi.fn();
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={onOpenAsset}
        onOpenDiscovery={vi.fn()}
        onOpenInvestor={onOpenInvestor}
        recentItems={[recentItem]}
        recentLoading={false}
        recentError={null}
        operationalStatus={healthyStatus}
      />
    );

    expect(screen.getByRole("heading", { name: "近期投资情报" })).toBeInTheDocument();
    expect(screen.getByText("多位投资者关注了该标的")).toBeInTheDocument();
    expect(screen.getByText("高级复核优先级")).toBeInTheDocument();
    expect(
      within(screen.getByRole("region", { name: "近期投资情报" })).queryByText(
        /investment rating|score|buy/i
      )
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("link", { name: /龙源电力.*HK:00916/ }));
    fireEvent.click(screen.getByRole("link", { name: "Investor A" }));
    expect(onOpenAsset).toHaveBeenCalledWith("asset-dragon");
    expect(onOpenInvestor).toHaveBeenCalledWith("investor-a");
  });

  it("uses safe empty wording when no recent intelligence is surfaced", () => {
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
        recentItems={[]}
        recentLoading={false}
        recentError={null}
        operationalStatus={healthyStatus}
      />
    );

    expect(
      screen.getByText("近期窗口暂无已呈现的投资情报。")
    ).toBeInTheDocument();
    expect(screen.queryByText(/No investor activity|Nothing happened today/i)).not.toBeInTheDocument();
  });

  it("keeps recent intelligence visible while warning about stale data", () => {
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
        recentItems={[recentItem]}
        recentLoading={false}
        recentError={null}
        operationalStatus={{ ...healthyStatus, status: "STALE", freshness: "STALE" }}
      />
    );

    expect(screen.getByText("数据可能较旧；当前展示最近可用情报。")).toBeInTheDocument();
    expect(screen.getByText("多位投资者关注了该标的")).toBeInTheDocument();
  });

  it("separates Feed API failure from refresh failure", () => {
    render(
      <OverviewPage
        assets={assets}
        loading={false}
        error={null}
        onOpenAsset={vi.fn()}
        onOpenDiscovery={vi.fn()}
        recentItems={[]}
        recentLoading={false}
        recentError={new Error("feed unavailable")}
        operationalStatus={healthyStatus}
      />
    );

    expect(screen.getByText("近期投资情报暂不可用。")).toBeInTheDocument();
    expect(screen.queryByText("feed unavailable")).not.toBeInTheDocument();
  });
});
