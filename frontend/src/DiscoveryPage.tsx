import { useMemo } from "react";

import type { AssetListItem } from "./types";
import { filterAssets, formatEnum, formatTime } from "./presentation";

const PAGE_SIZE = 12;

type MarketFilter = "ALL" | "SH" | "SZ" | "HK";
type BreadthFilter = "any" | "2" | "3";
type CrossFilter =
  | "any"
  | "mixed"
  | "divergent"
  | "disagreement"
  | "aligned_bullish"
  | "aligned_bearish"
  | "insufficient";
type ThesisFilter = "any" | "repeated" | "changed" | "reversal";
type GapFilter = "any" | "attention_gt_opinion";
type SortKey = "name" | "latest" | "attention" | "opinion" | "span";

interface DiscoveryQuery {
  search: string;
  market: MarketFilter;
  attention: BreadthFilter;
  opinion: BreadthFilter;
  cross: CrossFilter;
  thesis: ThesisFilter;
  gap: GapFilter;
  sort: SortKey;
  page: number;
  invalid: boolean;
}

interface DiscoveryPageProps {
  assets: AssetListItem[];
  loading: boolean;
  error: Error | null;
  queryString: string;
  onOpenAsset: (assetId: string) => void;
  onQueryChange: (queryString: string) => void;
}

const defaultQuery: Omit<DiscoveryQuery, "invalid"> = {
  search: "",
  market: "ALL",
  attention: "any",
  opinion: "any",
  cross: "any",
  thesis: "any",
  gap: "any",
  sort: "name",
  page: 1
};

const presets: Array<{
  key: string;
  label: string;
  changes: Partial<Record<keyof Omit<DiscoveryQuery, "invalid">, string | number | null>>;
}> = [
  { key: "all", label: "全部", changes: { ...defaultQuery } },
  { key: "shared-attention", label: "共同关注", changes: { attention: "2", page: 1 } },
  { key: "multi-opinion", label: "多投资者观点", changes: { opinion: "2", page: 1 } },
  {
    key: "direction-disagreement",
    label: "方向分歧",
    changes: { cross: "disagreement", page: 1 }
  },
  {
    key: "attention-gap",
    label: "关注动态 > 观点",
    changes: { gap: "attention_gt_opinion", page: 1 }
  },
  { key: "repeated-thesis", label: "重复投资逻辑", changes: { thesis: "repeated", page: 1 } }
];

export function parseDiscoveryQuery(search: string): DiscoveryQuery {
  const params = new URLSearchParams(search);
  let invalid = false;

  const readChoice = <T extends string>(
    key: string,
    allowed: readonly T[],
    fallback: T
  ): T => {
    const value = params.get(key);
    if (value === null || value === "") return fallback;
    if (allowed.includes(value as T)) return value as T;
    invalid = true;
    return fallback;
  };

  const rawPage = params.get("page");
  let page = 1;
  if (rawPage !== null) {
    const parsed = Number(rawPage);
    if (Number.isInteger(parsed) && parsed >= 1) page = parsed;
    else invalid = true;
  }

  return {
    search: params.get("q") ?? "",
    market: readChoice("market", ["ALL", "SH", "SZ", "HK"], "ALL"),
    attention: readChoice("attention", ["any", "2", "3"], "any"),
    opinion: readChoice("opinion", ["any", "2", "3"], "any"),
    cross: readChoice(
      "cross",
      [
        "any",
        "mixed",
        "divergent",
        "disagreement",
        "aligned_bullish",
        "aligned_bearish",
        "insufficient"
      ],
      "any"
    ),
    thesis: readChoice("thesis", ["any", "repeated", "changed", "reversal"], "any"),
    gap: readChoice("gap", ["any", "attention_gt_opinion"], "any"),
    sort: readChoice("sort", ["name", "latest", "attention", "opinion", "span"], "name"),
    page,
    invalid
  };
}

