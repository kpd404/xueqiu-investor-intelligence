import type { MouseEvent, ReactNode } from "react";

import type {
  InvestorAssetIntelligenceProductView,
  InvestorProductActivityEvent,
  InvestorProductView
} from "./types";
import {
  displayText,
  directionClass,
  directionLabel,
  evidenceLabel,
  formatEnum,
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
            投资者洞察 / 产品视图
          </div>
          <h1>{view.investor.name}</h1>
          <p>
            展示一位投资者的关注动态、已持久化观点与投资逻辑证据。这是
            只读证据工作区，不评价投资者质量。
          </p>
        </div>
        <div className="investor-boundary">
          <span>投资者身份</span>
          <strong>{view.investor.source_platform}</strong>
          <small>{view.investor.source_user_id} · {shortId(view.investor.investor_id)}</small>
        </div>
      </header>

      <div className="investor-window-line">
        有效观察窗口： {formatTime(view.window_start)} → {formatTime(view.window_end)}
      </div>

      <section className="investor-metric-strip" aria-label="投资者情报概览">
        <Metric label="已观察标的" value={view.summary.observed_asset_count} />
        <Metric label="观点标的" value={view.summary.opinion_asset_count} />
        <Metric label="仅关注动态标的" value={view.coverage.attention_only_assets.length} />
        <Metric label="关注动态次数" value={view.summary.attention_occurrence_count} />
        <Metric label="观点" value={view.summary.opinion_count} />
        <Metric label="投资逻辑变化" value={view.summary.thesis_change_count} accent="coral" />
      </section>

      <section className="investor-product-note" role="note">
        <strong>观察到的关注动态与已持久化观点是两类不同证据。</strong>
        <span>
          数量仅描述已记录产物。“仅关注动态”表示当前读取范围内没有有效的已持久化观点
          不代表该投资者的观点。
        </span>
      </section>

      {!view.asset_views.length && (
        <section className="investor-product-empty-note" role="status">
          <strong>当前采集记录中暂无该投资者的情报证据。</strong>
          <span>历史完整性未知；此状态不代表历史上不存在。</span>
        </section>
      )}

      <section className="investor-section investor-product-coverage-section">
        <SectionHeading
          title="按证据类型覆盖"
          subtitle="同一标的可能有观察、观点，或仅有关注动态记录。"
        />
        <div className="investor-product-coverage-grid">
          <CoverageCard title="已观察标的" assets={view.coverage.observed_assets} onOpen={onOpenAsset} />
          <CoverageCard title="观点标的" assets={view.coverage.opinion_assets} onOpen={onOpenAsset} />
          <CoverageCard title="仅关注动态标的" assets={view.coverage.attention_only_assets} onOpen={onOpenAsset} />
        </div>
      </section>

      <section className="investor-section investor-asset-section">
        <SectionHeading
          title="标的情报"
          subtitle="最近方向仅取最近一条有效持久化观点。"
          count={view.asset_views.length + " 个标的"}
        />
        {view.asset_views.length ? (
          <div className="investor-asset-list">
            {view.asset_views.map((asset) => (
              <InvestorAssetProductRow key={asset.asset.asset_id} asset={asset} onOpen={onOpenAsset} />
            ))}
          </div>
        ) : (
          <div className="investor-inline-empty">
            当前采集记录中暂无情报证据。
          </div>
        )}
      </section>

      <div className="investor-dual-grid">
        <section className="investor-section">
          <SectionHeading
            title="近期投资逻辑变化"
            subtitle="已持久化的投资逻辑变化，按事实时间排序。"
            count={thesisAssets.length + " 个标的"}
          />
          {thesisAssets.length ? (
            <div className="investor-product-thesis-list">
              {thesisAssets.map((asset) => (
                <AssetRouteLink
                  className="investor-product-thesis-row"
                  assetId={asset.asset.asset_id}
                  onOpen={onOpenAsset}
                  ariaLabel={`打开标的 ${asset.asset.name} ${asset.asset.market}:${asset.asset.symbol}`}
                  key={asset.asset.asset_id}
                >
                  <span>
                    <strong>{asset.asset.name}</strong>
                    <small>{asset.asset.market}:{asset.asset.symbol}</small>
                  </span>
                  <b>{asset.thesis.latest_change_type ? thesisLabel(asset.thesis.latest_change_type) : "—"}</b>
                  <small>{formatTime(asset.thesis.latest_change_at)}</small>
                </AssetRouteLink>
              ))}
            </div>
          ) : (
            <div className="investor-inline-empty">暂无投资逻辑变化记录。</div>
          )}
        </section>

        <section className="investor-section">
          <SectionHeading
            title="近期活动"
            subtitle="按事实时间排序的关注动态、观点和投资逻辑记录。"
            count={activity.length + " 项活动"}
          />
          {activity.length ? (
            <div className="investor-product-activity-list">
              {activity.map((event, index) => (
                <ActivityRow key={activityKey(event, index)} event={event} onOpen={onOpenAsset} />
              ))}
            </div>
          ) : (
            <div className="investor-inline-empty">暂无近期活动。</div>
          )}
        </section>
      </div>

      <section className="investor-section investor-quality-section">
        <SectionHeading title="数据质量" subtitle="覆盖边界明确展示，不代表错误状态。" />
        <div className="investor-quality-grid">
          <QualityFact label="历史完整性" value={view.data_quality.historical_completeness} />
          <QualityFact
            label="历史对比"
            value={view.data_quality.historical_comparison_supported ? "支持" : "不支持"}
          />
          <QualityFact
            label="缺失推断"
            value={view.data_quality.absence_inference_supported ? "支持" : "不支持"}
          />
        </div>
        <ul className="investor-product-limitations">
          {view.data_quality.limitations.map((limitation) => <li key={limitation}>{displayText(limitation)}</li>)}
        </ul>
      </section>

      <section className="investor-section investor-quality-section">
        <SectionHeading title="证据可追溯性" subtitle="规范化持久化产物的引用。" />
        <div className="investor-product-traceability-grid">
          <QualityFact label="关注动态引用" value={String(view.traceability_summary.attention_occurrence_ref_count)} />
          <QualityFact label="采集事件引用" value={String(view.traceability_summary.raw_event_ref_count)} />
          <QualityFact label="观点引用" value={String(view.traceability_summary.opinion_ref_count)} />
          <QualityFact label="投资逻辑变化引用" value={String(view.traceability_summary.thesis_change_ref_count)} />
          <QualityFact label="活动来源引用" value={String(view.traceability_summary.activity_source_ref_count)} />
        </div>
        <details className="investor-product-evidence-details">
          <summary>查看来源引用</summary>
          <div className="investor-product-source-list">
            {view.asset_views.flatMap((asset) => [
              ...asset.traceability.attention_occurrence_ids.map((id) => ({ type: "关注动态", id, asset })),
              ...asset.traceability.raw_event_ids.map((id) => ({ type: "采集事件", id, asset })),
              ...asset.traceability.opinion_ids.map((id) => ({ type: "观点", id, asset })),
              ...asset.traceability.thesis_change_ids.map((id) => ({ type: "投资逻辑变化", id, asset }))
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
        <span>只读投资者产品视图 · 查询时组合</span>
        <span>最近观察产物：{formatTime(view.summary.latest_observed_at)}</span>
      </footer>
    </div>
  );
}

function Metric({ label, value, accent }: { label: string; value: number; accent?: "coral" }) {
  return <div className={"investor-metric" + (accent ? " " + accent : "")}><span>{label}</span><strong>{value}</strong><small>已记录产物</small></div>;
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
          <AssetRouteLink
            key={asset.asset_id}
            assetId={asset.asset_id}
            onOpen={onOpen}
            className="investor-product-coverage-asset-link"
            ariaLabel={`打开标的 ${asset.name} ${asset.market}:${asset.symbol}`}
          >
            {asset.name} <small>{asset.market}:{asset.symbol}</small>
          </AssetRouteLink>
        ))}
        {assets.length > 8 && <small>+{assets.length - 8} 个标的可在标的情报中查看</small>}
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
    <AssetRouteLink
      className="investor-asset-row"
      assetId={asset.asset.asset_id}
      onOpen={onOpen}
      ariaLabel={`打开标的 ${asset.asset.name} ${asset.asset.market}:${asset.asset.symbol}`}
    >
      <div className="investor-asset-title">
        <strong>{asset.asset.name}</strong>
        <span>{asset.asset.market}:{asset.asset.symbol}</span>
      </div>
      <div className="investor-asset-cell attention-cell">
        <span>关注动态</span>
        <strong>{asset.attention.occurrence_count} 次关注动态</strong>
        <small>{formatTime(asset.attention.latest_observed_at)}</small>
        <div className="investor-evidence-chips">
          {asset.attention.evidence_types.map((evidence) => <em className="investor-evidence-chip" key={evidence}>{evidenceLabel(evidence)}</em>)}
        </div>
      </div>
      <div className="investor-asset-cell opinion-cell">
        <span>已持久化观点</span>
        <strong>{asset.opinion.opinion_count} 条记录</strong>
        <span className={"investor-direction-pill " + directionClass(asset.opinion.latest_direction)}>
          {asset.opinion.latest_direction
            ? directionLabel(asset.opinion.latest_direction)
            : "暂无已持久化观点"}
        </span>
        <small>{formatTime(asset.opinion.latest_opinion_at)}</small>
      </div>
      <div className="investor-asset-cell thesis-cell">
        <span>投资逻辑</span>
        <strong>{asset.thesis.thesis_change_count} 次变化</strong>
        <small>{asset.thesis.latest_change_type ? thesisLabel(asset.thesis.latest_change_type) : "暂无投资逻辑变化"}</small>
        <small>{formatTime(asset.thesis.latest_change_at)}</small>
      </div>
      <div className="investor-asset-cell cross-cell">
        <span>关系</span>
        <strong>{asset.relationship.attention_only ? "仅关注动态" : asset.relationship.has_opinion ? "关注动态 + 观点" : "投资逻辑证据"}</strong>
        <small>最近观察：{formatTime(asset.latest_observed_at)}</small>
      </div>
      <span className="investor-open-mark" aria-hidden="true">→</span>
    </AssetRouteLink>
  );
}

