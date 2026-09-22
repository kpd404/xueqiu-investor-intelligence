import type { MouseEvent } from "react";

import type { AssetIntelligenceView, AttentionClass, ProductEvolutionStep } from "./types";
import { displayText, formatEnum as localizedEnum, formatTime, localizeText, shortId } from "./presentation";

interface AssetProductViewPageProps {
  view: AssetIntelligenceView;
  investorNames?: Record<string, string>;
  onOpenInvestor: (investorId: string) => void;
}

const reviewLabels: Record<AttentionClass, string> = {
  IMMEDIATE_REVIEW: "优先复核",
  ACTIVE_REVIEW: "持续复核",
  BACKGROUND_MONITORING: "背景观察",
  LIMITED_CONTEXT: "背景有限"
};

const reviewDescriptions: Record<AttentionClass, string> = {
  IMMEDIATE_REVIEW: "存在明确的变化证据，建议人工复核。",
  ACTIVE_REVIEW: "存在当前产品发现证据，建议人工复核。",
  BACKGROUND_MONITORING: "存在历史情报，但当前不满足发现条件。",
  LIMITED_CONTEXT: "已观察证据范围有限，无法提升复核等级。"
};

const reasonLabels: Record<string, string> = {
  CONSENSUS_STATE_CHANGE: "观察到共识状态变化",
  CONSENSUS_FRAGMENTATION: "共识分化证据",
  MULTI_INVESTOR_EXPANSION: "多位投资者已观察",
  THESIS_TRANSITION: "观察到实质性投资逻辑转变",
  HIGH_PRIORITY_EVIDENCE: "高优先级证据",
  ACTIVE_INTELLIGENCE: "存在当前发现证据",
  HISTORICAL_INTELLIGENCE: "观察到历史情报",
  LIMITED_CONTEXT: "背景有限"
};

