import { useMemo } from "react";

import type {
  AssetListItem,
  IntelligenceFeedItem,
  OperationalStatusResponse
} from "./types";
import { formatEnum, formatTime } from "./presentation";

interface OverviewPageProps {
  assets: AssetListItem[];
  loading: boolean;
  error: Error | null;
  onOpenAsset: (assetId: string) => void;
  onOpenDiscovery: (queryString: string) => void;
  onOpenInvestor?: (investorId: string) => void;
  recentItems?: IntelligenceFeedItem[];
  recentLoading?: boolean;
  recentError?: Error | null;
  operationalStatus?: OperationalStatusResponse | null;
}

export function OverviewPage({
  assets,
  loading,
  error,
  onOpenAsset,
  onOpenDiscovery,
  onOpenInvestor = () => undefined,
  recentItems = [],
  recentLoading = false,
  recentError = null,
  operationalStatus = null
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
        <div className="eyebrow">已观察情报 / 只读</div>
        <h1>API 暂不可用</h1>
        <p>无法访问已观察证据目录，系统未推断概览结论。</p>
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
            已观察情报 / 全部标的
          </div>
          <h1>已观察情报概览</h1>
          <p>当前监测样本中的证据模式，可前往标的发现查看。</p>
        </div>
        <div className="overview-boundary" role="note">
          <span>数据边界</span>
          <strong>历史完整性：未知</strong>
          <small>仅展示已观察证据</small>
        </div>
      </header>

      <RecentIntelligencePanel
        items={recentItems}
        loading={recentLoading}
        error={recentError}
        operationalStatus={operationalStatus}
        onOpenAsset={onOpenAsset}
        onOpenInvestor={onOpenInvestor}
      />

      <section className="overview-summary" aria-label="已观察标的概览">
        <OverviewMetric label="已观察标的" value={assets.length} note="有证据记录" />
        <OverviewMetric label="共同关注" value={sharedAttentionAssets.length} note="至少 2 位投资者" />
          <OverviewMetric label="多投资者观点" value={multiOpinionAssets.length} note="至少 2 位投资者" />
          <OverviewMetric label="方向分歧" value={disagreementAssets.length} note="方向混杂或观点分化" accent="coral" />
          <OverviewMetric label="重复投资逻辑" value={repeatedThesisAssets.length} note="重复时间线" accent="violet" />
      </section>

      <section className="overview-section">
        <OverviewSectionHeading
          number="01"
          title="证据模式"
          subtitle="按不同维度浏览已有证据"
        />
        <div className="pattern-grid">
          <PatternCard
            title="共同关注"
            count={sharedAttentionAssets.length}
            explanation="至少两位受监测投资者出现关注动态的标的。"
            onExplore={() => explore("attention=2")}
          />
          <PatternCard
            title="多投资者观点"
            count={multiOpinionAssets.length}
            explanation="至少两位受监测投资者形成结构化观点的标的。"
            onExplore={() => explore("opinion=2")}
          />
          <PatternCard
            title="方向分歧"
            count={disagreementAssets.length}
            explanation="已观察证据呈现方向分歧或观点分化的标的。"
            onExplore={() => explore("cross=disagreement")}
          />
          <PatternCard
            title="关注动态 > 观点"
            count={attentionGapCount}
            explanation="关注动态覆盖的受监测投资者多于形成结构化观点的投资者。"
            onExplore={() => explore("gap=attention_gt_opinion")}
          />
          <PatternCard
            title="重复投资逻辑"
            count={repeatedThesisAssets.length}
            explanation="存在重复投资者 × 标的投资逻辑时间线的标的。"
            onExplore={() => explore("thesis=repeated")}
          />
        </div>
      </section>

      <section className="overview-section overview-disagreement-section">
        <OverviewSectionHeading
          number="02"
          title="方向分歧"
          subtitle="已有方向证据，不新增评分"
          action={<button type="button" className="overview-text-action" onClick={() => explore("cross=disagreement")}>前往标的发现 →</button>}
        />
        <div className="disagreement-stat-row">
          <div><strong>{assets.filter((asset) => asset.latest_alignment === "MIXED_DIRECTION").length}</strong><span>方向分歧</span></div>
          <div><strong>{assets.filter((asset) => asset.latest_consensus === "DIVERGENT").length}</strong><span>观点分化</span></div>
          <p>最近观察到的观点可能横跨多个方向；这里展示的是证据，不代表因果关系。</p>
        </div>
        {disagreementAssets.some((asset) => asset.latest_consensus === "DIVERGENT") ? (
          <div className="overview-asset-rows">
            {disagreementAssets
              .filter((asset) => asset.latest_consensus === "DIVERGENT")
              .map((asset) => (
                <OverviewAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} highlight="观点分化" />
              ))}
          </div>
        ) : (
          <div className="overview-inline-note">当前已观察样本中没有观点分化标的。</div>
        )}
      </section>

      <section className="overview-section">
        <OverviewSectionHeading
          number="03"
          title="最近观察到的标的"
          subtitle="按最近证据时间展示，不代表排名"
        />
        <div className="overview-asset-rows latest-rows">
          {latestObservedAssets.map((asset) => (
            <OverviewAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} />
          ))}
        </div>
      </section>

      <section className="overview-dual-grid">
        <div className="overview-section overview-compact-panel">
          <OverviewSectionHeading number="04" title="投资逻辑演变" subtitle="已观察的重复与变化时间线" />
          <div className="compact-fact-list">
            <CompactFact label="重复投资逻辑标的" value={repeatedThesisAssets.length} />
            <CompactFact label="投资逻辑变化标的" value={changedThesisAssets.length} />
            <CompactFact label="方向反转标的" value={reversalAssets.length} />
          </div>
          <div className="compact-actions">
            <button type="button" onClick={() => explore("thesis=repeated")}>查看重复投资逻辑 →</button>
            <button type="button" onClick={() => explore("thesis=reversal")}>查看方向反转 →</button>
          </div>
        </div>
        <div className="overview-section overview-compact-panel gap-panel">
          <OverviewSectionHeading number="05" title="关注动态 > 观点" subtitle="覆盖广度与结构化观点并不等同" />
          <div className="gap-intro">
            <strong>{attentionGapCount} 个标的</strong>
            <span>关注动态覆盖的受监测投资者多于形成结构化观点的投资者。</span>
          </div>
          <div className="overview-asset-rows compact-rows">
            {attentionGapAssets.map((asset) => (
              <OverviewAssetRow asset={asset} key={asset.asset_id} onOpen={onOpenAsset} compact />
            ))}
          </div>
          <button type="button" className="overview-text-action" onClick={() => explore("gap=attention_gt_opinion")}>查看全部关注动态 &gt; 观点 →</button>
        </div>
      </section>

      <section className="overview-section overview-boundary-section">
        <OverviewSectionHeading number="Q" title="数据边界" subtitle="明确展示限制，不夸大解读" />
        <div className="boundary-facts">
          <div><span>历史完整性</span><strong>未知</strong></div>
          <div><span>支持</span><strong>出现与顺序证据</strong></div>
          <div><span>不支持</span><strong>缺失推断</strong></div>
          <div><span>方向标签</span><strong>仅最近观察</strong></div>
        </div>
        <div className="gap-summary">
          <div>
            <span>数据缺口</span>
            <strong>缺少投资逻辑对比 · {missingComparisonAssets.length}</strong>
          </div>
          {missingComparisonAssets.slice(0, 3).map((asset) => (
            <button type="button" key={asset.asset_id} onClick={() => onOpenAsset(asset.asset_id)}>
              {asset.asset_name} · {asset.market}:{asset.symbol} →
            </button>
          ))}
        </div>
      </section>

      <footer className="overview-footer">
        <span>雪球情报 · 已观察证据概览</span>
        <span>打开标的，查看完整证据视图。</span>
      </footer>
    </div>
  );
}

