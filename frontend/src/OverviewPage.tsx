import { useMemo } from "react";

import type { AssetListItem } from "./types";
import { formatTime } from "./presentation";

interface OverviewPageProps {
  assets: AssetListItem[];
  loading: boolean;
  error: Error | null;
  onOpenAsset: (assetId: string) => void;
  onOpenDiscovery: (queryString: string) => void;
}

export function OverviewPage({
  assets,
  loading,
  error,
  onOpenAsset,
  onOpenDiscovery
}: OverviewPageProps) {
  const sharedAttentionAssets = useMemo(
    () => assets.filter((asset) => asset.attention_investor_count >= 2),
    [assets]
  );
  const multiOpinionAssets = useMemo(
    () => assets.filter((asset) => asset.opinion_investor_count >= 2),
    [assets]
  );
  const disagreementAssets = useMemo(
    () =>
      assets.filter(
        (asset) =>
          asset.latest_alignment === "MIXED_DIRECTION" ||
          asset.latest_consensus === "DIVERGENT"
      ),
    [assets]
  );
  const attentionGapAssets = useMemo(
    () => sortLatest(assets.filter((asset) => asset.attention_opinion_gap)).slice(0, 5),
    [assets]
  );
  const attentionGapCount = useMemo(
    () => assets.filter((asset) => asset.attention_opinion_gap).length,
    [assets]
  );
  const latestObservedAssets = useMemo(() => sortLatest(assets).slice(0, 8), [assets]);
  const repeatedThesisAssets = useMemo(
    () => assets.filter((asset) => asset.has_repeated_thesis),
    [assets]
  );
  const changedThesisAssets = useMemo(
    () => assets.filter((asset) => asset.has_thesis_changed),
    [assets]
  );
  const reversalAssets = useMemo(
    () => assets.filter((asset) => asset.has_direction_reversal),
    [assets]
  );
  const missingComparisonAssets = useMemo(
    () => assets.filter((asset) => asset.data_quality_flags.includes("MISSING_THESIS_COMPARISON")),
    [assets]
  );

  if (loading) return <OverviewLoading />;
  if (error) {
    return (
      <div className="overview-state error-state">
        <div className="state-symbol error">!</div>
        <div className="eyebrow">OBSERVED INTELLIGENCE / READ-ONLY</div>
        <h1>API unavailable</h1>
        <p>The observed evidence catalog could not be reached. No overview conclusion was inferred.</p>
      </div>
    );
  }

  const explore = (queryString: string) => onOpenDiscovery(queryString);

  return (
    <div className="overview-container">
      <header className="overview-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            OBSERVED INTELLIGENCE / UNIVERSE VIEW
          </div>
          <h1>Observed Intelligence Overview</h1>
          <p>Evidence patterns across the current monitored sample, ready to open in Asset Discovery.</p>
        </div>
        <div className="overview-boundary" role="note">
          <span>DATA BOUNDARY</span>
          <strong>Historical completeness: UNKNOWN</strong>
          <small>Observed evidence only</small>
        </div>
      </header>

      <section className="overview-summary" aria-label="Observed universe summary">
        <OverviewMetric label="Observed Assets" value={assets.length} note="Evidence-bearing" />
        <OverviewMetric label="Shared Attention" value={sharedAttentionAssets.length} note="2+ Investors" />
          <OverviewMetric label="Multi-Opinion" value={multiOpinionAssets.length} note="2+ Investors" />
          <OverviewMetric label="Direction Disagreement" value={disagreementAssets.length} note="Mixed or divergent" accent="coral" />
          <OverviewMetric label="Repeated Thesis" value={repeatedThesisAssets.length} note="Repeated timelines" accent="violet" />
      </section>

      <section className="overview-section">
        <OverviewSectionHeading
          number="01"
          title="Evidence Patterns"
          subtitle="Independent ways to browse existing evidence"
        />
        <div className="pattern-grid">
          <PatternCard
            title="Shared Attention"
            count={sharedAttentionAssets.length}
            explanation="Assets with Attention evidence from at least two monitored Investors."
            onExplore={() => explore("attention=2")}
          />
          <PatternCard
            title="Multi-Opinion"
            count={multiOpinionAssets.length}
            explanation="Assets with structured Opinions from at least two monitored Investors."
            onExplore={() => explore("opinion=2")}
          />
          <PatternCard
            title="Direction Disagreement"
            count={disagreementAssets.length}
            explanation="Assets with MIXED_DIRECTION or DIVERGENT observed evidence."
            onExplore={() => explore("cross=disagreement")}
          />
          <PatternCard
            title="Attention > Opinion"
            count={attentionGapCount}
            explanation="More monitored Investors have Attention evidence than structured Opinion evidence."
            onExplore={() => explore("gap=attention_gt_opinion")}
          />
          <PatternCard
            title="Repeated Thesis"
            count={repeatedThesisAssets.length}
            explanation="Assets with repeated Investor × Asset Thesis timelines."
            onExplore={() => explore("thesis=repeated")}
          />
        </div>
      </section>

      <section className="overview-section overview-disagreement-section">
        <OverviewSectionHeading
          number="02"
          title="Direction Disagreement"
          subtitle="Existing directional evidence, without a new score"
          action={<button type="button" className="overview-text-action" onClick={() => explore("cross=disagreement")}>Explore in Discovery →</button>}
        />
        <div className="disagreement-stat-row">
          <div><strong>{assets.filter((asset) => asset.latest_alignment === "MIXED_DIRECTION").length}</strong><span>MIXED_DIRECTION</span></div>
          <div><strong>{assets.filter((asset) => asset.latest_consensus === "DIVERGENT").length}</strong><span>DIVERGENT</span></div>
          <p>Latest observed Opinions may span multiple direction sides; this is observed evidence, not causality.</p>
        </div>
        {disagreementAssets.some((asset) => asset.latest_consensus === "DIVERGENT") ? (
          <div className="overview-asset-rows">
            {disagreementAssets
              .filter((asset) => asset.latest_consensus === "DIVERGENT")
              .map((asset) => (
                <OverviewAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} highlight="DIVERGENT" />
              ))}
          </div>
        ) : (
          <div className="overview-inline-note">No current DIVERGENT Asset is present in the observed sample.</div>
        )}
      </section>

      <section className="overview-section">
        <OverviewSectionHeading
          number="03"
          title="Latest Observed Assets"
          subtitle="Most recent observed evidence time, not a ranking"
        />
        <div className="overview-asset-rows latest-rows">
          {latestObservedAssets.map((asset) => (
            <OverviewAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />
          ))}
        </div>
      </section>

      <section className="overview-dual-grid">
        <div className="overview-section overview-compact-panel">
          <OverviewSectionHeading number="04" title="Thesis Evolution" subtitle="Observed repeated and changed timelines" />
          <div className="compact-fact-list">
            <CompactFact label="Repeated Thesis Assets" value={repeatedThesisAssets.length} />
            <CompactFact label="Thesis Changed Assets" value={changedThesisAssets.length} />
            <CompactFact label="Direction Reversal Assets" value={reversalAssets.length} />
          </div>
          <div className="compact-actions">
            <button type="button" onClick={() => explore("thesis=repeated")}>Explore Repeated Thesis →</button>
            <button type="button" onClick={() => explore("thesis=reversal")}>Explore Direction Reversal →</button>
          </div>
        </div>
        <div className="overview-section overview-compact-panel gap-panel">
          <OverviewSectionHeading number="05" title="Attention > Opinion" subtitle="Breadth and structured viewpoint are not the same" />
          <div className="gap-intro">
            <strong>{attentionGapCount} Assets</strong>
            <span>More monitored Investors have Attention evidence than structured Opinion evidence.</span>
          </div>
          <div className="overview-asset-rows compact-rows">
            {attentionGapAssets.map((asset) => (
              <OverviewAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} compact />
            ))}
          </div>
          <button type="button" className="overview-text-action" onClick={() => explore("gap=attention_gt_opinion")}>Explore all Attention &gt; Opinion →</button>
        </div>
      </section>

      <section className="overview-section overview-boundary-section">
        <OverviewSectionHeading number="Q" title="Data Boundary" subtitle="Limitations remain explicit and quiet" />
        <div className="boundary-facts">
          <div><span>Historical completeness</span><strong>UNKNOWN</strong></div>
          <div><span>Supported</span><strong>Presence / ordering evidence</strong></div>
          <div><span>Unsupported</span><strong>Absence inference</strong></div>
          <div><span>Direction label</span><strong>Latest observed only</strong></div>
        </div>
        <div className="gap-summary">
          <div>
            <span>DATA GAPS</span>
            <strong>Missing Thesis Comparison · {missingComparisonAssets.length}</strong>
          </div>
          {missingComparisonAssets.slice(0, 3).map((asset) => (
            <button type="button" key={asset.asset_id} onClick={() => onOpenAsset(asset.asset_id)}>
              {asset.asset_name} · {asset.market}:{asset.symbol} →
            </button>
          ))}
        </div>
      </section>

      <footer className="overview-footer">
        <span>Snowball Intelligence · observed evidence overview</span>
        <span>Open an Asset to inspect its complete evidence view.</span>
      </footer>
    </div>
  );
}