const discoveryReasonLabels: Record<string, string> = {
  MULTI_INVESTOR_ACTIVITY: "多投资者活动",
  THESIS_ACTIVITY: "投资逻辑活动",
  CROSS_INVESTOR_ACTIVITY: "跨投资者活动",
  CONSENSUS_ACTIVITY: "共识活动"
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
            标的情报 / 产品视图
          </div>
          <div className="asset-title-row">
            <h1>{view.asset.name}</h1>
            <span className="listing-badge">
              {view.asset.market} <i>·</i> {view.asset.symbol}
            </span>
          </div>
          <p className="asset-subtitle">
            该标的的已观察情报工作区。研究复核优先级不代表投资评级。
          </p>
        </div>
        <div className={"product-review-card " + reviewClass} role="status">
          <span className="product-review-label">研究复核优先级</span>
          <strong>{reviewLabels[view.review.attention_class]}</strong>
          <small>{reviewDescriptions[view.review.attention_class]}</small>
          <em>研究复核优先级 · 不代表投资评级</em>
        </div>
      </header>

      {!view.discovery.is_discoverable && hasHistoricalIntelligence && (
        <div className="product-history-note" role="note">
          <strong>已有历史情报。</strong>
          <span>该标的当前不符合情报发现流条件。</span>
        </div>
      )}

      <section className="product-section product-why-section">
        <ProductHeading number="01" title="该标的为何被呈现" subtitle="仅展示已有证据" />
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
            <span className="product-muted">暂无更高层级的研究触发因素。</span>
          )}
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="02" title="当前情报状态" subtitle="方向一致性与共识证据彼此独立" />
        <div className="product-state-grid">
          <StateCard
            label="方向一致性"
            value={view.current_state.alignment}
            description={alignmentDescription(view.current_state.alignment)}
            tone="alignment"
          />
          <StateCard
            label="共识证据"
            value={view.current_state.consensus}
            description={consensusDescription(view.current_state.consensus)}
            tone="consensus"
          />
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="03" title="已观察覆盖" subtitle="投资者参与与当前证据数量" />
        <div className="product-stat-grid">
          <ProductStat label="当前背景中的投资者" value={view.context.investor_context.current_investor_count} />
          <ProductStat label="关注动态证据" value={view.context.attention_context.current_attention_count} />
          <ProductStat label="投资逻辑变化" value={view.context.thesis_context.current_thesis_changes} />
          <ProductStat label="当前背景中的变化信号" value={view.context.activity_context.current_signal_count} />
        </div>
        <div className="product-context-note">
          <span>{view.discovery.activity_summary ? "发现活动" : "历史证据"}</span>
          <strong>
            {view.discovery.activity_summary
              ? view.discovery.activity_summary.investor_count + " 位受监测投资者"
              : "暂无当前发现候选"}
          </strong>
        </div>
      </section>

      <section className="product-section product-narrative-section">
        <ProductHeading number="04" title="情报叙述" subtitle="已观察证据的确定性摘要" />
        <div className="product-narrative">
          <h2>{localizeText(view.narrative.headline)}</h2>
          <p>{localizeText(view.narrative.summary)}</p>
          <details className="product-narrative-details">
            <summary>查看叙述详情</summary>
            <div className="product-narrative-grid">
              <NarrativeFact label="关注动态" value={localizeText(view.narrative.attention_summary)} />
              <NarrativeFact label="投资逻辑" value={localizeText(view.narrative.thesis_summary)} />
              <NarrativeFact label="跨投资者" value={localizeText(view.narrative.cross_investor_summary)} />
              <NarrativeFact label="共识" value={localizeText(view.narrative.consensus_summary)} />
            </div>
          </details>
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="05" title="已观察背景" subtitle="事实时间窗口对照" />
        <div className="product-context-grid">
          <ContextFact label="活动" value={localizeText(view.context.activity_context.change_description)} />
          <ContextFact label="投资者" value={view.context.investor_context.current_investor_count + " 当前 · " + view.context.investor_context.previous_investor_count + "此前已观察"} />
          <ContextFact label="关注动态" value={localizeText(view.context.attention_context.change_description)} />
          <ContextFact label="投资逻辑" value={view.context.thesis_context.current_thesis_changes + " 当前 · " + view.context.thesis_context.historical_thesis_changes + "此前已观察"} />
        </div>
        <div className="product-comparison-note">
          历史对比不可作为完整性结论；此前窗口数量仅代表已观察到的计数。
        </div>
      </section>

      <section className="product-section">
        <ProductHeading number="06" title="近期演变" subtitle={view.evolution.step_count > visibleSteps.length ? "事实时间线中的近期步骤" : "按事实时间排序的证据"} />
        <div className="product-evolution-meta">
          <span>
            {formatTime(view.evolution.timeline_range.first_observed_at)} →{" "}
            {formatTime(view.evolution.timeline_range.latest_observed_at)}
          </span>
          <strong>{view.evolution.step_count} 个步骤</strong>
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
          <div className="product-empty-section">该标的暂无演变步骤。</div>
        )}
      </section>

      <section className="product-section">
        <ProductHeading number="07" title="情报流与事件生命周期" subtitle="生命周期状态不等于当前投资者活动" />
        <div className="product-lifecycle-grid">
          <LifecycleCard title="情报流生命周期" summary={view.feed} />
          <LifecycleCard title="事件生命周期" summary={view.events} />
        </div>
        <p className="product-lifecycle-note">
          这里的“进行中”仅描述生命周期或展示状态，不代表投资者当前正在讨论该标的。
        </p>
      </section>

      <section className="product-section product-quality-section">
        <ProductHeading number="Q" title="数据质量" subtitle="明确的数据边界不是错误状态" />
        <div className="product-quality-grid">
          <QualityFact label="历史完整性" value={view.data_quality.historical_completeness} />
          <QualityFact label="历史对比" value={view.data_quality.historical_comparison_supported ? "支持" : "不可用"} />
          <QualityFact label="缺失推断" value={view.data_quality.absence_inference_supported ? "支持" : "不支持"} />
        </div>
        <ul className="product-limitations">
          {view.data_quality.limitations.map((limitation) => <li key={limitation}>{displayText(limitation)}</li>)}
        </ul>
      </section>

      <section className="product-section product-traceability-section">
        <ProductHeading number="T" title="证据可追溯性" subtitle="已持久化来源产物的引用" />
        <div className="product-traceability-stats">
          <ProductStat label="证据引用" value={view.traceability_summary.source_ref_count} />
          <ProductStat label="规范来源" value={view.traceability_summary.canonical_source_count} />
          <ProductStat label="变化信号" value={view.traceability_summary.signal_count} />
        </div>
        <details className="product-evidence-details">
          <summary>查看证据来源引用</summary>
          <div className="product-evidence-list">
            {view.traceability_summary.evidence_refs.map((reference) => (
              <div key={reference.source_type + ":" + reference.source_id}>
                <span>{formatEnum(reference.source_type)}</span>
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
      <strong>{value ? formatEnum(value) : "暂无当前状态"}</strong>
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
  const investorLabel = investorName ?? "投资者编号 " + shortId(step.investor_id);
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
        <h3>{localizeText(step.title)}</h3>
        {step.investor_id && (
          <a
            className="product-investor-link"
            href={`/investors/${encodeURIComponent(step.investor_id)}`}
            onClick={handleInvestorClick}
            aria-label={`打开投资者 ${investorLabel}`}
          >
            投资者已观察 · {investorLabel}
          </a>
        )}
        <ul>{step.facts.map((fact) => <li key={fact}>{localizeText(fact)}</li>)}</ul>
      </div>
    </article>
  );
}

function LifecycleCard({ title, summary }: { title: string; summary: { active_count: number; states: Record<string, number> } }) {
  return (
    <div className="product-lifecycle-card">
      <span>{title}</span>
      <strong>{summary.active_count} 个进行中</strong>
      <div>{Object.entries(summary.states).map(([state, count]) => <small key={state}>{formatEnum(state)} · {count}</small>)}</div>
    </div>
  );
}

function QualityFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{formatEnum(value)}</strong></div>;
}

function alignmentDescription(value: string | null): string {
  if (value === "MIXED_DIRECTION") return "已观察观点横跨多个方向。";
  if (value === "INSUFFICIENT_EVIDENCE") return "已观察观点覆盖不足，无法判定方向一致性。";
  return value ? "当前已观察窗口已有方向一致性证据。" : "当前暂无跨投资者方向一致性状态。";
}

function consensusDescription(value: string | null): string {
  if (value === "DIVERGENT") return "已持久化的共识证据显示方向存在明显分歧。";
  if (value === "INSUFFICIENT_EVIDENCE") return "证据覆盖不足，无法进行共识分类。";
  return value ? "当前已观察窗口已有共识证据。" : "当前暂无共识证据。";
}

function formatEnum(value: string): string {
  return localizedEnum(value);
}
