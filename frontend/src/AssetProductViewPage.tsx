import type { MouseEvent } from "react";

import type { AssetIntelligenceView, AttentionClass, ProductEvolutionStep } from "./types";
import { formatTime, shortId } from "./presentation";

interface AssetProductViewPageProps {
  view: AssetIntelligenceView;
  investorNames?: Record<string, string>;
  onOpenInvestor: (investorId: string) => void;
}

const reviewLabels: Record<AttentionClass, string> = {
  IMMEDIATE_REVIEW: "Immediate review",
  ACTIVE_REVIEW: "Active review",
  BACKGROUND_MONITORING: "Background monitoring",
  LIMITED_CONTEXT: "Limited context"
};

const reviewDescriptions: Record<AttentionClass, string> = {
  IMMEDIATE_REVIEW: "Explicit change evidence is present for human review.",
  ACTIVE_REVIEW: "Current Product discovery evidence is available for human review.",
  BACKGROUND_MONITORING: "Historical Intelligence is present without current discovery eligibility.",
  LIMITED_CONTEXT: "The observed evidence boundary is too limited for a higher review class."
};

const reasonLabels: Record<string, string> = {
  CONSENSUS_STATE_CHANGE: "Consensus state change observed",
  CONSENSUS_FRAGMENTATION: "Consensus fragmentation evidence",
  MULTI_INVESTOR_EXPANSION: "Multiple investors observed",
  THESIS_TRANSITION: "Material thesis transition observed",
  HIGH_PRIORITY_EVIDENCE: "High Priority evidence",
  ACTIVE_INTELLIGENCE: "Current discovery evidence available",
  HISTORICAL_INTELLIGENCE: "Historical Intelligence observed",
  LIMITED_CONTEXT: "Context is limited"
};

const discoveryReasonLabels: Record<string, string> = {
  MULTI_INVESTOR_ACTIVITY: "Multiple-investor activity",
  THESIS_ACTIVITY: "Thesis activity",
  CROSS_INVESTOR_ACTIVITY: "Cross-investor activity",
  CONSENSUS_ACTIVITY: "Consensus activity"
};

