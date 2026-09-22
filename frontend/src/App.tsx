import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  getAssetIntelligenceView,
  getAssetList,
  getInvestorIntelligenceView,
  getInvestorList,
  getRecentIntelligence,
  getOperationalStatus
} from "./api";
import { AssetProductViewPage } from "./AssetProductViewPage";
import { DiscoveryPage } from "./DiscoveryPage";
import { InvestorProductViewPage } from "./InvestorProductViewPage";
import { InvestorDiscoveryPage } from "./InvestorPage";
import { OverviewPage } from "./OverviewPage";
import type {
  AssetListItem,
  AssetIntelligenceView,
  AttentionObservation,
  CombinedAssetView,
  Direction,
  InvestorProductView,
  InvestorListItem,
  InvestorView,
  IntelligenceFeedItem,
  OperationalStatusResponse,
  TimelineEvent,
  TimelineResponse
} from "./types";
import {
  directionClass,
  directionLabel,
  evidenceLabel,
  eventLabel,
  filterAssets,
  formatEnum,
  formatLag,
  formatTime,
  limitationLabel,
  shortId,
  thesisLabel
} from "./presentation";

interface RouteState {
  assetId: string | null;
  investorId: string | null;
  overview: boolean;
  discovery: boolean;
  investors: boolean;
  queryString: string;
}

function readRouteState(): RouteState {
  const path = window.location.pathname;
  const assetMatch = path.match(/^\/assets\/([^/]+)$/);
  const investorMatch = path.match(/^\/investors\/([^/]+)$/);
  return {
    assetId: assetMatch?.[1] ?? null,
    investorId: investorMatch?.[1] ?? null,
    overview: path === "/",
    discovery: path === "/assets",
    investors: path === "/investors" || investorMatch !== null,
    queryString: window.location.search
  };
}