function sortLatest(assets: AssetListItem[]): AssetListItem[] {
  return [...assets].sort((left, right) => {
    const leftTime = left.latest_evidence_time ? new Date(left.latest_evidence_time).getTime() : -Infinity;
    const rightTime = right.latest_evidence_time ? new Date(right.latest_evidence_time).getTime() : -Infinity;
    return rightTime - leftTime || left.asset_name.localeCompare(right.asset_name, "zh-Hans") || left.market.localeCompare(right.market) || left.symbol.localeCompare(right.symbol);
  });
}

function OverviewMetric({
  label,
  value,
  note,
  accent
}: {
  label: string;
  value: number;
  note: string;
  accent?: "coral" | "violet";
}) {
  return (
    <div className={"overview-metric" + (accent ? " " + accent : "")}>
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{note}</small>
    </div>
  );
}

function PatternCard({
  title,
  count,
  explanation,
  onExplore
}: {
  title: string;
  count: number;
  explanation: string;
  onExplore: () => void;
}) {
  return (
    <article className="pattern-card">
      <div className="pattern-card-top"><span>OBSERVED PATTERN</span><span>{count} Assets</span></div>
      <h3>{title}</h3>
      <p>{explanation}</p>
      <button type="button" aria-label={"Explore " + title} onClick={onExplore}>Explore <span>→</span></button>
    </article>
  );
}