export function AssetProductViewPage({
  view,
  investorNames = {},
  onOpenInvestor
}: AssetProductViewPageProps) {
  const reviewClass = view.review.attention_class.toLowerCase();
  const visibleSteps = [...view.evolution.recent_steps].sort(
    (left, right) => new Date(left.observed_at).getTime() - new Date(right.observed_at).getTime()
  );
  const hasHistoricalIntelligence = view.evolution.step_count > 0;

  return (
    <div className="product-page page-container">
      <header className="product-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            ASSET INTELLIGENCE / PRODUCT VIEW
          </div>
          <div className="asset-title-row">
            <h1>{view.asset.name}</h1>
            <span className="listing-badge">
              {view.asset.market} <i>·</i> {view.asset.symbol}
            </span>
          </div>
          <p className="asset-subtitle">
            Observed Intelligence workspace for this listing. Review priority is not an investment rating.
          </p>
        </div>
        <div className={"product-review-card " + reviewClass} role="status">
          <span className="product-review-label">REVIEW PRIORITY</span>
          <strong>{reviewLabels[view.review.attention_class]}</strong>
          <small>{reviewDescriptions[view.review.attention_class]}</small>
          <em>Human review priority · not investment rating</em>
        </div>
      </header>

      {!view.discovery.is_discoverable && hasHistoricalIntelligence && (
        <div className="product-history-note" role="note">
          <strong>Historical Intelligence is available.</strong>
          <span>This Asset is not currently eligible for the Discovery Feed.</span>
        </div>
      )}

      <section className="product-section product-why-section">
        <ProductHeading number="01" title="Why this Asset is surfaced" subtitle="Existing evidence only" />
        <div className="product-chip-row">
          {view.review.reasons.map((reason) => (
            <span className="product-chip review-chip" key={"review-" + reason}>
              {reasonLabels[reason] ?? formatEnum(reason)}
            </span>
          ))}
          {view.discovery.discovery_reasons.map((reason) => (
            <span className="product-chip discovery-chip" key={"discovery-" + reason}>
              {discoveryReasonLabels[reason] ?? formatEnum(reason)}
            </span>
          ))}
          {view.current_state.patterns.map((pattern) => (
            <span className="product-chip pattern-chip" key={"pattern-" + pattern}>
              {formatEnum(pattern)}
            </span>
          ))}
          {!view.review.reasons.length && !view.discovery.discovery_reasons.length && (
            <span className="product-muted">No higher-level review trigger is present.</span>
          )}
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="02" title="Current Intelligence State" subtitle="Alignment and Consensus remain independent" />
        <div className="product-state-grid">
          <StateCard
            label="Directional Alignment"
            value={view.current_state.alignment}
            description={alignmentDescription(view.current_state.alignment)}
            tone="alignment"
          />
          <StateCard
            label="Consensus Evidence"
            value={view.current_state.consensus}
            description={consensusDescription(view.current_state.consensus)}
            tone="consensus"
          />
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="03" title="Observed Breadth" subtitle="Investor participation and current evidence counts" />
        <div className="product-stat-grid">
          <ProductStat label="Investors in current context" value={view.context.investor_context.current_investor_count} />
          <ProductStat label="Attention evidence" value={view.context.attention_context.current_attention_count} />
          <ProductStat label="Thesis changes" value={view.context.thesis_context.current_thesis_changes} />
          <ProductStat label="Signals in current context" value={view.context.activity_context.current_signal_count} />
        </div>
        <div className="product-context-note">
          <span>{view.discovery.activity_summary ? "Discovery activity" : "Historical evidence"}</span>
          <strong>
            {view.discovery.activity_summary
              ? view.discovery.activity_summary.investor_count + " monitored investor(s)"
              : "No current Discovery candidate"}
          </strong>
        </div>
      </section>

      <section className="product-section product-narrative-section">
        <ProductHeading number="04" title="Narrative" subtitle="Deterministic summary of observed evidence" />
        <div className="product-narrative">
          <h2>{view.narrative.headline}</h2>
          <p>{view.narrative.summary}</p>
          <details className="product-narrative-details">
            <summary>Show narrative detail</summary>
            <div className="product-narrative-grid">
              <NarrativeFact label="Attention" value={view.narrative.attention_summary} />
              <NarrativeFact label="Thesis" value={view.narrative.thesis_summary} />
              <NarrativeFact label="Cross-Investor" value={view.narrative.cross_investor_summary} />
              <NarrativeFact label="Consensus" value={view.narrative.consensus_summary} />
            </div>
          </details>
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="05" title="Observed Context" subtitle="Fact-time window comparison" />
        <div className="product-context-grid">
          <ContextFact label="Activity" value={view.context.activity_context.change_description} />
          <ContextFact label="Investors" value={view.context.investor_context.current_investor_count + " current · " + view.context.investor_context.previous_investor_count + " previous observed"} />
          <ContextFact label="Attention" value={view.context.attention_context.change_description} />
          <ContextFact label="Thesis" value={view.context.thesis_context.current_thesis_changes + " current · " + view.context.thesis_context.historical_thesis_changes + " previous observed"} />
        </div>
        <div className="product-comparison-note">
          Historical comparison is unavailable as a completeness claim. Previous-window counts are observed counts only.
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="06" title="Recent Evolution" subtitle={view.evolution.step_count > visibleSteps.length ? "Recent steps from the fact-time timeline" : "Fact-time ordered evidence"} />
        <div className="product-evolution-meta">
          <span>
            {formatTime(view.evolution.timeline_range.first_observed_at)} →{" "}
            {formatTime(view.evolution.timeline_range.latest_observed_at)}
          </span>
          <strong>{view.evolution.step_count} total steps</strong>
        </div>
        {visibleSteps.length ? (
          <div className="product-evolution-list">
            {visibleSteps.map((step) => (
              <EvolutionRow
                key={step.step_id}
                step={step}
                investorNames={investorNames}
                onOpenInvestor={onOpenInvestor}
              />
            ))}
          </div>
        ) : (
          <div className="product-empty-section">No Evolution steps are available for this Asset.</div>
        )}
      </section>

      <section className="product-section">
        <ProductHeading number="07" title="Feed and Event Lifecycle" subtitle="Lifecycle state is not current investor activity" />
        <div className="product-lifecycle-grid">
          <LifecycleCard title="Feed lifecycle" summary={view.feed} />
          <LifecycleCard title="Event lifecycle" summary={view.events} />
        </div>
        <p className="product-lifecycle-note">
          ACTIVE here describes lifecycle/presentation state only. It does not mean investors are discussing this Asset now.
        </p>
      </section>

      <section className="product-section product-quality-section">
        <ProductHeading number="Q" title="Data Quality" subtitle="Boundaries are explicit, not error states" />
        <div className="product-quality-grid">
          <QualityFact label="Historical completeness" value={view.data_quality.historical_completeness} />
          <QualityFact label="Historical comparison" value={view.data_quality.historical_comparison_supported ? "Supported" : "Unavailable"} />
          <QualityFact label="Absence inference" value={view.data_quality.absence_inference_supported ? "Supported" : "Unsupported"} />
        </div>
        <ul className="product-limitations">
          {view.data_quality.limitations.map((limitation) => <li key={limitation}>{limitation}</li>)}
        </ul>
      </section>

      <section className="product-section product-traceability-section">
        <ProductHeading number="T" title="Evidence Traceability" subtitle="References to persisted source artifacts" />
        <div className="product-traceability-stats">
          <ProductStat label="Evidence references" value={view.traceability_summary.source_ref_count} />
          <ProductStat label="Canonical sources" value={view.traceability_summary.canonical_source_count} />
          <ProductStat label="Signals" value={view.traceability_summary.signal_count} />
        </div>
        <details className="product-evidence-details">
          <summary>Show evidence source references</summary>
          <div className="product-evidence-list">
            {view.traceability_summary.evidence_refs.map((reference) => (
              <div key={reference.source_type + ":" + reference.source_id}>
                <span>{reference.source_type}</span>
                <code title={reference.source_id}>{reference.source_id.slice(0, 8)}…</code>
              </div>
            ))}
          </div>
        </details>
      </section>
    </div>
  );
}

