import { useEffect, useMemo, useState } from "react";

import {
  ApiError,
  getAsset,
  getAssetList,
  getAssetTimeline,
  getInvestor,
  getInvestorList
} from "./api";
import { DiscoveryPage } from "./DiscoveryPage";
import { InvestorDetailPage, InvestorDiscoveryPage } from "./InvestorPage";
import { OverviewPage } from "./OverviewPage";
import type {
  AssetListItem,
  AttentionObservation,
  CombinedAssetView,
  Direction,
  InvestorIntelligenceView,
  InvestorListItem,
  InvestorView,
  TimelineEvent,
  TimelineResponse
} from "./types";
import {
  directionClass,
  directionLabel,
  evidenceLabel,
  eventLabel,
  filterAssets,
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

function navigateToInvestorQuery(investorId: string, queryString: string): void {
  window.history.pushState(
    {},
    "",
    "/investors/" + investorId + (queryString ? "?" + queryString : "")
  );
  window.dispatchEvent(new PopStateEvent("popstate"));
}

export default function App() {
  const [assets, setAssets] = useState<AssetListItem[]>([]);
  const [investors, setInvestors] = useState<InvestorListItem[]>([]);
  const [assetQuery, setAssetQuery] = useState("");
  const [route, setRoute] = useState<RouteState>(readRouteState);
  const [catalogLoading, setCatalogLoading] = useState(true);
  const [catalogError, setCatalogError] = useState<Error | null>(null);
  const [view, setView] = useState<CombinedAssetView | null>(null);
  const [timeline, setTimeline] = useState<TimelineResponse | null>(null);
  const [viewLoading, setViewLoading] = useState(false);
  const [viewError, setViewError] = useState<Error | null>(null);
  const [investorCatalogLoading, setInvestorCatalogLoading] = useState(true);
  const [investorCatalogError, setInvestorCatalogError] = useState<Error | null>(null);
  const [investorView, setInvestorView] = useState<InvestorIntelligenceView | null>(null);
  const [investorViewLoading, setInvestorViewLoading] = useState(false);
  const [investorViewError, setInvestorViewError] = useState<Error | null>(null);
  const assetId = route.assetId;
  const investorId = route.investorId;

  useEffect(() => {
    const handlePopState = () => setRoute(readRouteState());
    window.addEventListener("popstate", handlePopState);
    return () => window.removeEventListener("popstate", handlePopState);
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
            error instanceof Error ? error : new Error("API unavailable")
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
        if (active) setCatalogError(error instanceof Error ? error : new Error("API unavailable"));
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
      setTimeline(null);
      return;
    }
    let active = true;
    setViewLoading(true);
    setViewError(null);
    Promise.all([getAsset(assetId), getAssetTimeline(assetId)])
      .then(([asset, assetTimeline]) => {
        if (!active) return;
        setView(asset);
        setTimeline(assetTimeline);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setView(null);
        setTimeline(null);
        setViewError(error instanceof Error ? error : new Error("API unavailable"));
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
      return;
    }
    let active = true;
    setInvestorViewLoading(true);
    setInvestorViewError(null);
    getInvestor(investorId)
      .then((value) => {
        if (active) setInvestorView(value);
      })
      .catch((error: unknown) => {
        if (!active) return;
        setInvestorView(null);
        setInvestorViewError(error instanceof Error ? error : new Error("API unavailable"));
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
            <small>INTELLIGENCE</small>
          </div>
        </div>

        <div className="sidebar-divider" />
        <div className="sidebar-kicker">WORKSPACE</div>
        <button
          type="button"
          className={"sidebar-nav-item" + (route.overview ? " active" : "")}
          onClick={navigateToOverview}
        >
          <span className="nav-dot" />
          Overview
        </button>
        <button
          type="button"
          className={"sidebar-nav-item" + (route.discovery ? " active" : "")}
          onClick={() => navigateToDiscovery()}
        >
          <span className="nav-dot" />
          Asset Discovery
        </button>
        <button
          type="button"
          className={"sidebar-nav-item" + (!route.overview && !route.discovery ? " active" : "")}
          disabled={!assetId && assets.length === 0}
          onClick={() => navigateToAsset(assetId ?? assets[0]?.asset_id ?? "")}
        >
          <span className="nav-dot" />
          Asset Intelligence
        </button>
        <button
          type="button"
          className={"sidebar-nav-item" + (route.investors ? " active" : "")}
          onClick={() => navigateToInvestors()}
        >
          <span className="nav-dot" />
          Investor Intelligence
        </button>

        <div className="asset-selector">
          <label htmlFor="asset-select">Jump to Asset</label>
          <input
            id="asset-search"
            aria-label="Search assets"
            type="search"
            placeholder="Search name, market, symbol"
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
              {catalogLoading ? "Loading assets…" : "Select an asset"}
            </option>
            {visibleAssets.map((asset) => (
              <option key={asset.asset_id} value={asset.asset_id}>
                {asset.asset_name} · {asset.market}:{asset.symbol}
              </option>
            ))}
          </select>
          <span className="selector-count">
            {catalogLoading
              ? "Syncing evidence…"
              : visibleAssets.length === assets.length
                ? assets.length + " evidence-bearing assets"
                : visibleAssets.length + " of " + assets.length + " assets"}
          </span>
        </div>

        <div className="quick-list">
          <div className="sidebar-kicker">QUICK ACCESS</div>
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
            <strong>Read-only evidence layer</strong>
            <span>Production API · V0</span>
          </div>
        </div>
      </aside>

      <main className="main-content">
        <div className="topbar">
          <div className="breadcrumb">
            <span>INTELLIGENCE</span>
            <b>/</b>
            <span className="muted">
              {route.overview
                ? "OVERVIEW"
                : route.discovery
                  ? "ASSET DISCOVERY"
                  : route.investors
                    ? "INVESTOR INTELLIGENCE"
                    : "ASSET VIEW"}
            </span>
          </div>
          <div className="topbar-status">
            <span className="live-dot" />
            Observed evidence
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
                  ? "No observed Investor evidence"
                  : "API unavailable"
              }
              description={
                investorViewError instanceof ApiError && investorViewError.status === 404
                  ? "This page only presents effective observed Attention or Opinion evidence."
                  : "The read-only Investor API returned an unexpected response. No conclusion was inferred."
              }
            />
          ) : investorView ? (
            <InvestorDetailPage
              view={investorView}
              queryString={route.queryString}
              onOpenAsset={handleSelect}
              onOpenInvestor={navigateToInvestor}
              onQueryChange={(queryString) =>
                navigateToInvestorQuery(investorId ?? "", queryString)
              }
            />
          ) : (
            <PageState
              kind="empty"
              title="No observed Investor evidence"
              description="There is no effective observed evidence for this Investor in the current window."
            />
          )
        ) : catalogError && !assetId ? (
          <PageState
            kind="error"
            title="API unavailable"
            description="The Asset Intelligence API could not be reached. Try again when the local backend is running."
          />
        ) : viewLoading ? (
          <LoadingState />
        ) : viewError ? (
          <PageState
            kind={viewError instanceof ApiError && viewError.status === 404 ? "empty" : "error"}
            title={
              viewError instanceof ApiError && viewError.status === 404
                ? "No evidence in selected window"
                : "API unavailable"
            }
            description={
              viewError instanceof ApiError && viewError.status === 404
                ? "This page only presents effective evidence observed in the current database window."
                : "The read-only API returned an unexpected response. No intelligence has been inferred."
            }
          />
        ) : view && timeline ? (
          <AssetPage view={view} timeline={timeline} />
        ) : selectedAsset ? (
          <PageState
            kind="empty"
            title="No evidence in selected window"
            description="There is no effective Attention or Opinion evidence for this Asset in the selected window."
          />
        ) : (
          <PageState
            kind="empty"
            title="Choose an Asset"
            description="Select an evidence-bearing Asset from the left to inspect its observed intelligence."
          />
        )}
      </main>
    </div>
  );
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
            ASSET INTELLIGENCE / OBSERVED EVIDENCE
          </div>
          <div className="asset-title-row">
            <h1>{view.asset_name}</h1>
            <span className="listing-badge">
              {view.market} <i>·</i> {view.symbol}
            </span>
          </div>
          <p className="asset-subtitle">
            A monitored-sample view of attention, opinions, and thesis evidence over time.
          </p>
        </div>
        <div className="boundary-card">
          <span className="boundary-label">HISTORICAL COMPLETENESS</span>
          <strong>UNKNOWN</strong>
          <span className="boundary-note">Observed sequence only</span>
        </div>
      </header>

      <div className="metric-strip">
        <Metric label="Attention Investors" value={view.attention_summary.attention_investor_count} note="Observed breadth" />
        <Metric label="Opinion Investors" value={opinionInvestorCount} note="Structured viewpoints" />
        <Metric label="Attention Occurrences" value={view.attention_summary.attention_occurrence_count} note="Effective evidence" />
        <Metric label="Opinion Rows" value={opinionCount} note="Production-effective" />
        <Metric label="Temporal Edges" value={view.attention_summary.temporal_edges.length} note="Observed order" />
        <Metric
          label="Missing Comparison"
          value={missingComparisons}
          note={missingComparisons ? "Needs review" : "No known gap"}
          accent={missingComparisons ? "amber" : undefined}
        />
      </div>

      <section className="panel attention-panel">
        <SectionHeading
          number="01"
          title="Observed Attention"
          subtitle="First observed in monitored sample"
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
                <span className="summary-label">OBSERVED ORDER</span>
                <strong>{sequence.investor_count} Investors</strong>
              </div>
              <div>
                <span className="summary-label">TEMPORAL SPAN</span>
                <strong>
                  {view.attention_summary.observed_span_days !== null
                    ? view.attention_summary.observed_span_days.toFixed(2) + "d"
                    : "—"}
                </strong>
              </div>
              <div className="sequence-note">
                Presence and timing only. Equal timestamps are displayed as simultaneous, not causal.
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
                          ? "Observed at same time"
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
          <EmptyInline text="No multi-investor observed sequence is available for this Asset." />
        )}
      </section>

      <section className="panel investor-panel">
        <SectionHeading
          number="02"
          title="Investor Views"
          subtitle="Independent evidence by Investor"
          action={<span className="section-count">{view.investor_views.length} PARTICIPANTS</span>}
        />
        {view.investor_views.length ? (
          <div className="investor-grid">
            {view.investor_views.map((investor, index) => (
              <InvestorCard key={investor.investor_id} investor={investor} index={index} />
            ))}
          </div>
        ) : (
          <EmptyInline text="No Investor evidence is available for this Asset." />
        )}
      </section>

      <section className="context-grid">
        <div className="panel context-panel">
          <SectionHeading number="03" title="Cross-Investor Context" subtitle="Existing evidence, no new scoring" />
          <div className="context-cards">
            <ContextCard
              label="DIRECTIONAL ALIGNMENT"
              value={view.alignment?.directional_alignment_state ?? "UNAVAILABLE"}
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
              label="CONSENSUS V2"
              value={view.consensus?.consensus_state ?? "UNAVAILABLE"}
              tone={view.consensus?.consensus_state === "DIVERGENT" ? "split" : "teal"}
              description={contextDescription(view.consensus?.consensus_state, "consensus")}
            />
          </div>
          <div className="coverage-callout">
            <div className="coverage-icon">◎</div>
            <div>
              <strong>Attention breadth ≠ Opinion breadth</strong>
              <span>
                {view.attention_summary.attention_investor_count} Investors observed attention;{" "}
                {opinionInvestorCount} have effective Opinions.
              </span>
            </div>
          </div>
        </div>

        <DataQualityPanel view={view} />
      </section>

      <section className="panel timeline-panel">
        <SectionHeading
          number="04"
          title="Unified Timeline"
          subtitle="Evidence events ordered by published time"
          action={<span className="timeline-legend">Serialization order ≠ causal order</span>}
        />
        <UnifiedTimeline timeline={timeline} />
      </section>

      <footer className="page-footer">
        <span>Snowball Intelligence · read-only evidence view</span>
        <span>Latest direction means latest observed Opinion only.</span>
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
            {first ? "FIRST OBSERVED" : simultaneous ? "OBSERVED AT SAME TIME" : "OBSERVED LATER"}
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
          <span className="latest-label">LATEST OBSERVED OPINION</span>
          <DirectionPill direction={investor.latest_observed_direction} />
          <small className="latest-time">{formatTime(investor.latest_opinion_time)}</small>
        </div>
        <span className={"chevron" + (open ? " up" : "")}>⌄</span>
      </button>

      <div className="investor-quick-summary">
        <div>
          <strong>{investor.attention_occurrence_count}</strong>
          <span>Attention</span>
        </div>
        <div>
          <strong>{investor.opinion_count}</strong>
          <span>Opinions</span>
        </div>
        <div>
          <strong>{investor.thesis_change_count}</strong>
          <span>Thesis changes</span>
        </div>
        <div>
          <strong>{formatTime(investor.first_attention_time)}</strong>
          <span>First observed</span>
        </div>
      </div>

      <div id={detailId} className="investor-card-body">
        <div className="investor-stat-grid">
          <Stat label="Attention" value={String(investor.attention_occurrence_count)} />
          <Stat label="Opinions" value={String(investor.opinion_count)} />
          <Stat label="Thesis changes" value={String(investor.thesis_change_count)} />
          <Stat label="Reversals" value={String(investor.reversal_count)} accent={investor.reversal_count ? "coral" : undefined} />
        </div>

        <div className="evidence-block">
          <div className="block-label">ATTENTION</div>
          <div className="attention-detail-row">
            <span>First observed</span>
            <strong>{formatTime(investor.first_attention_time)}</strong>
          </div>
          <div className="attention-detail-row">
            <span>Evidence</span>
            <span className="chip-row compact">
              {investor.attention_evidence_types.length
                ? investor.attention_evidence_types.map((evidence) => (
                    <EvidenceChip evidence={evidence} key={evidence} />
                  ))
                : "No Attention"}
            </span>
          </div>
        </div>

        <div className="evidence-block">
          <div className="block-label">OPINION</div>
          <div className="attention-detail-row">
            <span>First → latest</span>
            <strong>
              {formatTime(investor.first_opinion_time)} <i>→</i> {formatTime(investor.latest_opinion_time)}
            </strong>
          </div>
          <div className="attention-detail-row">
            <span>Latest observed direction</span>
            <DirectionPill direction={investor.latest_observed_direction} />
          </div>
        </div>

        <div className="evidence-block thesis-block">
          <div className="block-label">THESIS</div>
          <div className="thesis-summary-row">
            <div>
              <span>Changed</span>
              <strong>{investor.changed_count}</strong>
            </div>
            <div>
              <span>Extended</span>
              <strong>{investor.extended_count}</strong>
            </div>
            <div>
              <span>Latest semantic</span>
              <strong>{thesisLabel(investor.latest_thesis_change_type)}</strong>
            </div>
          </div>
          {investor.missing_thesis_comparison_count > 0 && (
            <div className="comparison-note">
              <span className="note-icon">!</span>
              <span>{investor.missing_thesis_comparison_count} comparison unavailable</span>
            </div>
          )}
        </div>

        {timeline && (
          <div className="thesis-timeline">
            <div className="block-label">THESIS EVOLUTION TIMELINE</div>
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
                        <span className="comparison-unavailable">Comparison unavailable</span>
                      ) : (
                        <span>{entry.direction_transition.replaceAll("_", " ")}</span>
                      )}
                    </div>
                    {(entry.thesis.length > 0 || entry.catalysts.length > 0 || entry.risks.length > 0) && (
                      <div className="thesis-text">
                        {entry.thesis.length > 0 && <span><b>Thesis</b> {entry.thesis.join(" · ")}</span>}
                        {entry.catalysts.length > 0 && <span><b>Catalyst</b> {entry.catalysts.join(" · ")}</span>}
                        {entry.risks.length > 0 && <span><b>Risk</b> {entry.risks.join(" · ")}</span>}
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
      <strong>{value.replaceAll("_", " ")}</strong>
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
      <SectionHeading number="Q" title="Data Quality" subtitle="Limitations stay visible" />
      <div className="quality-status">
        <span className="quality-icon">◈</span>
        <div>
          <strong>Observed evidence boundary</strong>
          <span>Historical completeness: UNKNOWN</span>
        </div>
      </div>
      <QualityGroup title="PERSISTENT LIMITATIONS" flags={persistentFlags} />
      <QualityGroup title="ASSET-SPECIFIC GAPS" flags={assetFlags} />
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
        <div className="quality-none">None observed</div>
      )}
    </div>
  );
}