function OverviewAssetRow({
  asset,
  onOpen,
  highlight,
  compact = false
}: {
  asset: AssetListItem;
  onOpen: (assetId: string) => void;
  highlight?: string;
  compact?: boolean;
}) {
  const duplicateInsufficientCoverage =
    asset.latest_alignment === "INSUFFICIENT_EVIDENCE" &&
    asset.latest_consensus === "INSUFFICIENT_EVIDENCE";
  const dataGap = asset.data_quality_flags.includes("MISSING_THESIS_COMPARISON");
  return (
    <button
      type="button"
      className={"overview-asset-row" + (compact ? " compact" : "")}
      onClick={() => onOpen(asset.asset_id)}
      aria-label={"Open " + asset.asset_name + " " + asset.market + ":" + asset.symbol}
    >
      <div className="overview-asset-identity">
        <strong>{asset.asset_name}</strong>
        <span>{asset.market} · {asset.symbol}</span>
      </div>
      <div className="overview-asset-evidence">
        <span>Latest observed</span>
        <strong>{formatTime(asset.latest_evidence_time)}</strong>
      </div>
      <div className="overview-asset-breadth">
        <span>Attention <b>{asset.attention_investor_count}</b></span>
        <span>Opinion <b>{asset.opinion_investor_count}</b></span>
      </div>
      {!compact && (
        <div className="overview-asset-badges">
          {highlight && <FactBadge value={highlight} tone="coral" />}
          {asset.latest_alignment && (
            <FactBadge
              value={duplicateInsufficientCoverage ? "ALIGNMENT · " + labelFromEnum(asset.latest_alignment) : labelFromEnum(asset.latest_alignment)}
              tone="alignment"
            />
          )}
          {asset.latest_consensus && (
            <FactBadge
              value={duplicateInsufficientCoverage ? "CONSENSUS · " + labelFromEnum(asset.latest_consensus) : labelFromEnum(asset.latest_consensus)}
              tone="consensus"
            />
          )}
          {asset.attention_opinion_gap && <FactBadge value="ATTENTION > OPINION" tone="gap" />}
          {asset.has_repeated_thesis && <FactBadge value="REPEATED THESIS" tone="thesis" />}
          {asset.has_direction_reversal && <FactBadge value="DIRECTION REVERSAL" tone="reversal" />}
          {dataGap && <FactBadge value="DATA GAP" tone="gap" />}
        </div>
      )}
      <span className="overview-open-mark" aria-hidden="true">↗</span>
    </button>
  );
}

function CompactFact({ label, value }: { label: string; value: number }) {
  return <div><strong>{value}</strong><span>{label}</span></div>;
}

function FactBadge({ value, tone }: { value: string; tone: "alignment" | "consensus" | "gap" | "thesis" | "reversal" | "coral" }) {
  return <span className={"overview-badge " + tone}>{value}</span>;
}

function labelFromEnum(value: string): string {
  return value.replaceAll("_", " ");
}

function OverviewSectionHeading({
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
    <div className="overview-section-heading">
      <div>
        <span className="overview-section-number">{number}</span>
        <div><h2>{title}</h2><span>{subtitle}</span></div>
      </div>
      {action}
    </div>
  );
}

function OverviewLoading() {
  return (
    <div className="overview-container overview-loading" aria-label="Loading Observed Intelligence Overview">
      <div className="skeleton loading-overview-title" />
      <div className="loading-overview-summary">
        {[1, 2, 3, 4, 5].map((item) => <div className="skeleton" key={item} />)}
      </div>
      <div className="skeleton loading-overview-patterns" />
    </div>
  );
}