function queryFromChanges(
  currentSearch: string,
  changes: Partial<Record<keyof Omit<DiscoveryQuery, "invalid">, string | number | null>>
): string {
  const params = new URLSearchParams(currentSearch);
  const defaults = defaultQuery as Record<string, string | number>;
  for (const [key, value] of Object.entries(changes)) {
    const paramKey = key === "search" ? "q" : key;
    if (value === null || value === "" || value === defaults[key]) params.delete(paramKey);
    else params.set(paramKey, String(value));
  }
  return params.toString();
}

function breadthMatches(value: number, filter: BreadthFilter): boolean {
  if (filter === "any") return true;
  return value >= Number(filter);
}

function crossMatches(asset: AssetListItem, filter: CrossFilter): boolean {
  const alignment = asset.latest_alignment;
  const consensus = asset.latest_consensus;
  if (filter === "any") return true;
  if (filter === "mixed") return alignment === "MIXED_DIRECTION";
  if (filter === "divergent") return consensus === "DIVERGENT";
  if (filter === "disagreement") {
    return alignment === "MIXED_DIRECTION" || consensus === "DIVERGENT";
  }
  if (filter === "aligned_bullish") return alignment === "ALIGNED_BULLISH";
  if (filter === "aligned_bearish") return alignment === "ALIGNED_BEARISH";
  return alignment === "INSUFFICIENT_EVIDENCE" || consensus === "INSUFFICIENT_EVIDENCE";
}

function thesisMatches(asset: AssetListItem, filter: ThesisFilter): boolean {
  if (filter === "any") return true;
  if (filter === "repeated") return asset.has_repeated_thesis;
  if (filter === "changed") return asset.has_thesis_changed;
  return asset.has_direction_reversal;
}

function compareNullableTime(left: string | null, right: string | null): number {
  if (left === right) return 0;
  if (left === null) return 1;
  if (right === null) return -1;
  return new Date(right).getTime() - new Date(left).getTime();
}

function compareAssets(left: AssetListItem, right: AssetListItem, sort: SortKey): number {
  if (sort === "latest") {
    const latest = compareNullableTime(left.latest_evidence_time, right.latest_evidence_time);
    if (latest !== 0) return latest;
  } else if (sort === "attention" && left.attention_investor_count !== right.attention_investor_count) {
    return right.attention_investor_count - left.attention_investor_count;
  } else if (sort === "opinion" && left.opinion_investor_count !== right.opinion_investor_count) {
    return right.opinion_investor_count - left.opinion_investor_count;
  } else if (sort === "span") {
    const leftSpan = left.temporal_span_days ?? -1;
    const rightSpan = right.temporal_span_days ?? -1;
    if (leftSpan !== rightSpan) return rightSpan - leftSpan;
  }
  return (
    left.asset_name.localeCompare(right.asset_name, "zh-Hans") ||
    left.market.localeCompare(right.market) ||
    left.symbol.localeCompare(right.symbol) ||
    left.asset_id.localeCompare(right.asset_id)
  );
}

function labelFromEnum(value: string | null): string {
  return value ? formatEnum(value) : "—";
}

function activePreset(query: DiscoveryQuery): string {
  if (
    !query.search &&
    query.market === "ALL" &&
    query.attention === "any" &&
    query.opinion === "any" &&
    query.cross === "any" &&
    query.thesis === "any" &&
    query.gap === "any"
  ) {
    return "all";
  }
  if (query.attention === "2" && query.opinion === "any" && query.cross === "any" && query.thesis === "any" && query.gap === "any") return "shared-attention";
  if (query.opinion === "2" && query.attention === "any" && query.cross === "any" && query.thesis === "any" && query.gap === "any") return "multi-opinion";
  if (query.cross === "disagreement" && query.attention === "any" && query.opinion === "any" && query.thesis === "any" && query.gap === "any") return "direction-disagreement";
  if (query.gap === "attention_gt_opinion" && query.attention === "any" && query.opinion === "any" && query.cross === "any" && query.thesis === "any") return "attention-gap";
  if (query.thesis === "repeated" && query.attention === "any" && query.opinion === "any" && query.cross === "any" && query.gap === "any") return "repeated-thesis";
  return "";
}