function contextDescription(value: string | undefined, kind: "alignment" | "consensus"): string {
  if (!value) {
    return kind === "alignment"
      ? "No active cross-investor lineage for this window."
      : "No active Consensus lineage for this window.";
  }
  if (value === "MIXED_DIRECTION") return "Observed Opinions span multiple direction sides.";
  if (value === "DIVERGENT") {
    return "Observed latest Opinions include both bullish-side and bearish-side directions.";
  }
  if (value === "INSUFFICIENT_EVIDENCE") {
    return "Current Opinion coverage does not meet the active consensus evidence requirement.";
  }
  return kind === "alignment"
    ? "Existing Alignment evidence for this observed window."
    : "Existing Consensus evidence for this observed window.";
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
    ["ALL", "All"],
    ["ATTENTION", "Attention"],
    ["OPINION", "Opinion"],
    ["THESIS", "Thesis"]
  ];

  return (
    <>
      <div className="timeline-controls">
        <div className="timeline-filters" role="group" aria-label="Timeline event filters">
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
            Showing {visibleEvents.length} of {filteredEvents.length}
          </span>
          {filteredEvents.length > 12 && (
            <button
              type="button"
              className="show-all-button"
              onClick={() => setShowAll((value) => !value)}
            >
              {showAll ? "Show first 12" : "Show all"}
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
        <EmptyInline text="No timeline events match this filter." />
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
          <summary>Evidence details</summary>
          <div className="provenance-grid">
            {event.raw_event_id && <Provenance label="RawEvent" value={event.raw_event_id} />}
            {event.opinion_id && <Provenance label="Opinion" value={event.opinion_id} />}
            {event.event_analysis_id && <Provenance label="Analysis" value={event.event_analysis_id} />}
            {event.attention_occurrence_id && (
              <Provenance label="Attention" value={event.attention_occurrence_id} />
            )}
            {event.thesis_change_id && <Provenance label="ThesisChange" value={event.thesis_change_id} />}
            {event.predecessor_opinion_id && (
              <Provenance label="Predecessor" value={event.predecessor_opinion_id} />
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
      <span className="eyebrow">{kind === "error" ? "SYSTEM MESSAGE" : "NO OBSERVED EVIDENCE"}</span>
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
    OPINION_AT_FIRST_ATTENTION: "Opinion at first Attention",
    OPINION_AFTER_ATTENTION: "Opinion after Attention",
    ATTENTION_WITHOUT_OPINION: "Attention without Opinion",
    OPINION_WITHOUT_PRIOR_ATTENTION: "Opinion without prior Attention",
    SIMULTANEOUS: "Observed simultaneously"
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
