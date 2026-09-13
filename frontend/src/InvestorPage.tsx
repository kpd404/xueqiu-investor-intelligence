import { useMemo } from "react";

import type {
  EvidenceType,
  InvestorAssetIntelligenceSummary,
  InvestorIntelligenceView,
  InvestorListItem
} from "./types";
import {
  directionClass,
  directionLabel,
  evidenceLabel,
  formatTime
} from "./presentation";

type AssetFilter =
  | "all"
  | "attention"
  | "opinion"
  | "repeated"
  | "changed"
  | "reversal"
  | "shared_attention"
  | "shared_opinion";
type AssetSort = "latest" | "first" | "attention" | "opinion" | "name";
type OverlapSort = "name" | "attention" | "opinion";

interface InvestorPageProps {
  view: InvestorIntelligenceView;
  queryString: string;
  onOpenAsset: (assetId: string) => void;
  onOpenInvestor: (investorId: string) => void;
  onQueryChange: (queryString: string) => void;
}

interface InvestorDiscoveryPageProps {
  investors: InvestorListItem[];
  loading: boolean;
  error: Error | null;
  queryString: string;
  onOpenInvestor: (investorId: string) => void;
  onQueryChange: (queryString: string) => void;
}

interface InvestorDetailQuery {
  filter: AssetFilter;
  sort: AssetSort;
  overlapSort: OverlapSort;
  invalid: boolean;
}

const defaultDetailQuery: Omit<InvestorDetailQuery, "invalid"> = {
  filter: "all",
  sort: "latest",
  overlapSort: "name"
};

export function parseInvestorDetailQuery(search: string): InvestorDetailQuery {
  const params = new URLSearchParams(search);
  let invalid = false;
  const read = <T extends string>(key: string, allowed: readonly T[], fallback: T): T => {
    const value = params.get(key);
    if (!value) return fallback;
    if (allowed.includes(value as T)) return value as T;
    invalid = true;
    return fallback;
  };
  return {
    filter: read(
      "filter",
      ["all", "attention", "opinion", "repeated", "changed", "reversal", "shared_attention", "shared_opinion"],
      "all"
    ),
    sort: read("sort", ["latest", "first", "attention", "opinion", "name"], "latest"),
    overlapSort: read("overlap_sort", ["name", "attention", "opinion"], "name"),
    invalid
  };
}

function updateQuery(
  currentSearch: string,
  changes: Partial<Record<keyof typeof defaultDetailQuery, string | null>>
): string {
  const params = new URLSearchParams(currentSearch);
  for (const [key, value] of Object.entries(changes)) {
    const isDefault = value === defaultDetailQuery[key as keyof typeof defaultDetailQuery];
    if (value === null || value === "" || isDefault) params.delete(key);
    else params.set(key === "overlapSort" ? "overlap_sort" : key, value);
  }
  return params.toString();
}