function ProductHeading({ number, title, subtitle }: { number: string; title: string; subtitle: string }) {
  return (
    <div className="product-section-heading">
      <div>
        <span>{number}</span>
        <div><h2>{title}</h2><small>{subtitle}</small></div>
      </div>
    </div>
  );
}

function StateCard({ label, value, description, tone }: { label: string; value: string | null; description: string; tone: "alignment" | "consensus" }) {
  return (
    <div className={"product-state-card " + tone}>
      <span>{label}</span>
      <strong>{value ? formatEnum(value) : "No current state"}</strong>
      <p>{description}</p>
    </div>
  );
}

function ProductStat({ label, value }: { label: string; value: number }) {
  return <div className="product-stat"><span>{label}</span><strong>{value}</strong></div>;
}

function NarrativeFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><p>{value}</p></div>;
}

function ContextFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{value}</strong></div>;
}

function EvolutionRow({
  step,
  investorNames,
  onOpenInvestor
}: {
  step: ProductEvolutionStep;
  investorNames: Record<string, string>;
  onOpenInvestor: (investorId: string) => void;
}) {
  const investorName = step.investor_id ? investorNames[step.investor_id] : null;
  const investorLabel = investorName ?? "Investor ID " + shortId(step.investor_id);
  const handleInvestorClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    if (step.investor_id) onOpenInvestor(step.investor_id);
  };
  return (
    <article className="product-evolution-row">
      <div className="product-evolution-time">{formatTime(step.observed_at)}</div>
      <div className="product-evolution-marker" />
      <div>
        <span className="product-evolution-type">{formatEnum(step.step_type)}</span>
        <h3>{step.title}</h3>
        {step.investor_id && (
          <a
            className="product-investor-link"
            href={`/investors/${encodeURIComponent(step.investor_id)}`}
            onClick={handleInvestorClick}
            aria-label={`Open Investor ${investorLabel}`}
          >
            Investor observed · {investorLabel}
          </a>
        )}
        <ul>{step.facts.map((fact) => <li key={fact}>{fact}</li>)}</ul>
      </div>
    </article>
  );
}

function LifecycleCard({ title, summary }: { title: string; summary: { active_count: number; states: Record<string, number> } }) {
  return (
    <div className="product-lifecycle-card">
      <span>{title}</span>
      <strong>{summary.active_count} ACTIVE</strong>
      <div>{Object.entries(summary.states).map(([state, count]) => <small key={state}>{formatEnum(state)} · {count}</small>)}</div>
    </div>
  );
}

function QualityFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{formatEnum(value)}</strong></div>;
}

function alignmentDescription(value: string | null): string {
  if (value === "MIXED_DIRECTION") return "Observed Opinions span multiple direction sides.";
  if (value === "INSUFFICIENT_EVIDENCE") return "Observed Opinion coverage is insufficient for Alignment.";
  return value ? "Existing Alignment evidence for this observed window." : "No current cross-investor Alignment state.";
}

function consensusDescription(value: string | null): string {
  if (value === "DIVERGENT") return "Persisted Consensus evidence reports direct directional divergence.";
  if (value === "INSUFFICIENT_EVIDENCE") return "Coverage is insufficient for a Consensus classification.";
  return value ? "Existing Consensus evidence for this observed window." : "No current Consensus evidence.";
}

function formatEnum(value: string): string {
  return value.replaceAll("_", " ");
}