export function DiscoveryPage({
  assets,
  loading,
  error,
  queryString,
  onOpenAsset,
  onQueryChange
}: DiscoveryPageProps) {
  const query = useMemo(() => parseDiscoveryQuery(queryString), [queryString]);
  const filteredAssets = useMemo(() => {
    return filterAssets(assets, query.search)
      .filter((asset) => query.market === "ALL" || asset.market.toUpperCase() === query.market)
      .filter((asset) => breadthMatches(asset.attention_investor_count, query.attention))
      .filter((asset) => breadthMatches(asset.opinion_investor_count, query.opinion))
      .filter((asset) => crossMatches(asset, query.cross))
      .filter((asset) => thesisMatches(asset, query.thesis))
      .filter((asset) => query.gap === "any" || asset.attention_opinion_gap)
      .sort((left, right) => compareAssets(left, right, query.sort));
  }, [assets, query]);

  if (loading) return <DiscoveryLoading />;
  if (error) {
    return (
      <div className="discovery-state error-state">
        <div className="state-symbol error">!</div>
        <div className="eyebrow">标的发现 / 只读</div>
        <h1>API 暂不可用</h1>
        <p>无法访问证据目录，系统未推断发现结论。</p>
      </div>
    );
  }

  const totalPages = Math.max(1, Math.ceil(filteredAssets.length / PAGE_SIZE));
  const currentPage = Math.min(query.page, totalPages);
  const pageItems = filteredAssets.slice((currentPage - 1) * PAGE_SIZE, currentPage * PAGE_SIZE);
  const selectedPreset = activePreset(query);

  const updateQuery = (
    changes: Partial<Record<keyof Omit<DiscoveryQuery, "invalid">, string | number | null>>
  ) => onQueryChange(queryFromChanges(queryString, changes));

  return (
    <div className="discovery-container">
      <header className="discovery-header">
        <div>
          <div className="eyebrow">
            <span className="eyebrow-line" />
            标的发现 / 已观察证据
          </div>
          <h1>标的发现</h1>
          <p>浏览包含已观察关注动态、观点、投资逻辑和跨投资者证据的标的。</p>
        </div>
        <div className="discovery-boundary" role="note">
          <span>数据边界</span>
          <strong>历史完整性：未知</strong>
          <small>仅表示存在与顺序</small>
        </div>
      </header>

      {query.invalid && (
        <div className="query-note" role="status">
          部分 URL 筛选值无效，已忽略。
        </div>
      )}

      <section className="discovery-toolbar" aria-label="标的发现控制">
        <div className="discovery-search-row">
          <label className="discovery-search-label" htmlFor="discovery-search">
            搜索已观察标的
          </label>
          <input
            id="discovery-search"
            type="search"
            value={query.search}
            placeholder="名称、市场或代码"
            onChange={(event) => updateQuery({ search: event.target.value, page: 1 })}
          />
          <span className="discovery-search-hint">名称与上市标的保持区分。</span>
        </div>
        <div className="preset-tabs" role="group" aria-label="发现预设">
          {presets.map((preset) => (
            <button
              key={preset.key}
              type="button"
              className={selectedPreset === preset.key ? "active" : ""}
              aria-pressed={selectedPreset === preset.key}
              onClick={() => updateQuery({ ...defaultQuery, ...preset.changes })}
            >
              {preset.label}
            </button>
          ))}
        </div>
        <div className="filter-grid">
          <FilterSelect
            label="市场"
            value={query.market}
            onChange={(value) => updateQuery({ market: value, page: 1 })}
            options={[
              ["ALL", "全部"],
              ["SH", "SH"],
              ["SZ", "SZ"],
              ["HK", "HK"]
            ]}
          />
          <FilterSelect
            label="关注动态覆盖"
            value={query.attention}
            onChange={(value) => updateQuery({ attention: value, page: 1 })}
            options={[["any", "不限"], ["2", "至少 2 位投资者"], ["3", "至少 3 位投资者"]]}
          />
          <FilterSelect
            label="观点覆盖"
            value={query.opinion}
            onChange={(value) => updateQuery({ opinion: value, page: 1 })}
            options={[["any", "不限"], ["2", "至少 2 位投资者"], ["3", "至少 3 位投资者"]]}
          />
          <FilterSelect
            label="跨投资者"
            value={query.cross}
            onChange={(value) => updateQuery({ cross: value, page: 1 })}
            options={[
              ["any", "不限"],
              ["mixed", "方向混杂"],
              ["divergent", "观点分化"],
              ["aligned_bullish", "方向一致（积极）"],
              ["aligned_bearish", "方向一致（谨慎）"],
              ["insufficient", "证据不足"]
            ]}
          />
          <FilterSelect
            label="投资逻辑"
            value={query.thesis}
            onChange={(value) => updateQuery({ thesis: value, page: 1 })}
            options={[
              ["any", "不限"],
              ["repeated", "重复投资逻辑"],
              ["changed", "投资逻辑已变化"],
              ["reversal", "方向反转"]
            ]}
          />
          <FilterSelect
            label="证据缺口"
            value={query.gap}
            onChange={(value) => updateQuery({ gap: value, page: 1 })}
            options={[["any", "不限"], ["attention_gt_opinion", "关注动态 > 观点"]]}
          />
        </div>
      </section>

      <div className="discovery-result-bar">
        <div>
          <strong>{filteredAssets.length}</strong>
          <span>共 {filteredAssets.length} 个已观察标的</span>
          {query.search && <small>搜索：“{query.search}”</small>}
        </div>
        <div className="sort-control">
          <label htmlFor="discovery-sort">排序</label>
          <select
            id="discovery-sort"
            value={query.sort}
            onChange={(event) => updateQuery({ sort: event.target.value, page: 1 })}
          >
            <option value="name">标的名称</option>
            <option value="latest">最近观察证据</option>
            <option value="attention">关注动态投资者</option>
            <option value="opinion">观点投资者</option>
            <option value="span">时间跨度</option>
          </select>
        </div>
      </div>

      {pageItems.length ? (
        <div className="discovery-list" aria-live="polite">
          {pageItems.map((asset) => (
            <DiscoveryCard asset={asset} key={asset.asset_id} onOpenAsset={onOpenAsset} />
          ))}
        </div>
      ) : (
        <div className="discovery-empty">
          <div className="empty-mark">⌕</div>
          <h2>没有符合这些证据筛选条件的标的。</h2>
          <p>请清除筛选条件，或搜索其他名称、市场或代码。</p>
          <button type="button" onClick={() => updateQuery({ ...defaultQuery })}>
            清除筛选
          </button>
        </div>
      )}

      <div className="discovery-pagination">
        <span>
          显示 {pageItems.length ? (currentPage - 1) * PAGE_SIZE + 1 : 0}–
          {(currentPage - 1) * PAGE_SIZE + pageItems.length} / {filteredAssets.length}
        </span>
        <div>
          <button
            type="button"
            aria-label="上一页"
            disabled={currentPage <= 1}
            onClick={() => updateQuery({ page: currentPage - 1 })}
          >
            上一页
          </button>
          <strong>
            {currentPage} / {totalPages}
          </strong>
          <button
            type="button"
            aria-label="下一页"
            disabled={currentPage >= totalPages}
            onClick={() => updateQuery({ page: currentPage + 1 })}
          >
            下一页
          </button>
        </div>
      </div>
    </div>
  );
}

