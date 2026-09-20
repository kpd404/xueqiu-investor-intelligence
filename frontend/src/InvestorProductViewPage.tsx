import type {
  InvestorAssetIntelligenceProductView,
  InvestorProductActivityEvent,
  InvestorProductView
} from "./types";
import {
  directionClass,
  directionLabel,
  evidenceLabel,
  formatTime,
  shortId,
  thesisLabel
} from "./presentation";

interface InvestorProductViewPageProps {
  view: InvestorProductView;
  onOpenAsset: (assetId: string) => void;
}

export function InvestorProductViewPage({ view, onOpenAsset }: InvestorProductViewPageProps) {
  const thesisAssets = [...view.asset_views]
    .filter((item) => item.thesis.thesis_change_count > 0)
    .sort((left, right) => compareTimes(left.thesis.latest_change_at, right.thesis.latest_change_at));
  const activity = [...view.recent_activity].sort(
    (left, right) => new Date(left.observed_at).getTime() - new Date(right.observed_at).getTime()
  );

  return (
    <div className="investor-detail-container investor-product-page">
      <header className="investor-detail-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            INVESTOR INTELLIGENCE / PRODUCT VIEW
          </div>
          <h1>{view.investor.name}</h1>
          <p>
            Observed Attention, persisted Opinion and Thesis evidence for one Investor. This is a
            read-only evidence workspace; it does not evaluate Investor quality.
          </p>
        </div>
        <div className="investor-boundary">
          <span>INVESTOR IDENTITY</span>
          <strong>{view.investor.source_platform}</strong>
          <small>{view.investor.source_user_id} · {shortId(view.investor.investor_id)}</small>
        </div>
      </header>

      <div className="investor-window-line">
        Effective observed window: {formatTime(view.window_start)} → {formatTime(view.window_end)}
      </div>

      <section className="investor-metric-strip" aria-label="Investor intelligence summary">
        <Metric label="Observed assets" value={view.summary.observed_asset_count} />
        <Metric label="Opinion assets" value={view.summary.opinion_asset_count} />
        <Metric label="Attention-only assets" value={view.coverage.attention_only_assets.length} />
        <Metric label="Attention occurrences" value={view.summary.attention_occurrence_count} />
        <Metric label="Opinions" value={view.summary.opinion_count} />
        <Metric label="Thesis changes" value={view.summary.thesis_change_count} accent="coral" />
      </section>

      <section className="investor-product-note" role="note">
        <strong>Observed Attention is distinct from persisted Opinion.</strong>
        <span>
          Counts describe recorded artifacts only. Attention-only means no effective persisted Opinion
          is present in this read scope; it does not describe the Investor&apos;s view.
        </span>
      </section>

      <section className="investor-section investor-product-coverage-section">
        <SectionHeading
          title="Coverage by evidence type"
          subtitle="The same Asset can be observed, have an Opinion, or remain Attention-only."
        />
        <div className="investor-product-coverage-grid">
          <CoverageCard title="Observed Assets" assets={view.coverage.observed_assets} onOpen={onOpenAsset} />
          <CoverageCard title="Opinion Assets" assets={view.coverage.opinion_assets} onOpen={onOpenAsset} />
          <CoverageCard title="Attention-only Assets" assets={view.coverage.attention_only_assets} onOpen={onOpenAsset} />
        </div>
      </section>

      <section className="investor-section investor-asset-section">
        <SectionHeading
          title="Asset intelligence"
          subtitle="Latest direction comes only from the latest effective persisted Opinion."
          count={view.asset_views.length + " assets"}
        />
        {view.asset_views.length ? (
          <div className="investor-asset-list">
            {view.asset_views.map((asset) => (
              <InvestorAssetProductRow key={asset.asset.asset_id} asset={asset} onOpen={onOpenAsset} />
            ))}
          </div>
        ) : (
          <div className="investor-inline-empty">
            No effective Attention, Opinion or Thesis artifacts are available in this read scope.
          </div>
        )}
      </section>

      <div className="investor-dual-grid">
        <section className="investor-section">
          <SectionHeading
            title="Recent Thesis changes"
            subtitle="Persisted ThesisChange semantics, ordered by fact time."
            count={thesisAssets.length + " assets"}
          />
          {thesisAssets.length ? (
            <div className="investor-product-thesis-list">
              {thesisAssets.map((asset) => (
                <button
                  type="button"
                  className="investor-product-thesis-row"
                  key={asset.asset.asset_id}
                  onClick={() => onOpenAsset(asset.asset.asset_id)}
                >
                  <span>
                    <strong>{asset.asset.name}</strong>
                    <small>{asset.asset.market}:{asset.asset.symbol}</small>
                  </span>
                  <b>{asset.thesis.latest_change_type ? thesisLabel(asset.thesis.latest_change_type) : "—"}</b>
                  <small>{formatTime(asset.thesis.latest_change_at)}</small>
                </button>
              ))}
            </div>
          ) : (
            <div className="investor-inline-empty">No ThesisChange artifact is available.</div>
          )}
        </section>

        <section className="investor-section">
          <SectionHeading
            title="Recent activity"
            subtitle="Attention, Opinion and Thesis artifacts in fact-time order."
            count={activity.length + " events"}
          />
          {activity.length ? (
            <div className="investor-product-activity-list">
              {activity.map((event, index) => (
                <ActivityRow key={activityKey(event, index)} event={event} onOpen={onOpenAsset} />
              ))}
            </div>
          ) : (
            <div className="investor-inline-empty">No recent activity is available.</div>
          )}
        </section>
      </div>

      <section className="investor-section investor-quality-section">
        <SectionHeading title="Data quality" subtitle="Coverage boundaries are explicit, not error states." />
        <div className="investor-quality-grid">
          <QualityFact label="Historical completeness" value={view.data_quality.historical_completeness} />
          <QualityFact
            label="Historical comparison"
            value={view.data_quality.historical_comparison_supported ? "Supported" : "Unsupported"}
          />
          <QualityFact
            label="Absence inference"
            value={view.data_quality.absence_inference_supported ? "Supported" : "Unsupported"}
          />
        </div>
        <ul className="investor-product-limitations">
          {view.data_quality.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      </section>

      <section className="investor-section investor-quality-section">
        <SectionHeading title="Evidence traceability" subtitle="References to canonical persisted artifacts." />
        <div className="investor-product-traceability-grid">
          <QualityFact label="Attention references" value={String(view.traceability_summary.attention_occurrence_ref_count)} />
          <QualityFact label="RawEvent references" value={String(view.traceability_summary.raw_event_ref_count)} />
          <QualityFact label="Opinion references" value={String(view.traceability_summary.opinion_ref_count)} />
          <QualityFact label="ThesisChange references" value={String(view.traceability_summary.thesis_change_ref_count)} />
          <QualityFact label="Activity source references" value={String(view.traceability_summary.activity_source_ref_count)} />
        </div>
        <details className="investor-product-evidence-details">
          <summary>Show source references</summary>
          <div className="investor-product-source-list">
            {view.asset_views.flatMap((asset) => [
              ...asset.traceability.attention_occurrence_ids.map((id) => ({ type: "AttentionOccurrence", id, asset })),
              ...asset.traceability.raw_event_ids.map((id) => ({ type: "RawEvent", id, asset })),
              ...asset.traceability.opinion_ids.map((id) => ({ type: "Opinion", id, asset })),
              ...asset.traceability.thesis_change_ids.map((id) => ({ type: "ThesisChange", id, asset }))
            ]).map((reference) => (
              <div key={reference.type + ":" + reference.id}>
                <span>{reference.type} · {reference.asset.asset.name}</span>
                <code title={reference.id}>{shortId(reference.id)}</code>
              </div>
            ))}
          </div>
        </details>
      </section>

      <footer className="investor-footer">
        <span>Read-only Investor Product View · query-time composition</span>
        <span>Latest observed artifact: {formatTime(view.summary.latest_observed_at)}</span>
      </footer>
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: number; accent?: "coral" }) {
  return <div className={"investor-metric" + (accent ? " " + accent : "")}><span>{label}</span><strong>{value}</strong><small>Recorded artifacts</small></div>;
}

function SectionHeading({ title, subtitle, count }: { title: string; subtitle: string; count?: string }) {
  return (
    <div className="investor-section-heading">
      <div><h2>{title}</h2><span>{subtitle}</span></div>
      {count && <span className="investor-section-count">{count}</span>}
    </div>
  );
}

function CoverageCard({
  title,
  assets,
  onOpen
}: {
  title: string;
  assets: InvestorProductView["coverage"]["observed_assets"];
  onOpen: (assetId: string) => void;
}) {
  return (
    <div className="investor-product-coverage-card">
      <div><span>{title}</span><strong>{assets.length}</strong></div>
      <div className="investor-product-coverage-assets">
        {assets.slice(0, 8).map((asset) => (
          <button type="button" key={asset.asset_id} onClick={() => onOpen(asset.asset_id)}>
            {asset.name} <small>{asset.market}:{asset.symbol}</small>
          </button>
        ))}
        {assets.length > 8 && <small>+{assets.length - 8} more in Asset intelligence</small>}
      </div>
    </div>
  );
}

function InvestorAssetProductRow({
  asset,
  onOpen
}: {
  asset: InvestorAssetIntelligenceProductView;
  onOpen: (assetId: string) => void;
}) {
  return (
    <button type="button" className="investor-asset-row" onClick={() => onOpen(asset.asset.asset_id)}>
      <div className="investor-asset-title">
        <strong>{asset.asset.name}</strong>
        <span>{asset.asset.market}:{asset.asset.symbol}</span>
      </div>
      <div className="investor-asset-cell attention-cell">
        <span>ATTENTION</span>
        <strong>{asset.attention.occurrence_count} occurrence{asset.attention.occurrence_count === 1 ? "" : "s"}</strong>
        <small>{formatTime(asset.attention.latest_observed_at)}</small>
        <div className="investor-evidence-chips">
          {asset.attention.evidence_types.map((evidence) => <em className="investor-evidence-chip" key={evidence}>{evidenceLabel(evidence)}</em>)}
        </div>
      </div>
      <div className="investor-asset-cell opinion-cell">
        <span>PERSISTED OPINION</span>
        <strong>{asset.opinion.opinion_count} record{asset.opinion.opinion_count === 1 ? "" : "s"}</strong>
        <span className={"investor-direction-pill " + directionClass(asset.opinion.latest_direction)}>
          {asset.opinion.latest_direction
            ? directionLabel(asset.opinion.latest_direction)
            : "No persisted Opinion"}
        </span>
        <small>{formatTime(asset.opinion.latest_opinion_at)}</small>
      </div>
      <div className="investor-asset-cell thesis-cell">
        <span>THESIS</span>
        <strong>{asset.thesis.thesis_change_count} change{asset.thesis.thesis_change_count === 1 ? "" : "s"}</strong>
        <small>{asset.thesis.latest_change_type ? thesisLabel(asset.thesis.latest_change_type) : "No ThesisChange"}</small>
        <small>{formatTime(asset.thesis.latest_change_at)}</small>
      </div>
      <div className="investor-asset-cell cross-cell">
        <span>RELATIONSHIP</span>
        <strong>{asset.relationship.attention_only ? "Attention-only" : asset.relationship.has_opinion ? "Attention + Opinion" : "Thesis evidence"}</strong>
        <small>Latest observed {formatTime(asset.latest_observed_at)}</small>
      </div>
      <span className="investor-open-mark" aria-hidden="true">→</span>
    </button>
  );
}

function ActivityRow({ event, onOpen }: { event: InvestorProductActivityEvent; onOpen: (assetId: string) => void }) {
  return (
    <button type="button" className="investor-product-activity-row" onClick={() => onOpen(event.asset.asset_id)}>
      <span className="investor-product-activity-time">{formatTime(event.observed_at)}</span>
      <span className="investor-product-activity-type">{activityLabel(event.event_type)}</span>
      <strong>{event.asset.name}</strong>
      <small>{event.asset.market}:{event.asset.symbol} · {event.source_refs.length} source refs</small>
    </button>
  );
}

function QualityFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function activityLabel(value: InvestorProductActivityEvent["event_type"]): string {
  if (value === "ATTENTION_OBSERVED") return "Attention observed";
  if (value === "OPINION_RECORDED") return "Opinion recorded";
  return "Thesis change observed";
}

function activityKey(event: InvestorProductActivityEvent, index: number): string {
  return event.event_type + ":" + event.asset.asset_id + ":" + event.observed_at + ":" + index;
}

function compareTimes(left: string | null, right: string | null): number {
  return (right ? new Date(right).getTime() : Number.NEGATIVE_INFINITY) -
    (left ? new Date(left).getTime() : Number.NEGATIVE_INFINITY);
}