function RecentIntelligencePanel({
  items,
  loading,
  error,
  operationalStatus,
  onOpenAsset,
  onOpenInvestor
}: {
  items: IntelligenceFeedItem[];
  loading: boolean;
  error: Error | null;
  operationalStatus: OperationalStatusResponse | null;
  onOpenAsset: (assetId: string) => void;
  onOpenInvestor: (investorId: string) => void;
}) {
  const statusNotice =
    operationalStatus?.status === "STALE"
      ? "数据可能较旧；当前展示最近可用情报。"
      : operationalStatus?.status === "ACTION_REQUIRED"
        ? "刷新需要处理；已有情报仍可查看。"
        : operationalStatus?.status === "SOURCE_LIMITED"
          ? "数据源暂时受限；已有情报仍可查看。"
          : null;

  return (
    <section className="overview-section recent-intelligence-panel" aria-label="近期投资情报">
      <OverviewSectionHeading
        number="00"
        title="近期投资情报"
        subtitle="最近 24 小时内呈现的可用投资情报"
      />
      {statusNotice && <div className="recent-intelligence-notice">{statusNotice}</div>}
      {loading ? (
        <div className="recent-intelligence-loading" aria-label="正在加载近期投资情报">
          正在加载近期投资情报…
        </div>
      ) : error ? (
        <div className="recent-intelligence-empty" role="status">
          <strong>近期投资情报暂不可用。</strong>
          <span>情报流查询无法加载；上方运行状态仍可查看。</span>
        </div>
      ) : items.length === 0 ? (
        <div className="recent-intelligence-empty" role="status">
          <strong>近期窗口暂无已呈现的投资情报。</strong>
          <span>数据刷新成功与情报呈现是两件事；下方仍保留历史证据。</span>
        </div>
      ) : (
        <div className="recent-intelligence-grid">
          {items.map((item) => (
            <RecentIntelligenceCard
              item={item}
              key={item.id}
              onOpenAsset={onOpenAsset}
              onOpenInvestor={onOpenInvestor}
            />
          ))}
        </div>
      )}
    </section>
  );
}

