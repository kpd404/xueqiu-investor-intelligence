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
  formatEnum,
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
        <div className="eyebrow">投资者洞察 / 只读</div>
        <h1>API 暂不可用</h1>
        <p>无法访问已观察投资者目录，系统未推断投资者结论。</p>
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
            投资者洞察 / 已观察证据
          </div>
          <h1>投资者洞察</h1>
          <p>选择受监测投资者，查看已观察标的、观点、投资逻辑变化和重叠关系。</p>
        </div>
        <div className="investor-boundary" role="note">
          <span>数据边界</span>
          <strong>历史完整性：未知</strong>
          <small>已有采集来源记录不足以证明历史完整性。</small>
        </div>
      </header>

      <section className="investor-selector-panel" aria-label="投资者选择器">
        <label htmlFor="investor-search">搜索投资者名称</label>
        <input
          id="investor-search"
          type="search"
          value={query}
          placeholder="投资者名称"
          onChange={(event) => setSearch(event.target.value)}
        />
        <span>{visible.length} / {investors.length} 位已观察投资者</span>
      </section>

      {visible.length ? (
        <div className="investor-list" aria-live="polite">
          {visible.map((investor) => (
            <button
              type="button"
              className="investor-list-card"
              key={investor.investor_id}
              aria-label={"打开投资者 " + investor.investor_name}
              onClick={() => onOpenInvestor(investor.investor_id)}
            >
              <div className="investor-list-identity">
                <span>已观察投资者</span>
                <strong>{investor.investor_name}</strong>
              </div>
              <div><span>关注标的</span><strong>{investor.attention_asset_count}</strong></div>
              <div><span>观点标的</span><strong>{investor.opinion_asset_count}</strong></div>
              <div><span>最近观察</span><strong>{formatTime(investor.latest_observed_evidence_time)}</strong></div>
              <span className="investor-open-mark" aria-hidden="true">↗</span>
            </button>
          ))}
        </div>
      ) : (
        <div className="investor-empty">
          <div className="empty-mark">⌕</div>
          <h2>没有符合搜索条件的已观察投资者。</h2>
          <p>仅按投资者名称搜索，不对结果排序。</p>
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
            投资者洞察 / 已观察证据
          </div>
          <h1>{view.investor_name}</h1>
          <p>当前数据库窗口中的投资者 × 标的已观察证据。</p>
        </div>
        <div className="investor-boundary" role="note">
          <span>数据边界</span>
          <strong>历史完整性：未知</strong>
          <small>仅展示已观察证据 · 已有采集来源不足以证明历史完整性。</small>
        </div>
      </header>

      <div className="investor-window-line">
        已观察窗口： {formatTime(view.window_start)} — {formatTime(view.window_end)}
      </div>

      <section className="investor-metric-strip" aria-label="投资者已观察证据概览">
        <InvestorMetric label="关注标的" value={view.attention_asset_count} />
        <InvestorMetric label="观点标的" value={view.opinion_asset_count} />
        <InvestorMetric label="重复观点标的" value={view.repeated_opinion_asset_count} />
        <InvestorMetric label="投资逻辑变化标的" value={view.thesis_changed_asset_count} />
        <InvestorMetric label="方向反转标的" value={view.direction_reversal_asset_count} accent="coral" />
        <InvestorMetric label="共同关注标的" value={view.shared_attention_asset_count} />
      </section>

      {query.invalid && (
        <div className="investor-query-note" role="status">部分投资者 URL 筛选值无效，已忽略。</div>
      )}

      <section className="investor-breadth-panel">
        <InvestorSectionHeading title="关注动态与观点" subtitle="已观察覆盖与结构化观点是两种独立证据维度" />
        <div className="investor-breadth-content">
          <div><span>已观察关注覆盖</span><strong>{view.attention_asset_count} 个标的</strong></div>
          <div className="breadth-divider">≠</div>
          <div><span>结构化观点覆盖</span><strong>{view.opinion_asset_count} 个标的</strong></div>
          <p>这些数量描述已观察证据，不代表研究质量或重要性。</p>
        </div>
      </section>

      <section className="investor-section investor-asset-section">
        <InvestorSectionHeading
          title="已观察标的"
          subtitle="标的行保留上市身份与现有跨投资者状态"
          action={<span className="investor-section-count">{assets.length} / {view.asset_views.length} 个标的</span>}
        />
        <div className="investor-asset-controls" aria-label="投资者标的筛选">
          <label htmlFor="investor-asset-filter">筛选</label>
          <select id="investor-asset-filter" value={query.filter} onChange={(event) => changeQuery({ filter: event.target.value })}>
            <option value="all">全部</option>
            <option value="attention">仅关注动态</option>
            <option value="opinion">有观点</option>
            <option value="repeated">重复观点</option>
            <option value="changed">投资逻辑已变化</option>
            <option value="reversal">方向反转</option>
            <option value="shared_attention">共同关注</option>
            <option value="shared_opinion">共同观点</option>
          </select>
          <label htmlFor="investor-asset-sort">排序</label>
          <select id="investor-asset-sort" value={query.sort} onChange={(event) => changeQuery({ sort: event.target.value })}>
            <option value="latest">最近观察</option>
            <option value="first">首次观察</option>
            <option value="attention">关注次数</option>
            <option value="opinion">观点数量</option>
            <option value="name">标的名称</option>
          </select>
          <span>仅统计已观察的共同标的数量</span>
        </div>
        {assets.length ? (
          <div className="investor-asset-list" aria-live="polite">
            {assets.map((asset) => (
              <InvestorAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />
            ))}
          </div>
        ) : (
          <div className="investor-inline-empty">没有符合筛选条件的已观察标的证据。</div>
        )}
      </section>

      <section className="investor-dual-grid">
        <div className="investor-section investor-compact-panel">
          <InvestorSectionHeading title="投资逻辑活动" subtitle="确定性事实摘要；按投资逻辑变化数量排序" />
          <div className="investor-activity-facts">
            <div><strong>{view.repeated_opinion_asset_count}</strong><span>重复观点标的</span></div>
            <div><strong>{view.thesis_changed_asset_count}</strong><span>投资逻辑变化标的</span></div>
            <div><strong>{view.direction_reversal_asset_count}</strong><span>方向反转标的</span></div>
          </div>
          <div className="investor-mini-list">
            {thesisAssets.map((asset) => <InvestorMiniAsset asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />)}
          </div>
        </div>
        <div className="investor-section investor-compact-panel">
          <InvestorSectionHeading title="共同标的背景" subtitle="其他受监测投资者也观察到的标的" />
          <div className="shared-context-summary">
            <div><strong>{view.shared_attention_asset_count}</strong><span>共同关注标的</span></div>
            <div><strong>{view.shared_opinion_asset_count}</strong><span>共同观点标的</span></div>
          </div>
          <div className="investor-mini-list">
            {sharedAssets.slice(0, 5).map((asset) => <InvestorMiniAsset asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />)}
          </div>
        </div>
      </section>

      <section className="investor-section investor-overlap-section">
        <InvestorSectionHeading title="已观察标的重叠" subtitle="与其他受监测投资者的集合交集，仅展示数量" action={<span className="investor-section-count">{overlaps.length} 个重叠投资者</span>} />
        <div className="overlap-controls">
          <label htmlFor="overlap-sort">重叠排序</label>
          <select id="overlap-sort" value={query.overlapSort} onChange={(event) => changeQuery({ overlapSort: event.target.value })}>
            <option value="name">投资者名称</option>
            <option value="attention">共同关注数量</option>
            <option value="opinion">共同观点数量</option>
          </select>
          <span>已观察共同标的数量</span>
        </div>
        {overlaps.length ? (
          <div className="overlap-list">
            {overlaps.map((overlap) => (
              <button
                type="button"
                className="overlap-row"
                key={overlap.other_investor_id}
                onClick={() => onOpenInvestor(overlap.other_investor_id)}
                aria-label={"打开投资者 " + overlap.other_investor_name}
              >
                <strong>{overlap.other_investor_name}</strong>
                <span>共同关注 <b>{overlap.shared_attention_asset_count}</b></span>
                <span>共同观点 <b>{overlap.shared_opinion_asset_count}</b></span>
                <span className="investor-open-mark" aria-hidden="true">↗</span>
              </button>
            ))}
          </div>
        ) : (
          <div className="investor-inline-empty">当前已观察窗口没有共同标的重叠。</div>
        )}
      </section>

      <section className="investor-section investor-quality-section">
        <InvestorSectionHeading title="数据边界 / 数据质量" subtitle="已观察限制明确展示，不代表不存在" />
        <div className="investor-quality-grid">
          <QualityFact label="历史完整性" value="未知" />
          <QualityFact label="采集来源" value="不可用" />
          <QualityFact label="缺失推断" value="不支持" />
          <QualityFact label="最近方向" value="仅最近观察" />
          <QualityFact label="观点覆盖" value={view.data_quality.opinion_coverage} />
          <QualityFact label="缺失投资逻辑对比" value={String(view.data_quality.missing_thesis_comparison_count)} />
        </div>
      </section>

      <footer className="investor-footer">
        <span>雪球情报 · 已观察投资者证据</span>
        <span>最近方向仅表示最近观察到的观点。</span>
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
  return <div className={"investor-metric" + (accent ? " " + accent : "")}><span>{label}</span><strong>{value}</strong><small>已观察证据</small></div>;
}

function InvestorSectionHeading({ title, subtitle, action }: { title: string; subtitle: string; action?: React.ReactNode }) {
  return <div className="investor-section-heading"><div><h2>{title}</h2><span>{subtitle}</span></div>{action}</div>;
}

function InvestorAssetRow({ asset, onOpen }: { asset: InvestorAssetIntelligenceSummary; onOpen: (assetId: string) => void }) {
  const duplicateInsufficient = asset.alignment === "INSUFFICIENT_EVIDENCE" && asset.consensus === "INSUFFICIENT_EVIDENCE";
  return (
    <button type="button" className="investor-asset-row" onClick={() => onOpen(asset.asset_id)} aria-label={"打开标的 " + asset.asset_name + " " + asset.market + ":" + asset.symbol}>
      <div className="investor-asset-title"><strong>{asset.asset_name}</strong><span>{asset.market} · {asset.symbol}</span></div>
      <div className="investor-asset-cell attention-cell"><span>关注动态</span><strong>{asset.attention_occurrence_count} 次</strong><small>{formatTime(asset.first_attention_time)} → {formatTime(asset.latest_attention_time)}</small><EvidenceChips values={asset.attention_evidence_types} /></div>
      <div className="investor-asset-cell opinion-cell"><span>观点</span><strong>{asset.opinion_count} 条观点</strong><small>{formatTime(asset.first_opinion_time)} → {formatTime(asset.latest_opinion_time)}</small><DirectionPill direction={asset.latest_observed_direction} /></div>
      <div className="investor-asset-cell thesis-cell"><span>投资逻辑</span><strong>{asset.thesis_change_count} 次变化</strong><small>已变化 {asset.changed_count} · 已扩展 {asset.extended_count} · 反转 {asset.reversal_count}</small>{asset.missing_thesis_comparison_count > 0 && <em>{asset.missing_thesis_comparison_count} 次对比不可用</em>}</div>
      <div className="investor-asset-cell cross-cell"><span>跨投资者</span><strong>关注动态 {asset.attention_investor_count} · 观点 {asset.opinion_investor_count}</strong><small>共同关注 {asset.shared_attention_investor_count} · 共同观点 {asset.shared_opinion_investor_count}</small><div className="investor-state-badges">{asset.alignment && <StateBadge value={duplicateInsufficient ? "方向一致性 · " + labelFromEnum(asset.alignment) : labelFromEnum(asset.alignment)} tone="alignment" />}{asset.consensus && <StateBadge value={duplicateInsufficient ? "共识 · " + labelFromEnum(asset.consensus) : labelFromEnum(asset.consensus)} tone="consensus" />}</div></div>
      <span className="investor-open-mark" aria-hidden="true">↗</span>
    </button>
  );
}

function InvestorMiniAsset({ asset, onOpen }: { asset: InvestorAssetIntelligenceSummary; onOpen: (assetId: string) => void }) {
  return <button type="button" className="investor-mini-asset" onClick={() => onOpen(asset.asset_id)}><span><strong>{asset.asset_name}</strong><small>{asset.market} · {asset.symbol}</small></span><span>{asset.thesis_change_count ? asset.thesis_change_count + " 次变化" : "共同标的"}</span><span className="investor-open-mark" aria-hidden="true">↗</span></button>;
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
  return <div><span>{label}</span><strong>{formatEnum(value)}</strong></div>;
}

function labelFromEnum(value: string): string {
  return formatEnum(value);
}

function InvestorLoading() {
  return <div className="investor-state investor-loading" aria-label="正在加载投资者洞察"><div className="skeleton loading-investor-title" /><div className="skeleton loading-investor-panel" /><div className="skeleton loading-investor-list" /></div>;
}