export function InvestorDiscoveryPage({
  investors,
  loading,
  error,
  queryString,
  onOpenInvestor,
  onQueryChange
}: InvestorDiscoveryPageProps) {
  const params = new URLSearchParams(queryString);
  const query = params.get("q") ?? "";
  const normalized = query.trim().toLocaleLowerCase();
  const visible = investors.filter((investor) =>
    investor.investor_name.toLocaleLowerCase().includes(normalized)
  );

  if (loading) return <InvestorLoading />;
  if (error) {
    return (
      <div className="investor-state error-state">
        <div className="state-symbol error">!</div>
        <div className="eyebrow">INVESTOR INTELLIGENCE / READ-ONLY</div>
        <h1>API unavailable</h1>
        <p>The observed Investor catalog could not be reached. No Investor conclusion was inferred.</p>
      </div>
    );
  }

  const setSearch = (value: string) => {
    const next = new URLSearchParams(queryString);
    if (value) next.set("q", value);
    else next.delete("q");
    onQueryChange(next.toString());
  };

  return (
    <div className="investor-discovery-container">
      <header className="investor-discovery-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            INVESTOR INTELLIGENCE / OBSERVED EVIDENCE
          </div>
          <h1>Investor Intelligence</h1>
          <p>Select a monitored Investor to inspect observed Assets, Opinions, Thesis changes, and overlap.</p>
        </div>
        <div className="investor-boundary" role="note">
          <span>DATA BOUNDARY</span>
          <strong>Historical completeness: UNKNOWN</strong>
          <small>Collection provenance unavailable</small>
        </div>
      </header>

      <section className="investor-selector-panel" aria-label="Investor selector">
        <label htmlFor="investor-search">Search Investor name</label>
        <input
          id="investor-search"
          type="search"
          value={query}
          placeholder="Investor name"
          onChange={(event) => setSearch(event.target.value)}
        />
        <span>{visible.length} of {investors.length} observed Investors</span>
      </section>

      {visible.length ? (
        <div className="investor-list" aria-live="polite">
          {visible.map((investor) => (
            <button
              type="button"
              className="investor-list-card"
              key={investor.investor_id}
              aria-label={"Open Investor " + investor.investor_name}
              onClick={() => onOpenInvestor(investor.investor_id)}
            >
              <div className="investor-list-identity">
                <span>OBSERVED INVESTOR</span>
                <strong>{investor.investor_name}</strong>
              </div>
              <div><span>Attention Assets</span><strong>{investor.attention_asset_count}</strong></div>
              <div><span>Opinion Assets</span><strong>{investor.opinion_asset_count}</strong></div>
              <div><span>Latest observed</span><strong>{formatTime(investor.latest_observed_evidence_time)}</strong></div>
              <span className="investor-open-mark" aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="investor-empty">
          <div className="empty-mark">⌕</div>
          <h2>No observed Investors match this search.</h2>
          <p>Search uses Investor name only and does not rank results.</p>
        </div>
      )}
    </div>
  );
}

export function InvestorDetailPage({
  view,
  queryString,
  onOpenAsset,
  onOpenInvestor,
  onQueryChange
}: InvestorPageProps) {
  const query = useMemo(() => parseInvestorDetailQuery(queryString), [queryString]);
  const filteredAssets = useMemo(
    () => view.asset_views.filter((asset) => assetMatchesFilter(asset, query.filter)),
    [view.asset_views, query.filter]
  );
  const assets = useMemo(
    () => [...filteredAssets].sort((left, right) => compareAssetViews(left, right, query.sort)),
    [filteredAssets, query.sort]
  );
  const overlaps = useMemo(
    () => [...view.overlap_summaries].sort((left, right) => compareOverlaps(left, right, query.overlapSort)),
    [query.overlapSort, view.overlap_summaries]
  );
  const thesisAssets = useMemo(
    () =>
      [...view.asset_views]
        .filter((asset) => asset.thesis_change_count > 0)
        .sort(
          (left, right) =>
            right.thesis_change_count - left.thesis_change_count ||
            compareAssetViews(left, right, "name")
        )
        .slice(0, 5),
    [view.asset_views]
  );
  const sharedAssets = view.asset_views.filter(
    (asset) => asset.shared_attention_investor_count > 0 || asset.shared_opinion_investor_count > 0
  );
  const changeQuery = (changes: Partial<Record<keyof typeof defaultDetailQuery, string | null>>) =>
    onQueryChange(updateQuery(queryString, changes));

  return (
    <div className="investor-detail-container">
      <header className="investor-detail-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            INVESTOR INTELLIGENCE / OBSERVED EVIDENCE
          </div>
          <h1>{view.investor_name}</h1>
          <p>Observed Investor × Asset evidence over the current database window.</p>
        </div>
        <div className="investor-boundary" role="note">
          <span>DATA BOUNDARY</span>
          <strong>Historical completeness: UNKNOWN</strong>
          <small>Observed evidence only · Collection provenance unavailable</small>
        </div>
      </header>

      <div className="investor-window-line">
        Observed window: {formatTime(view.window_start)} — {formatTime(view.window_end)}
      </div>

      <section className="investor-metric-strip" aria-label="Investor observed evidence summary">
        <InvestorMetric label="Attention Assets" value={view.attention_asset_count} />
        <InvestorMetric label="Opinion Assets" value={view.opinion_asset_count} />
        <InvestorMetric label="Repeated Opinion Assets" value={view.repeated_opinion_asset_count} />
        <InvestorMetric label="Thesis Changed Assets" value={view.thesis_changed_asset_count} />
        <InvestorMetric label="Direction Reversal Assets" value={view.direction_reversal_asset_count} accent="coral" />
        <InvestorMetric label="Shared Attention Assets" value={view.shared_attention_asset_count} />
      </section>

      {query.invalid && (
        <div className="investor-query-note" role="status">Some Investor URL filter values were invalid and were ignored.</div>
      )}

      <section className="investor-breadth-panel">
        <InvestorSectionHeading title="Attention vs Opinion" subtitle="Observed breadth and structured viewpoint are separate evidence dimensions" />
        <div className="investor-breadth-content">
          <div><span>OBSERVED ATTENTION BREADTH</span><strong>{view.attention_asset_count} Assets</strong></div>
          <div className="breadth-divider">≠</div>
          <div><span>STRUCTURED OPINION BREADTH</span><strong>{view.opinion_asset_count} Assets</strong></div>
          <p>These counts describe observed evidence; they do not express research quality or importance.</p>
        </div>
      </section>

      <section className="investor-section investor-asset-section">
        <InvestorSectionHeading
          title="Observed Assets"
          subtitle="Asset rows preserve listing identity and existing cross-Investor states"
          action={<span className="investor-section-count">{assets.length} / {view.asset_views.length} ASSETS</span>}
        />
        <div className="investor-asset-controls" aria-label="Investor Asset filters">
          <label htmlFor="investor-asset-filter">Filter</label>
          <select id="investor-asset-filter" value={query.filter} onChange={(event) => changeQuery({ filter: event.target.value })}>
            <option value="all">All</option>
            <option value="attention">Attention only</option>
            <option value="opinion">Has Opinion</option>
            <option value="repeated">Repeated Opinion</option>
            <option value="changed">Thesis Changed</option>
            <option value="reversal">Direction Reversal</option>
            <option value="shared_attention">Shared Attention</option>
            <option value="shared_opinion">Shared Opinion</option>
          </select>
          <label htmlFor="investor-asset-sort">Sort by</label>
          <select id="investor-asset-sort" value={query.sort} onChange={(event) => changeQuery({ sort: event.target.value })}>
            <option value="latest">Latest observed</option>
            <option value="first">First observed</option>
            <option value="attention">Attention count</option>
            <option value="opinion">Opinion count</option>
            <option value="name">Asset name</option>
          </select>
          <span>Observed shared Asset count only</span>
        </div>
        {assets.length ? (
          <div className="investor-asset-list" aria-live="polite">
            {assets.map((asset) => (
              <InvestorAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />
            ))}
          </div>
        ) : (
          <div className="investor-inline-empty">No observed Asset evidence matches this filter.</div>
        )}
      </section>

      <section className="investor-dual-grid">
        <div className="investor-section investor-compact-panel">
          <InvestorSectionHeading title="Thesis Activity" subtitle="Deterministic fact summary; representatives sorted by ThesisChange count" />
          <div className="investor-activity-facts">
            <div><strong>{view.repeated_opinion_asset_count}</strong><span>Repeated Opinion Assets</span></div>
            <div><strong>{view.thesis_changed_asset_count}</strong><span>Thesis Changed Assets</span></div>
            <div><strong>{view.direction_reversal_asset_count}</strong><span>Direction Reversal Assets</span></div>
          </div>
          <div className="investor-mini-list">
            {thesisAssets.map((asset) => <InvestorMiniAsset asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />)}
          </div>
        </div>
        <div className="investor-section investor-compact-panel">
          <InvestorSectionHeading title="Shared Asset Context" subtitle="Assets also observed by other monitored Investors" />
          <div className="shared-context-summary">
            <div><strong>{view.shared_attention_asset_count}</strong><span>Shared Attention Assets</span></div>
            <div><strong>{view.shared_opinion_asset_count}</strong><span>Shared Opinion Assets</span></div>
          </div>
          <div className="investor-mini-list">
            {sharedAssets.slice(0, 5).map((asset) => <InvestorMiniAsset asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />)}
          </div>
        </div>
      </section>

      <section className="investor-section investor-overlap-section">
        <InvestorSectionHeading title="Observed Asset Overlap" subtitle="Set intersections with other monitored Investors; counts only" action={<span className="investor-section-count">{overlaps.length} OVERLAPPING INVESTORS</span>} />
        <div className="overlap-controls">
          <label htmlFor="overlap-sort">Overlap sort</label>
          <select id="overlap-sort" value={query.overlapSort} onChange={(event) => changeQuery({ overlapSort: event.target.value })}>
            <option value="name">Investor name</option>
            <option value="attention">Shared Attention count</option>
            <option value="opinion">Shared Opinion count</option>
          </select>
          <span>Observed shared Asset count</span>
        </div>
        {overlaps.length ? (
          <div className="overlap-list">
            {overlaps.map((overlap) => (
              <button
                type="button"
                className="overlap-row"
                key={overlap.other_investor_id}
                onClick={() => onOpenInvestor(overlap.other_investor_id)}
                aria-label={"Open Investor " + overlap.other_investor_name}
              >
                <strong>{overlap.other_investor_name}</strong>
                <span>Shared Attention <b>{overlap.shared_attention_asset_count}</b></span>
                <span>Shared Opinion <b>{overlap.shared_opinion_asset_count}</b></span>
                <span className="investor-open-mark" aria-hidden="true">↗</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="investor-inline-empty">No shared Asset overlap is present in this observed window.</div>
        )}
      </section>

      <section className="investor-section investor-quality-section">
        <InvestorSectionHeading title="Data Boundary / Data Quality" subtitle="Observed limitations are explicit and do not imply absence" />
        <div className="investor-quality-grid">
          <QualityFact label="Historical completeness" value="UNKNOWN" />
          <QualityFact label="Collection provenance" value="Unavailable" />
          <QualityFact label="Absence inference" value="Unsupported" />
          <QualityFact label="Latest direction" value="Latest observed only" />
          <QualityFact label="Opinion coverage" value={view.data_quality.opinion_coverage} />
          <QualityFact label="Missing Thesis comparison" value={String(view.data_quality.missing_thesis_comparison_count)} />
        </div>
      </section>

      <footer className="investor-footer">
        <span>Snowball Intelligence · observed Investor evidence</span>
        <span>Latest direction is the latest observed Opinion only.</span>
      </footer>
    </div>
  );
}

function assetMatchesFilter(asset: InvestorAssetIntelligenceSummary, filter: AssetFilter): boolean {
  if (filter === "all") return true;
  if (filter === "attention") return asset.attention_occurrence_count > 0;
  if (filter === "opinion") return asset.opinion_count > 0;
  if (filter === "repeated") return asset.opinion_count >= 2;
  if (filter === "changed") return asset.changed_count > 0;
  if (filter === "reversal") return asset.reversal_count > 0;
  if (filter === "shared_attention") return asset.attention_occurrence_count > 0 && asset.shared_attention_investor_count > 0;
  return asset.opinion_count > 0 && asset.shared_opinion_investor_count > 0;
}

function compareTime(left: string | null, right: string | null, ascending = false): number {
  if (left === right) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  const difference = new Date(left).getTime() - new Date(right).getTime();
  return ascending ? difference : -difference;
}

function compareAssetViews(left: InvestorAssetIntelligenceSummary, right: InvestorAssetIntelligenceSummary, sort: AssetSort): number {
  if (sort === "latest") {
    const result = compareTime(left.latest_evidence_time, right.latest_evidence_time);
    if (result) return result;
  } else if (sort === "first") {
    const result = compareTime(left.first_attention_time ?? left.first_opinion_time, right.first_attention_time ?? right.first_opinion_time, true);
    if (result) return result;
  } else if (sort === "attention" && left.attention_occurrence_count !== right.attention_occurrence_count) {
    return right.attention_occurrence_count - left.attention_occurrence_count;
  } else if (sort === "opinion" && left.opinion_count !== right.opinion_count) {
    return right.opinion_count - left.opinion_count;
  }
  return left.asset_name.localeCompare(right.asset_name, "zh-Hans") || left.market.localeCompare(right.market) || left.symbol.localeCompare(right.symbol) || left.asset_id.localeCompare(right.asset_id);
}

function compareOverlaps(left: InvestorIntelligenceView["overlap_summaries"][number], right: InvestorIntelligenceView["overlap_summaries"][number], sort: OverlapSort): number {
  if (sort === "attention" && left.shared_attention_asset_count !== right.shared_attention_asset_count) return right.shared_attention_asset_count - left.shared_attention_asset_count;
  if (sort === "opinion" && left.shared_opinion_asset_count !== right.shared_opinion_asset_count) return right.shared_opinion_asset_count - left.shared_opinion_asset_count;
  return left.other_investor_name.localeCompare(right.other_investor_name, "zh-Hans") || left.other_investor_id.localeCompare(right.other_investor_id);
}

function InvestorMetric({ label, value, accent }: { label: string; value: number; accent?: "coral" }) {
  return <div className={"investor-metric" + (accent ? " " + accent : "")}><span>{label}</span><strong>{value}</strong><small>Observed evidence</small></div>;
}

function InvestorSectionHeading({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) {
  return <div className="investor-section-heading"><div><h2>{title}</h2><span>{subtitle}</span></div>{action}</div>;
}

function InvestorAssetRow({ asset, onOpen }: { asset: InvestorAssetIntelligenceSummary; onOpen: (assetId: string) => void }) {
  const duplicateInsufficient = asset.alignment === "INSUFFICIENT_EVIDENCE" && asset.consensus === "INSUFFICIENT_EVIDENCE";
  return (
    <button type="button" className="investor-asset-row" onClick={() => onOpen(asset.asset_id)} aria-label={"Open Asset " + asset.asset_name + " " + asset.market + ":" + asset.symbol}>
      <div className="investor-asset-title"><strong>{asset.asset_name}</strong><span>{asset.market} · {asset.symbol}</span></div>
      <div className="investor-asset-cell attention-cell"><span>ATTENTION</span><strong>{asset.attention_occurrence_count} occurrences</strong><small>{formatTime(asset.first_attention_time)} → {formatTime(asset.latest_attention_time)}</small><EvidenceChips values={asset.attention_evidence_types} /></div>
      <div className="investor-asset-cell opinion-cell"><span>OPINION</span><strong>{asset.opinion_count} Opinions</strong><small>{formatTime(asset.first_opinion_time)} → {formatTime(asset.latest_opinion_time)}</small><DirectionPill direction={asset.latest_observed_direction} /></div>
      <div className="investor-asset-cell thesis-cell"><span>THESIS</span><strong>{asset.thesis_change_count} changes</strong><small>Changed {asset.changed_count} · Extended {asset.extended_count} · Reversal {asset.reversal_count}</small>{asset.missing_thesis_comparison_count > 0 && <em>{asset.missing_thesis_comparison_count} comparison unavailable</em>}</div>
      <div className="investor-asset-cell cross-cell"><span>CROSS-INVESTOR</span><strong>Attention {asset.attention_investor_count} · Opinion {asset.opinion_investor_count}</strong><small>Shared Attention {asset.shared_attention_investor_count} · Shared Opinion {asset.shared_opinion_investor_count}</small><div className="investor-state-badges">{asset.alignment && <StateBadge value={duplicateInsufficient ? "ALIGNMENT · " + labelFromEnum(asset.alignment) : labelFromEnum(asset.alignment)} tone="alignment" />}{asset.consensus && <StateBadge value={duplicateInsufficient ? "CONSENSUS · " + labelFromEnum(asset.consensus) : labelFromEnum(asset.consensus)} tone="consensus" />}</div></div>
      <span className="investor-open-mark" aria-hidden="true">↗</span>
    </button>
  );
}

function InvestorMiniAsset({ asset, onOpen }: { asset: InvestorAssetIntelligenceSummary; onOpen: (assetId: string) => void }) {
  return <button type="button" className="investor-mini-asset" onClick={() => onOpen(asset.asset_id)}><span><strong>{asset.asset_name}</strong><small>{asset.market} · {asset.symbol}</small></span><span>{asset.thesis_change_count ? asset.thesis_change_count + " changes" : "Shared"}</span><span className="investor-open-mark" aria-hidden="true">↗</span></button>;
}

function EvidenceChips({ values }: { values: EvidenceType[] }) {
  return <div className="investor-evidence-chips">{values.map((value) => <span className={"investor-evidence-chip " + value.toLowerCase()} key={value}>{evidenceLabel(value)}</span>)}</div>;
}

function DirectionPill({ direction }: { direction: InvestorAssetIntelligenceSummary["latest_observed_direction"] }) {
  return <span className={"investor-direction-pill " + directionClass(direction)}>{directionLabel(direction)}</span>;
}

function StateBadge({ value, tone }: { value: string; tone: "alignment" | "consensus" }) {
  return <span className={"investor-state-badge " + tone}>{value}</span>;
}

function QualityFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value.replaceAll("_", " ")}</strong></div>;
}

function labelFromEnum(value: string): string {
  return value.replaceAll("_", " ");
}

function InvestorLoading() {
  return <div className="investor-state investor-loading" aria-label="Loading Investor Intelligence"><div className="skeleton loading-investor-title" /><div className="skeleton loading-investor-panel" /><div className="skeleton loading-investor-list" /></div>;
}