function navigateToAsset(assetId: string): void {
  window.history.pushState({}, "", "/assets/" + assetId);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function navigateToDiscovery(queryString = ""): void {
  window.history.pushState({}, "", "/assets" + (queryString ? "?" + queryString : ""));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function navigateToOverview(): void {
  window.history.pushState({}, "", "/");
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function navigateToInvestors(queryString = ""): void {
  window.history.pushState({}, "", "/investors" + (queryString ? "?" + queryString : ""));
  window.dispatchEvent(new PopStateEvent("popstate"));
}

function navigateToInvestor(investorId: string): void {
  window.history.pushState({}, "", "/investors/" + investorId);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function App() {
  const [assets, setAssets] = useState<AssetListItem[]>([]);
  const [investors, setInvestors] = useState<InvestorListItem[]>([]);
  const [assetQuery, setAssetQuery] = useState("");
  const [route, setRoute] = useState<RouteState>(readRouteState);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<Error | null>(null);
  const [view, setView] = useState<AssetIntelligenceView | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewError, setViewError] = useState<Error | null>(null);
  const [investorCatalogLoading, setInvestorCatalogLoading] = useState(true);
  const [investorCatalogError, setInvestorCatalogError] = useState<Error | null>(null);
  const [investorView, setInvestorView] = useState<InvestorProductView | null>(null);
  const [investorViewLoading, setInvestorViewLoading] = useState(false);
  const [investorViewError, setInvestorViewError] = useState<Error | null>(null);
  const [operationalStatus, setOperationalStatus] = useState<OperationalStatusResponse | null>(null);
  const [operationalStatusError, setOperationalStatusError] = useState<Error | null>(null);
  const [recentIntelligence, setRecentIntelligence] = useState<IntelligenceFeedItem[]>([]);
  const [recentIntelligenceLoading, setRecentIntelligenceLoading] = useState(true);
  const [recentIntelligenceError, setRecentIntelligenceError] = useState<Error | null>(null);
  const assetId = route.assetId;
  const investorId = route.investorId;

  useEffect(() => {
    const handlePopState = () => setRoute(readRouteState());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
  }, []);

  useEffect(() => {
    let active = true;
    const loadRecentIntelligence = () => {
      const since = new Date(Date.now() - 24 * 60 * 60 * 1000).toISOString();
      setRecentIntelligenceLoading(true);
      getRecentIntelligence(since)
        .then((value) => {
          if (!active) return;
          setRecentIntelligence(value.items);
          setRecentIntelligenceError(null);
        })
        .catch((error: unknown) => {
          if (!active) return;
          setRecentIntelligence([]);
          setRecentIntelligenceError(
            error instanceof Error ? error : new Error("近期投资情报暂不可用")
          );
        })
        .finally(() => {
          if (active) setRecentIntelligenceLoading(false);
        });
    };
    loadRecentIntelligence();
    const interval = window.setInterval(loadRecentIntelligence, 60_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let active = true;
    const loadStatus = () => {
      getOperationalStatus()
        .then((value) => {
          if (!active) return;
          setOperationalStatus(value);
          setOperationalStatusError(null);
        })
        .catch((error: unknown) => {
          if (!active) return;
          setOperationalStatus(null);
          setOperationalStatusError(error instanceof Error ? error : new Error("API 暂不可用"));
        });
    };
    loadStatus();
    const interval = window.setInterval(loadStatus, 60_000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  useEffect(() => {
    let active = true;
    setInvestorCatalogLoading(true);
    getInvestorList()
      .then((payload) => {
        if (!active) return;
        setInvestors(payload.items);
        setInvestorCatalogError(null);
      })
      .catch((error: unknown) => {
        if (active) {
          setInvestorCatalogError(
            error instanceof Error ? error : new Error("API 暂不可用")
          );
        }
      })
      .finally(() => {
        if (active) setInvestorCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    let active = true;
    setCatalogLoading(true);
    getAssetList()
      .then((payload) => {
        if (!active) return;
        setAssets(payload.items);
        setCatalogError(null);
      })
      .catch((error: unknown) => {
        if (active) setCatalogError(error instanceof Error ? error : new Error("API 暂不可用"));
      })
      .finally(() => {
        if (active) setCatalogLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    if (!assetId) {
      setView(null);
      setViewError(null);
      setViewLoading(false);
      return;
    }
    let active = true;
    setView(null);
    setViewLoading(true);
    setViewError(null);
    getAssetIntelligenceView(assetId)
      .then((asset) => {
        if (!active) return;
        setView(asset);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setView(null);
        setViewError(error instanceof Error ? error : new Error("API 暂不可用"));
      })
      .finally(() => {
        if (active) setViewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [assetId]);

  useEffect(() => {
    if (!investorId) {
      setInvestorView(null);
      setInvestorViewError(null);
      setInvestorViewLoading(false);
      return;
    }
    let active = true;
    setInvestorView(null);
    setInvestorViewLoading(true);
    setInvestorViewError(null);
    getInvestorIntelligenceView(investorId)
      .then((value) => {
        if (active) setInvestorView(value);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setInvestorView(null);
        setInvestorViewError(error instanceof Error ? error : new Error("API 暂不可用"));
      })
      .finally(() => {
        if (active) setInvestorViewLoading(false);
      });
    return () => {
      active = false;
    };
  }, [investorId]);

  const selectedAsset = useMemo(
    () => assets.find((item) => item.asset_id === assetId) ?? null,
    [assets, assetId]
  );
  const visibleAssets = useMemo(
    () => filterAssets(assets, assetQuery),
    [assets, assetQuery]
  );
  const investorNames = useMemo(
    () => Object.fromEntries(investors.map((investor) => [investor.investor_id, investor.investor_name])),
    [investors]
  );

  const handleSelect = (nextAssetId: string) => {
    if (nextAssetId) navigateToAsset(nextAssetId);
  };

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark">
            <span />
            <span />
            <span />
          </div>
          <div>
            <strong>SNOWBALL</strong>
            <small>投资情报</small>
          </div>
        </div>

        <div className="sidebar-divider" />
        <div className="sidebar-kicker">工作区</div>
        <button
          type="button"
          className={"sidebar-nav-item" + (route.overview ? " active" : "")}
          onClick={navigateToOverview}
        >
          <span className="nav-dot" />
          概览
        </button>
        <button
          type="button"
          className={"sidebar-nav-item" + (route.discovery ? " active" : "")}
          onClick={() => navigateToDiscovery()}
        >
          <span className="nav-dot" />
          标的发现
        </button>
        <button
          type="button"
          className={"sidebar-nav-item" + (!route.overview && !route.discovery ? " active" : "")}
          disabled={!assetId && assets.length === 0}
          onClick={() => navigateToAsset(assetId ?? assets[0]?.asset_id ?? "")}
        >
          <span className="nav-dot" />
          标的情报
        </button>
        <button
          type="button"
          className={"sidebar-nav-item" + (route.investors ? " active" : "")}
          onClick={() => navigateToInvestors()}
        >
          <span className="nav-dot" />
          投资者洞察
        </button>

        <div className="asset-selector">
          <label htmlFor="asset-select">跳转到标的</label>
          <input
            id="asset-search"
            aria-label="搜索标的"
            type="search"
            placeholder="搜索名称、市场或代码"
            value={assetQuery}
            onChange={(event) => setAssetQuery(event.target.value)}
          />
          <select
            id="asset-select"
            value={assetId ?? ""}
            onChange={(event) => handleSelect(event.target.value)}
            disabled={catalogLoading || assets.length === 0}
          >
            <option value="" disabled>
              {catalogLoading ? "正在加载标的…" : "选择标的"}
            </option>
            {visibleAssets.map((asset) => (
              <option key={asset.asset_id} value={asset.asset_id}>
                {asset.asset_name} · {asset.market}:{asset.symbol}
              </option>
            ))}
          </select>
          <span className="selector-count">
            {catalogLoading
              ? "正在同步证据…"
              : visibleAssets.length === assets.length
                ? assets.length + " 个有证据标的"
                : visibleAssets.length + " / " + assets.length + " 个标的"}
          </span>
        </div>

        <div className="quick-list">
          <div className="sidebar-kicker">快速访问</div>
          {visibleAssets.slice(0, 7).map((asset) => (
            <button
              className={"quick-item" + (asset.asset_id === assetId ? " selected" : "")}
              key={asset.asset_id}
              onClick={() => handleSelect(asset.asset_id)}
            >
              <span>{asset.asset_name}</span>
              <small>
                {asset.market}:{asset.symbol}
              </small>
            </button>
          ))}
        </div>

        <div className="sidebar-footer">
          <div className="status-light" />
          <div>
            <strong>只读证据层</strong>
            <span>生产 API · V0</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <div className="topbar">
          <div className="breadcrumb">
            <span>投资情报</span>
            <b>/</b>
            <span className="muted">
              {route.overview
                ? "概览"
                : route.discovery
                  ? "标的发现"
                  : route.investors
                    ? "投资者洞察"
                    : "标的视图"}
            </span>
          </div>
          <div className="topbar-status">
            <OperationalStatusIndicator
              status={operationalStatus}
              error={operationalStatusError}
            />
            <span className="live-dot" />
            已观察证据
            <span className="topbar-separator" />
            PostgreSQL
          </div>
        </div>

        {route.overview ? (
          <OverviewPage
            assets={assets}
            loading={catalogLoading}
            error={catalogError}
            onOpenAsset={handleSelect}
            onOpenDiscovery={navigateToDiscovery}
            onOpenInvestor={navigateToInvestor}
            recentItems={recentIntelligence}
            recentLoading={recentIntelligenceLoading}
            recentError={recentIntelligenceError}
            operationalStatus={operationalStatus}
          />
        ) : route.discovery ? (
          <DiscoveryPage
            assets={assets}
            loading={catalogLoading}
            error={catalogError}
            queryString={route.queryString}
            onOpenAsset={handleSelect}
            onQueryChange={navigateToDiscovery}
          />
        ) : route.investors && !investorId ? (
          <InvestorDiscoveryPage
            investors={investors}
            loading={investorCatalogLoading}
            error={investorCatalogError}
            queryString={route.queryString}
            onOpenInvestor={navigateToInvestor}
            onQueryChange={navigateToInvestors}
          />
        ) : route.investors ? (
          investorViewLoading ? (
            <LoadingState />
          ) : investorViewError ? (
            <PageState
              kind={
                investorViewError instanceof ApiError && investorViewError.status === 404
                  ? "empty"
                  : "error"
              }
              title={
                investorViewError instanceof ApiError && investorViewError.status === 404
                  ? "暂无已观察的投资者证据"
                  : "API 暂不可用"
              }
              description={
                investorViewError instanceof ApiError && investorViewError.status === 404
                  ? "此页面仅展示当前有效的关注动态或观点证据。"
                  : "只读投资者 API 返回了异常响应，系统未推断结论。"
              }
            />
          ) : investorView ? (
            <InvestorProductViewPage view={investorView} onOpenAsset={handleSelect} />
          ) : (
            <PageState
              kind="empty"
              title="暂无已观察的投资者证据"
              description="当前窗口中没有该投资者的有效已观察证据。"
            />
          )
        ) : catalogError && !assetId ? (
          <PageState
            kind="error"
            title="API 暂不可用"
            description="标的情报 API 无法访问，请确认本地后端运行后重试。"
          />
        ) : viewLoading ? (
          <LoadingState />
        ) : viewError ? (
          <PageState
            kind={viewError instanceof ApiError && viewError.status === 404 ? "empty" : "error"}
            title={
              viewError instanceof ApiError && viewError.status === 404
                ? "暂无标的情报证据"
                : "API 暂不可用"
            }
            description={
              viewError instanceof ApiError && viewError.status === 404
                ? "当前数据库窗口中没有该标的的产品视图。"
                : "只读 API 返回了异常响应，系统未推断任何情报。"
            }
          />
        ) : view ? (
          <AssetProductViewPage
            view={view}
            investorNames={investorNames}
            onOpenInvestor={navigateToInvestor}
          />
        ) : selectedAsset ? (
          <PageState
            kind="empty"
            title="当前窗口暂无证据"
            description="所选窗口中没有该标的的有效关注动态或观点证据。"
          />
        ) : (
          <PageState
            kind="empty"
            title="选择一个标的"
            description="从左侧选择有证据记录的标的，查看已观察情报。"
          />
        )}
      </main>
    </div>
  );
}

export function OperationalStatusIndicator({
  status,
  error
}: {
  status: OperationalStatusResponse | null;
  error: Error | null;
}) {
  const label = operationalStatusLabel(status, error);
  const detail = operationalStatusDetail(status, error);
  return (
    <div className={"operational-status-indicator " + (status?.status?.toLowerCase() ?? "unknown")} aria-label={label}>
      <span className="operational-status-dot" />
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
    </div>
  );
}

function operationalStatusLabel(
  status: OperationalStatusResponse | null,
  error: Error | null
): string {
  if (error || !status) return "刷新状态不可用";
  if (status.status === "HEALTHY") return "运行正常";
  if (status.status === "STALE") return "数据较旧";
  if (status.status === "ACTION_REQUIRED") {
    return status.latest_failure_code === "AUTH_REQUIRED" || status.latest_failure_code === "CDP_UNAVAILABLE"
      ? "需要重新登录雪球"
      : "刷新失败";
  }
  if (status.status === "SOURCE_LIMITED") return "数据源暂时受限";
  return "刷新状态未知";
}

function operationalStatusDetail(
  status: OperationalStatusResponse | null,
  error: Error | null
): string {
  if (error || !status) return "无法加载运行状态";
  if (status.freshness_age_seconds === null || !Number.isFinite(status.freshness_age_seconds)) return "暂无成功刷新记录";
  return "数据刷新于 " + formatAge(status.freshness_age_seconds) + "前";
}

function formatAge(seconds: number): string {
  const minutes = Math.max(0, Math.floor(seconds / 60));
  if (minutes < 1) return "不到 1 分钟";
  if (minutes < 60) return minutes + "分钟";
  const hours = Math.floor(minutes / 60);
  const remaining = minutes % 60;
  return hours + "小时" + (remaining ? " " + remaining + "分钟" : "");
}

function AssetPage({
  view,
  timeline
}: {
  view: CombinedAssetView;
  timeline: TimelineResponse;
}) {
  const opinionInvestorCount = view.investor_views.filter((item) => item.opinion_count > 0).length;
  const opinionCount = view.investor_views.reduce((total, item) => total + item.opinion_count, 0);
  const missingComparisons = view.data_quality.missing_thesis_comparison_count;
  const sequence = view.observed_attention_sequence;
  const sequenceObservations = sequence
    ? [sequence.first_observed, ...sequence.later_observations]
    : [];

  return (
    <div className="page-container">
      <header className="asset-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            标的情报 / 已观察证据
          </div>
          <div className="asset-title-row">
            <h1>{view.asset_name}</h1>
            <span className="listing-badge">
              {view.market} <i>·</i> {view.symbol}
            </span>
          </div>
          <p className="asset-subtitle">
            展示监测样本中关注动态、观点与投资逻辑证据的时间变化。
          </p>
        </div>
        <div className="boundary-card">
          <span className="boundary-label">历史完整性</span>
          <strong>未知</strong>
          <span className="boundary-note">仅展示观察顺序</span>
        </div>
      </header>

      <div className="metric-strip">
        <Metric label="关注动态投资者" value={view.attention_summary.attention_investor_count} note="已观察覆盖" />
        <Metric label="观点投资者" value={opinionInvestorCount} note="结构化观点" />
        <Metric label="关注动态发生次数" value={view.attention_summary.attention_occurrence_count} note="有效证据" />
        <Metric label="观点记录" value={opinionCount} note="生产有效" />
        <Metric label="时间关系" value={view.attention_summary.temporal_edges.length} note="观察顺序" />
        <Metric
          label="缺少对比"
          value={missingComparisons}
          note={missingComparisons ? "需要复核" : "暂无已知缺口"}
          accent={missingComparisons ? "amber" : undefined}
        />
      </div>

      <section className="panel attention-panel">
        <SectionHeading
          number="01"
          title="已观察关注动态"
          subtitle="在监测样本中首次观察到"
          action={
            <span className="panel-window">
              {formatTime(view.window_start)} — {formatTime(view.window_end)}
            </span>
          }
        />
        {sequence ? (
          <>
            <div className="sequence-summary">
              <div>
                <span className="summary-label">观察顺序</span>
                <strong>{sequence.investor_count} 位投资者</strong>
              </div>
              <div>
                <span className="summary-label">时间跨度</span>
                <strong>
                  {view.attention_summary.observed_span_days !== null
                    ? view.attention_summary.observed_span_days.toFixed(2) + "天"
                    : "—"}
                </strong>
              </div>
              <div className="sequence-note">
                仅展示是否出现及时间顺序。相同时间戳显示为同时观察，不代表因果关系。
              </div>
            </div>
            <div className="sequence-track">
              {sequenceObservations.map((observation, index) => (
                <div className="sequence-step-wrap" key={observation.attention_occurrence_id}>
                  {index > 0 && (
                    <div className="sequence-connector">
                      <span className="connector-arrow">
                        {observation.lag_days === 0 ? "＝" : "↓"}
                      </span>
                      <span>
                        {observation.lag_days === 0
                          ? "同时观察到"
                          : formatLag(observation.lag_days)}
                      </span>
                    </div>
                  )}
                  <AttentionNode
                    observation={observation}
                    first={index === 0}
                  />
                </div>
              ))}
            </div>
          </>
        ) : (
          <EmptyInline text="该标的暂无多投资者观察顺序。" />
        )}
      </section>

      <section className="panel investor-panel">
        <SectionHeading
          number="02"
          title="投资者观点"
          subtitle="按投资者拆分的独立证据"
          action={<span className="section-count">{view.investor_views.length} 位参与者</span>}
        />
        {view.investor_views.length ? (
          <div className="investor-grid">
            {view.investor_views.map((investor, index) => (
              <InvestorCard key={investor.investor_id} investor={investor} index={index} />
            ))}
          </div>
        ) : (
          <EmptyInline text="该标的暂无投资者证据。" />
        )}
      </section>

      <section className="context-grid">
        <div className="panel context-panel">
          <SectionHeading number="03" title="跨投资者背景" subtitle="已有证据，不新增评分" />
          <div className="context-cards">
            <ContextCard
              label="方向一致性"
              value={view.alignment?.directional_alignment_state ?? "不可用"}
              tone={
                view.alignment?.directional_alignment_state === "MIXED_DIRECTION"
                  ? "split"
                  : "teal"
              }
              description={contextDescription(
                view.alignment?.directional_alignment_state,
                "alignment"
              )}
            />
            <ContextCard
              label="共识 V2"
              value={view.consensus?.consensus_state ?? "不可用"}
              tone={view.consensus?.consensus_state === "DIVERGENT" ? "split" : "teal"}
              description={contextDescription(view.consensus?.consensus_state, "consensus")}
            />
          </div>
          <div className="coverage-callout">
            <div className="coverage-icon">◎</div>
            <div>
              <strong>关注覆盖 ≠ 观点覆盖</strong>
              <span>
                {view.attention_summary.attention_investor_count} 位投资者出现关注动态；{" "}
                {opinionInvestorCount} 位投资者有有效观点。
              </span>
            </div>
          </div>
        </div>

        <DataQualityPanel view={view} />
      </section>

      <section className="panel timeline-panel">
        <SectionHeading
          number="04"
          title="统一时间线"
          subtitle="按发布时间排序的证据事件"
          action={<span className="timeline-legend">序列化顺序 ≠ 因果顺序</span>}
        />
        <UnifiedTimeline timeline={timeline} />
      </section>

      <footer className="page-footer">
        <span>雪球情报 · 只读证据视图</span>
        <span>最近方向仅表示最近观察到的观点。</span>
      </footer>
    </div>
  );
}

function Metric({
  label,
  value,
  note,
  accent
}: {
  label: string;
  value: number;
  note: string;
  accent?: "amber";
}) {
  return (
    <div className={"metric" + (accent ? " " + accent : "")}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function SectionHeading({
  number,
  title,
  subtitle,
  action
}: {
  number: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="section-heading">
      <div className="section-title">
        <span className="section-number">{number}</span>
        <div>
          <h2>{title}</h2>
          <span>{subtitle}</span>
        </div>
      </div>
      {action}
    </div>
  );
}

function AttentionNode({
  observation,
  first
}: {
  observation: AttentionObservation;
  first: boolean;
}) {
  const simultaneous = !first && observation.lag_days === 0;
  return (
    <div className="sequence-node">
      <div className={"node-marker" + (first ? " first" : "")}>
        <span>{first ? "01" : "•"}</span>
      </div>
      <div className="node-body">
        <div className="node-topline">
          <span className="node-state">
            {first ? "首次观察" : simultaneous ? "同时观察" : "之后观察"}
          </span>
          {observation.first_opinion_direction && (
            <DirectionPill direction={observation.first_opinion_direction} />
          )}
        </div>
        <h3>{observation.investor_name}</h3>
        <div className="node-meta">
          <span>{formatTime(observation.published_time)}</span>
          <span className="meta-separator">·</span>
          <span>{observation.evidence_types.map(evidenceLabel).join(" + ")}</span>
        </div>
        <div className="chip-row">
          {observation.evidence_types.map((evidence) => (
            <EvidenceChip evidence={evidence} key={evidence} />
          ))}
        </div>
      </div>
    </div>
  );
}

function InvestorCard({ investor, index }: { investor: InvestorView; index: number }) {
  const [open, setOpen] = useState(false);
  const timeline = investor.thesis_timeline;
  const detailId = "investor-detail-" + investor.investor_id;
  return (
    <div className={"investor-card" + (open ? " expanded" : "")}>
      <button
        type="button"
        className="investor-card-header"
        aria-expanded={open}
        aria-controls={detailId}
        onClick={() => setOpen((value) => !value)}
      >
        <div className="investor-avatar">{investor.investor_name.slice(0, 1)}</div>
        <div className="investor-heading">
          <strong>{investor.investor_name}</strong>
          <span>{relationLabel(investor.attention_opinion_relation)}</span>
        </div>
        <div className="investor-latest">
          <span className="latest-label">最近观察到的观点</span>
          <DirectionPill direction={investor.latest_observed_direction} />
          <small className="latest-time">{formatTime(investor.latest_opinion_time)}</small>
        </div>
        <span className={"chevron" + (open ? " up" : "")}>⌄</span>
      </button>

      <div className="investor-quick-summary">
        <div>
          <strong>{investor.attention_occurrence_count}</strong>
          <span>关注动态</span>
        </div>
        <div>
          <strong>{investor.opinion_count}</strong>
          <span>观点</span>
        </div>
        <div>
          <strong>{investor.thesis_change_count}</strong>
          <span>投资逻辑变化</span>
        </div>
        <div>
          <strong>{formatTime(investor.first_attention_time)}</strong>
          <span>首次观察</span>
        </div>
      </div>

      <div id={detailId} className="investor-card-body">
        <div className="investor-stat-grid">
          <Stat label="关注动态" value={String(investor.attention_occurrence_count)} />
          <Stat label="观点" value={String(investor.opinion_count)} />
          <Stat label="投资逻辑变化" value={String(investor.thesis_change_count)} />
          <Stat label="反转" value={String(investor.reversal_count)} accent={investor.reversal_count ? "coral" : undefined} />
        </div>

        <div className="evidence-block">
          <div className="block-label">关注动态</div>
          <div className="attention-detail-row">
            <span>首次观察</span>
            <strong>{formatTime(investor.first_attention_time)}</strong>
          </div>
          <div className="attention-detail-row">
            <span>证据来源</span>
            <span className="chip-row compact">
              {investor.attention_evidence_types.length
                ? investor.attention_evidence_types.map((evidence) => (
                    <EvidenceChip evidence={evidence} key={evidence} />
                  ))
                : "暂无关注动态"}
            </span>
          </div>
        </div>

        <div className="evidence-block">
          <div className="block-label">观点</div>
          <div className="attention-detail-row">
            <span>首次 → 最近</span>
            <strong>
              {formatTime(investor.first_opinion_time)} <i>→</i> {formatTime(investor.latest_opinion_time)}
            </strong>
          </div>
          <div className="attention-detail-row">
            <span>最近观察到的方向</span>
            <DirectionPill direction={investor.latest_observed_direction} />
          </div>
        </div>

        <div className="evidence-block thesis-block">
          <div className="block-label">投资逻辑</div>
          <div className="thesis-summary-row">
            <div>
              <span>已变化</span>
              <strong>{investor.changed_count}</strong>
            </div>
            <div>
              <span>已扩展</span>
              <strong>{investor.extended_count}</strong>
            </div>
            <div>
              <span>最近语义</span>
              <strong>{thesisLabel(investor.latest_thesis_change_type)}</strong>
            </div>
          </div>
          {investor.missing_thesis_comparison_count > 0 && (
            <div className="comparison-note">
              <span className="note-icon">!</span>
              <span>{investor.missing_thesis_comparison_count} 次对比不可用</span>
            </div>
          )}
        </div>

        {timeline && (
          <div className="thesis-timeline">
            <div className="block-label">投资逻辑演变时间线</div>
            <div className="mini-timeline">
              {timeline.entries.map((entry) => (
                <div className="mini-timeline-row" key={entry.opinion_id}>
                  <div className="mini-time">{formatTime(entry.published_time)}</div>
                  <div className="mini-dot" />
                  <div className="mini-content">
                    <div className="mini-title-row">
                      <DirectionPill direction={entry.direction} />
                      <span className="semantic-label">
                        {thesisLabel(entry.thesis_change_type)}
                      </span>
                    </div>
                    <div className="mini-meta">
                      {entry.thesis_comparison_status === "MISSING_THESIS_COMPARISON" ? (
                        <span className="comparison-unavailable">无法进行对比</span>
                      ) : (
                        <span>{formatEnum(entry.direction_transition)}</span>
                      )}
                    </div>
                    {(entry.thesis.length > 0 || entry.catalysts.length > 0 || entry.risks.length > 0) && (
                      <div className="thesis-text">
                        {entry.thesis.length > 0 && <span><b>投资逻辑</b> {entry.thesis.join(" · ")}</span>}
                        {entry.catalysts.length > 0 && <span><b>催化因素</b> {entry.catalysts.join(" · ")}</span>}
                        {entry.risks.length > 0 && <span><b>风险</b> {entry.risks.join(" · ")}</span>}
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: "coral" }) {
  return (
    <div className="investor-stat">
      <span>{label}</span>
      <strong className={accent ?? ""}>{value}</strong>
    </div>
  );
}

function DirectionPill({ direction }: { direction: Direction | null }) {
  const strong = direction?.startsWith("STRONG_") ? " strong-direction" : "";
  return (
    <span className={"direction-pill " + directionClass(direction) + strong}>
      {directionLabel(direction)}
    </span>
  );
}

function EvidenceChip({ evidence }: { evidence: "OPINION" | "EXPLICIT_MENTION" | "REPOST" }) {
  return <span className={"evidence-chip " + evidence.toLowerCase()}>{evidenceLabel(evidence)}</span>;
}

function ContextCard({
  label,
  value,
  tone,
  description
}: {
  label: string;
  value: string;
  tone: "teal" | "split";
  description: string;
}) {
  return (
    <div className={"context-card " + tone}>
      <div className="context-card-top">
        <span>{label}</span>
        <i className="context-symbol">{tone === "split" ? "◐" : "◌"}</i>
      </div>
      <strong>{formatEnum(value)}</strong>
      <p>{description}</p>
    </div>
  );
}

function DataQualityPanel({ view }: { view: CombinedAssetView }) {
  const flags = view.data_quality.unresolved_semantic_limitations;
  const persistentFlags = flags.filter((flag) =>
    [
      "HISTORICAL_COMPLETENESS_UNKNOWN",
      "ABSENCE_INFERENCE_UNSUPPORTED",
      "LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY"
    ].includes(flag)
  );
  const assetFlags = flags.filter(
    (flag) =>
      ![
        "HISTORICAL_COMPLETENESS_UNKNOWN",
        "ABSENCE_INFERENCE_UNSUPPORTED",
        "LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY"
      ].includes(flag)
  );
  if (
    view.investor_views.length > 0 &&
    !view.investor_views.some((investor) => investor.opinion_count > 0)
  ) {
    assetFlags.push("NO_OPINION_COVERAGE");
  }
  return (
    <div className="panel quality-panel">
      <SectionHeading number="Q" title="数据质量" subtitle="明确展示数据边界" />
      <div className="quality-status">
        <span className="quality-icon">◈</span>
        <div>
          <strong>已观察证据边界</strong>
          <span>历史完整性：未知</span>
        </div>
      </div>
      <QualityGroup title="持续性限制" flags={persistentFlags} />
      <QualityGroup title="标的特定缺口" flags={assetFlags} />
    </div>
  );
}

function QualityGroup({ title, flags }: { title: string; flags: string[] }) {
  return (
    <div className="quality-group">
      <span className="quality-group-title">{title}</span>
      {flags.length ? (
        <div className="quality-list">
          {flags.map((flag) => (
            <div className="quality-row" key={flag}>
              <span className="quality-check">•</span>
              <span>{limitationLabel(flag)}</span>
            </div>
          ))}
        </div>
      ) : (
        <div className="quality-none">暂无观察记录</div>
      )}
    </div>
  );
}

function contextDescription(value: string | undefined, kind: "alignment" | "consensus"): string {
  if (!value) {
    return kind === "alignment"
      ? "当前窗口暂无活跃的跨投资者谱系。"
      : "当前窗口暂无活跃的共识谱系。";
  }
  if (value === "MIXED_DIRECTION") return "已观察观点横跨多个方向。";
  if (value === "DIVERGENT") {
    return "最近观察到的观点同时包含积极与谨慎方向。";
  }
  if (value === "INSUFFICIENT_EVIDENCE") {
    return "当前观点覆盖未达到共识证据要求。";
  }
  return kind === "alignment"
    ? "当前已观察窗口已有方向一致性证据。"
    : "当前已观察窗口已有共识证据。";
}

type TimelineFilter = "ALL" | "ATTENTION" | "OPINION" | "THESIS";

function UnifiedTimeline({ timeline }: { timeline: TimelineResponse }) {
  const [filter, setFilter] = useState<TimelineFilter>("ALL");
  const [showAll, setShowAll] = useState(false);
  const filteredEvents = timeline.events.filter((event) => {
    if (filter === "ALL") return true;
    if (filter === "ATTENTION") return event.event_type.startsWith("ATTENTION");
    if (filter === "OPINION") return event.event_type === "OPINION_OBSERVED";
    return event.event_type === "THESIS_CHANGE_OBSERVED";
  });
  const visibleEvents = showAll ? filteredEvents : filteredEvents.slice(0, 12);
  const filters: Array<[TimelineFilter, string]> = [
    ["ALL", "全部"],
    ["ATTENTION", "关注动态"],
    ["OPINION", "观点"],
    ["THESIS", "投资逻辑"]
  ];

  return (
    <>
      <div className="timeline-controls">
        <div className="timeline-filters" role="group" aria-label="时间线事件筛选">
          {filters.map(([value, label]) => (
            <button
              type="button"
              className={"filter-pill" + (filter === value ? " active" : "")}
              aria-pressed={filter === value}
              key={value}
              onClick={() => {
                setFilter(value);
                setShowAll(false);
              }}
            >
              {label}
            </button>
          ))}
        </div>
        <div className="timeline-control-meta">
          <span>
            正在显示 {visibleEvents.length} / {filteredEvents.length}
          </span>
          {filteredEvents.length > 12 && (
            <button
              type="button"
              className="show-all-button"
              onClick={() => setShowAll((value) => !value)}
            >
              {showAll ? "显示前 12 条" : "显示全部"}
            </button>
          )}
        </div>
      </div>
      {visibleEvents.length ? (
        <div className="unified-timeline">
          {visibleEvents.map((event, index) => (
            <TimelineRow event={event} key={eventKey(event, index)} />
          ))}
        </div>
      ) : (
        <EmptyInline text="没有符合当前筛选的时间线事件。" />
      )}
    </>
  );
}

function TimelineRow({ event }: { event: TimelineEvent }) {
  return (
    <div className="timeline-row">
      <div className="timeline-time">{formatTime(event.published_time)}</div>
      <div className="timeline-spine">
        <span className={"timeline-dot " + event.event_type.toLowerCase()} />
      </div>
      <div className="timeline-event">
        <div className="timeline-event-header">
          <span className="event-type">{eventLabel(event.event_type)}</span>
          <span className="event-investor">{event.investor_name}</span>
        </div>
        <div className="timeline-event-meta">
          {event.direction && <DirectionPill direction={event.direction} />}
          {event.thesis_change_type && (
            <span className="semantic-label">{thesisLabel(event.thesis_change_type)}</span>
          )}
          {event.evidence_types.map((evidence) => (
            <EvidenceChip evidence={evidence} key={evidence} />
          ))}
        </div>
        <details className="provenance-details">
          <summary>证据详情</summary>
          <div className="provenance-grid">
            {event.raw_event_id && <Provenance label="采集事件" value={event.raw_event_id} />}
            {event.opinion_id && <Provenance label="观点" value={event.opinion_id} />}
            {event.event_analysis_id && <Provenance label="分析结果" value={event.event_analysis_id} />}
            {event.attention_occurrence_id && (
              <Provenance label="关注动态" value={event.attention_occurrence_id} />
            )}
            {event.thesis_change_id && <Provenance label="投资逻辑变化" value={event.thesis_change_id} />}
            {event.predecessor_opinion_id && (
              <Provenance label="前置观点" value={event.predecessor_opinion_id} />
            )}
          </div>
        </details>
      </div>
    </div>
  );
}

function Provenance({ label, value }: { label: string; value: string }) {
  return (
    <div className="provenance-item">
      <span>{label}</span>
      <code title={value}>{shortId(value)}</code>
    </div>
  );
}

function EmptyInline({ text }: { text: string }) {
  return <div className="empty-inline">{text}</div>;
}

function PageState({
  kind,
  title,
  description
}: {
  kind: "empty" | "error";
  title: string;
  description: string;
}) {
  return (
    <div className="page-state">
      <div className={"state-symbol " + kind}>{kind === "error" ? "!" : "○"}</div>
      <span className="eyebrow">{kind === "error" ? "系统提示" : "暂无已观察证据"}</span>
      <h1>{title}</h1>
      <p>{description}</p>
    </div>
  );
}

function LoadingState() {
  return (
    <div className="page-container loading-page">
      <div className="loading-header">
        <div className="skeleton eyebrow-skeleton" />
        <div className="skeleton title-skeleton" />
        <div className="skeleton subtitle-skeleton" />
      </div>
      <div className="skeleton metric-skeleton" />
      <div className="panel loading-panel">
        <div className="skeleton section-skeleton" />
        <div className="skeleton sequence-skeleton" />
      </div>
      <div className="loading-grid">
        <div className="panel loading-card" />
        <div className="panel loading-card" />
      </div>
    </div>
  );
}

function relationLabel(relation: InvestorView["attention_opinion_relation"]): string {
  const labels: Record<InvestorView["attention_opinion_relation"], string> = {
    OPINION_AT_FIRST_ATTENTION: "首次关注时已有观点",
    OPINION_AFTER_ATTENTION: "关注后形成观点",
    ATTENTION_WITHOUT_OPINION: "有关注、暂无观点",
    OPINION_WITHOUT_PRIOR_ATTENTION: "有观点、无先前关注",
    SIMULTANEOUS: "同时观察到"
  };
  return labels[relation];
}

function eventKey(event: TimelineEvent, index: number): string {
  return [
    event.published_time,
    event.event_type,
    event.investor_id,
    event.raw_event_id ?? "",
    index
  ].join("-");
}