function RecentIntelligenceCard({
  item,
  onOpenAsset,
  onOpenInvestor
}: {
  item: IntelligenceFeedItem;
  onOpenAsset: (assetId: string) => void;
  onOpenInvestor: (investorId: string) => void;
}) {
  const eventCopy = {
    ASSET_ACTIVITY_SPIKE: "多位投资者关注了该标的",
    INVESTOR_VIEW_CHANGE: "投资者观点发生变化",
    CROSS_INVESTOR_DISCOVERY: "发现跨投资者关注动态",
    CONSENSUS_STATE_CHANGE: "共识状态发生变化"
  }[item.event_type];
  const reasonCopy = {
    MULTI_INVESTOR_ATTENTION: "多位受监测投资者贡献了关注动态证据。",
    THESIS_ACCELERATION: "观察到多次投资逻辑变化。",
    CROSS_INVESTOR_DISCOVERY: "观察到跨投资者证据。",
    CONSENSUS_STATE_CHANGE: "共识证据状态发生变化。"
  }[item.reason];

  return (
    <article className="recent-intelligence-card">
      <div className="recent-intelligence-card-meta">
        <span className={"priority-badge " + item.priority_level.toLowerCase()}>
          {formatEnum(item.priority_level)}级复核优先级
        </span>
        <time dateTime={item.observed_at}>{formatTime(item.observed_at)}</time>
      </div>
      <h3>{eventCopy}</h3>
      <a
        href={"/assets/" + item.asset.asset_id}
        onClick={(event) => {
          event.preventDefault();
          onOpenAsset(item.asset.asset_id);
        }}
      >
        {item.asset.name} · {item.asset.market}:{item.asset.symbol}
      </a>
      <p>{reasonCopy}</p>
      <div className="recent-intelligence-card-footer">
        <span>证据数量 {String(item.context.signal_count ?? item.context.source_count ?? 0)}</span>
        {item.investors.length > 0 && (
          <span className="recent-intelligence-investors">
            {item.investors.slice(0, 3).map((investor) => (
              <a
                href={"/investors/" + investor.investor_id}
                key={investor.investor_id}
                onClick={(event) => {
                  event.preventDefault();
                  onOpenInvestor(investor.investor_id);
                }}
              >
                {investor.name}
              </a>
            ))}
            {item.investors.length > 3 && " +" + (item.investors.length - 3)}
          </span>
        )}
      </div>
    </article>
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
      <div className="pattern-card-top"><span>已观察模式</span><span>{count} 个标的</span></div>
      <h3>{title}</h3>
      <p>{explanation}</p>
      <button type="button" aria-label={"查看 " + title} onClick={onExplore}>查看 <span>→</span></button>
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
      aria-label={"打开 " + asset.asset_name + " " + asset.market + ":" + asset.symbol}
    >
      <div className="overview-asset-identity">
        <strong>{asset.asset_name}</strong>
        <span>{asset.market} · {asset.symbol}</span>
      </div>
      <div className="overview-asset-evidence">
        <span>最近观察</span>
        <strong>{formatTime(asset.latest_evidence_time)}</strong>
      </div>
      <div className="overview-asset-breadth">
        <span>关注动态 <b>{asset.attention_investor_count}</b></span>
        <span>观点 <b>{asset.opinion_investor_count}</b></span>
      </div>
      {!compact && (
        <div className="overview-asset-badges">
          {highlight && <FactBadge value={highlight} tone="coral" />}
          {asset.latest_alignment && (
            <FactBadge
              value={duplicateInsufficientCoverage ? "方向一致性 · " + labelFromEnum(asset.latest_alignment) : labelFromEnum(asset.latest_alignment)}
              tone="alignment"
            />
          )}
          {asset.latest_consensus && (
            <FactBadge
              value={duplicateInsufficientCoverage ? "共识 · " + labelFromEnum(asset.latest_consensus) : labelFromEnum(asset.latest_consensus)}
              tone="consensus"
            />
          )}
          {asset.attention_opinion_gap && <FactBadge value="关注动态 > 观点" tone="gap" />}
          {asset.has_repeated_thesis && <FactBadge value="重复投资逻辑" tone="thesis" />}
          {asset.has_direction_reversal && <FactBadge value="方向反转" tone="reversal" />}
          {dataGap && <FactBadge value="数据缺口" tone="gap" />}
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
  return formatEnum(value);
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
    <div className="overview-container overview-loading" aria-label="正在加载已观察情报概览">
      <div className="skeleton loading-overview-title" />
      <div className="loading-overview-summary">
        {[1, 2, 3, 4, 5].map((item) => <div className="skeleton" key={item} />)}
      </div>
      <div className="skeleton loading-overview-patterns" />
    </div>
  );
}