function ActivityRow({ event, onOpen }: { event: InvestorProductActivityEvent; onOpen: (assetId: string) => void }) {
  return (
    <AssetRouteLink
      className="investor-product-activity-row"
      assetId={event.asset.asset_id}
      onOpen={onOpen}
      ariaLabel={`打开标的 ${event.asset.name} ${event.asset.market}:${event.asset.symbol}`}
    >
      <span className="investor-product-activity-time">{formatTime(event.observed_at)}</span>
      <span className="investor-product-activity-type">{activityLabel(event.event_type)}</span>
      <strong>{event.asset.name}</strong>
      <small>{event.asset.market}:{event.asset.symbol} · {event.source_refs.length} 条来源引用</small>
    </AssetRouteLink>
  );
}

function AssetRouteLink({
  assetId,
  onOpen,
  className,
  ariaLabel,
  children
}: {
  assetId: string;
  onOpen: (assetId: string) => void;
  className: string;
  ariaLabel: string;
  children: ReactNode;
}) {
  const handleClick = (event: MouseEvent<HTMLAnchorElement>) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) {
      return;
    }
    event.preventDefault();
    onOpen(assetId);
  };
  return (
    <a
      className={className}
      href={`/assets/${encodeURIComponent(assetId)}`}
      onClick={handleClick}
      aria-label={ariaLabel}
    >
      {children}
    </a>
  );
}

function QualityFact({ label, value }: { label: string; value: string }) {
  return <div><span>{label}</span><strong>{displayText(value)}</strong></div>;
}

function activityLabel(value: InvestorProductActivityEvent["event_type"]): string {
  if (value === "ATTENTION_OBSERVED") return "观察到关注动态";
  if (value === "OPINION_RECORDED") return "已记录观点";
  return "观察到投资逻辑变化";
}

function activityKey(event: InvestorProductActivityEvent, index: number): string {
  return event.event_type + ":" + event.asset.asset_id + ":" + event.observed_at + ":" + index;
}

function compareTimes(left: string | null, right: string | null): number {
  return (right ? new Date(right).getTime() : Number.NEGATIVE_INFINITY) -
    (left ? new Date(left).getTime() : Number.NEGATIVE_INFINITY);
}