function FilterSelect({
  label,
  value,
  options,
  onChange
}: {
  label: string;
  value: string;
  options: Array<[string, string]>;
  onChange: (value: string) => void;
}) {
  const id = "discovery-filter-" + label.toLocaleLowerCase().replaceAll(" ", "-");
  return (
    <label className="filter-control" htmlFor={id}>
      <span>{label}</span>
      <select id={id} value={value} onChange={(event) => onChange(event.target.value)}>
        {options.map(([optionValue, optionLabel]) => (
          <option key={optionValue} value={optionValue}>
            {optionLabel}
          </option>
        ))}
      </select>
    </label>
  );
}

function DiscoveryCard({
  asset,
  onOpenAsset
}: {
  asset: AssetListItem;
  onOpenAsset: (assetId: string) => void;
}) {
  const flags = asset.data_quality_flags;
  const hasDataGap = flags.includes("MISSING_THESIS_COMPARISON");
  const duplicateInsufficientCoverage =
    asset.latest_alignment === "INSUFFICIENT_EVIDENCE" &&
    asset.latest_consensus === "INSUFFICIENT_EVIDENCE";
  return (
    <article className="discovery-card">
      <button
        type="button"
        className="discovery-card-header"
        onClick={() => onOpenAsset(asset.asset_id)}
        aria-label={"打开 " + asset.asset_name + " " + asset.market + ":" + asset.symbol}
      >
        <div>
          <span className="discovery-card-kicker">已观察标的</span>
          <h2>{asset.asset_name}</h2>
        </div>
        <span className="listing-badge">
          {asset.market} <i>·</i> {asset.symbol}
        </span>
        <span className="open-mark" aria-hidden="true">↗</span>
      </button>
      <div className="discovery-card-body">
        <div className="discovery-breadth">
          <DiscoveryStat label="关注动态" value={String(asset.attention_investor_count) + " 位投资者"} />
          <DiscoveryStat label="观点" value={String(asset.opinion_investor_count) + " 位投资者"} />
          <DiscoveryStat label="最近观察" value={formatTime(asset.latest_evidence_time)} />
          <DiscoveryStat
            label="时间跨度"
            value={asset.temporal_span_days === null ? "—" : asset.temporal_span_days.toFixed(1) + "天"}
          />
        </div>
        <div className="discovery-card-footer">
          <div className="discovery-badges">
            {asset.latest_alignment && (
              <EvidenceBadge
                value={
                  duplicateInsufficientCoverage
                    ? "方向一致性 · " + labelFromEnum(asset.latest_alignment)
                    : labelFromEnum(asset.latest_alignment)
                }
                tone="alignment"
              />
            )}
            {asset.latest_consensus && (
              <EvidenceBadge
                value={
                  duplicateInsufficientCoverage
                    ? "共识 · " + labelFromEnum(asset.latest_consensus)
                    : labelFromEnum(asset.latest_consensus)
                }
                tone="consensus"
              />
            )}
            {asset.attention_opinion_gap && <EvidenceBadge value="关注动态 > 观点" tone="gap" />}
            {asset.has_repeated_thesis && <EvidenceBadge value="重复投资逻辑" tone="thesis" />}
            {asset.has_direction_reversal && <EvidenceBadge value="方向反转" tone="reversal" />}
            {hasDataGap && <EvidenceBadge value="数据缺口" tone="gap" />}
          </div>
          <button type="button" className="open-detail" onClick={() => onOpenAsset(asset.asset_id)}>
            打开标的 <span>→</span>
          </button>
        </div>
      </div>
    </article>
  );
}

function DiscoveryStat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function EvidenceBadge({ value, tone }: { value: string; tone: "alignment" | "consensus" | "gap" | "thesis" | "reversal" }) {
  return <span className={"discovery-badge " + tone}>{value}</span>;
}

function DiscoveryLoading() {
  return (
    <div className="discovery-container discovery-loading" aria-label="正在加载标的发现">
      <div className="skeleton loading-discovery-title" />
      <div className="skeleton loading-discovery-toolbar" />
      <div className="loading-discovery-grid">
        {[1, 2, 3, 4, 5, 6].map((item) => <div className="skeleton loading-discovery-card" key={item} />)}
      </div>
    </div>
  );
}
