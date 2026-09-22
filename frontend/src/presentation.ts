import type {
  AssetListItem,
  Direction,
  EvidenceType,
  ThesisChangeType,
  TimelineEvent
} from "./types";

const timeFormatter = new Intl.DateTimeFormat("zh-CN", {
  timeZone: "Asia/Hong_Kong",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23"
});

const enumLabels: Record<string, string> = {
  UNKNOWN: "未知",  BULLISH: "看好",
  STRONG_BULLISH: "强烈看好",
  NEUTRAL: "中性",
  BEARISH: "谨慎",
  STRONG_BEARISH: "强烈谨慎",
  NONE: "暂无",
  PARTIAL: "部分",
  COMPLETE: "完整",
  SAME_DIRECTION: "方向未变",
  OPPOSITE_DIRECTION: "方向相反",
  NEUTRAL_OR_MIXED: "中性或混合",
  OPINION_MISSING: "缺少观点",
  OBSERVED_LATER: "后续观察",
  SIMULTANEOUS_OBSERVATION: "同时观察",
  INITIAL_OPINION: "首次观点",
  COMPARISON_AVAILABLE: "可进行对比",
  INITIAL_DIRECTION: "首次方向",
  BULLISH_TO_BEARISH: "由看好转为谨慎",
  BEARISH_TO_BULLISH: "由谨慎转为看好",
  TO_NEUTRAL: "转为中性",
  FROM_NEUTRAL: "由中性转出",
  OTHER: "其他",
  RUNNING: "运行中",
  SUCCESS: "成功",
  PARTIAL_FAILURE: "部分失败",
  FAILED: "失败",
  SKIPPED_ALREADY_RUNNING: "已有任务运行中",
  MANUAL: "手动触发",
  SCHEDULED: "定时触发",
  OPINION_RECORDED: "已记录观点",
  RAW_EVENT: "采集事件",
  EVENT_ANALYSIS: "分析结果",
  OPINION: "观点",
  THESIS_CHANGE: "投资逻辑变化",
  ATTENTION_OCCURRENCE: "关注动态",
  CONSENSUS_FRAGMENTATION: "共识分化",
  MULTI_INVESTOR_EXPANSION: "多位投资者扩展关注",
  THESIS_TRANSITION: "投资逻辑转变",
  HIGH_PRIORITY_EVIDENCE: "高优先级证据",
  ACTIVE_INTELLIGENCE: "当前情报",
  HISTORICAL_INTELLIGENCE: "历史情报",
  MULTI_INVESTOR_ACTIVITY: "多投资者活动",
  THESIS_ACTIVITY: "投资逻辑活动",
  CROSS_INVESTOR_ACTIVITY: "跨投资者活动",
  CONSENSUS_ACTIVITY: "共识活动",
  ATTENTION_SPIKE: "关注动态增加",
  REPEATED_THESIS: "重复投资逻辑",
  DIRECTION_REVERSAL: "方向反转",
  DATA_GAP: "数据缺口",
  MENTION: "明确提及",
  REPOST: "转发证据",
  INSUFFICIENT_EVIDENCE: "证据不足",
  MIXED_DIRECTION: "方向分歧",
  DIVERGENT: "观点分化",
  MIXED_WITH_NEUTRAL: "含中性的方向混合",
  CONSENSUS_BULLISH: "共识方向（看好）",
  CONSENSUS_BEARISH: "共识方向（谨慎）",
  CONSENSUS_NEUTRAL: "共识方向（中性）",
  NEW_DISCOVERY: "新发现",
  ACCELERATING_ACTIVITY: "活动加速",
  RETURNING_ATTENTION: "关注回流",
  CONSENSUS_FORMATION: "共识形成",
  INSUFFICIENT_HISTORY: "历史证据不足",
  HISTORICAL_COMPARISON_UNAVAILABLE: "历史对比不可用",
  COLLECTION_PROVENANCE_UNAVAILABLE: "采集来源不可用",
  NO_OPINION: "暂无观点",
  PARTIALLY_RESOLVED: "部分解析",
  UNRESOLVED: "未解析",
  AMBIGUOUS: "存在歧义",
  INVALID: "无效",
  ALIGNED_BULLISH: "方向一致（看好）",
  ALIGNED_BEARISH: "方向一致（谨慎）",
  ALIGNED_NEUTRAL: "方向一致（中性）",
  NEW_ATTENTION: "新关注",
  OPINION_UPGRADE: "观点增强",
  OPINION_DOWNGRADE: "观点减弱",
  OPINION_REVERSAL: "观点反转",
  NO_MATERIAL_CHANGE: "暂无实质变化",
  IMMEDIATE_REVIEW: "优先复核",
  ACTIVE_REVIEW: "持续复核",
  BACKGROUND_MONITORING: "背景观察",
  LIMITED_CONTEXT: "背景有限",
  OPINION_AT_FIRST_ATTENTION: "首次关注时已有观点",
  OPINION_AFTER_ATTENTION: "关注后形成观点",
  ATTENTION_WITHOUT_OPINION: "有关注、暂无观点",
  OPINION_WITHOUT_PRIOR_ATTENTION: "有观点、无先前关注",
  SIMULTANEOUS: "同时观察到",
  ATTENTION_FIRST_OBSERVED: "首次观察到关注",
  ATTENTION_OBSERVED: "观察到关注",
  OPINION_OBSERVED: "观察到观点",
  THESIS_CHANGE_OBSERVED: "观察到投资逻辑变化",
  NEW_THESIS: "新投资逻辑",
  THESIS_UNCHANGED: "投资逻辑未变",
  THESIS_REINFORCED: "投资逻辑强化",
  THESIS_EXTENDED: "投资逻辑扩展",
  THESIS_CHANGED: "投资逻辑变化",
  INSUFFICIENT_EVIDENCE_FOR_THESIS: "投资逻辑证据不足",
  HISTORICAL_COMPLETENESS_UNKNOWN: "历史完整性未知",
  ABSENCE_INFERENCE_UNSUPPORTED: "不支持基于缺失的推断",
  MISSING_THESIS_COMPARISON: "缺少一次投资逻辑对比",
  CROSS_INVESTOR_LINEAGE_UNAVAILABLE: "当前窗口暂无跨投资者谱系",
  NO_OPINION_COVERAGE: "当前标的暂无有效观点覆盖",
  LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY: "方向仅代表最近观察到的观点",
  HEALTHY: "运行正常",
  ACTION_REQUIRED: "需要处理",
  SOURCE_LIMITED: "数据源受限",
  STALE: "数据较旧",
  FRESH: "数据新鲜",
  ACTIVE: "进行中",
  NEW: "新情报",
  RESOLVED: "已处理",
  LOW: "低",
  MEDIUM: "中",
  HIGH: "高",
  ASSET_ACTIVITY_SPIKE: "标的活动增加",
  INVESTOR_VIEW_CHANGE: "投资者观点变化",
  CROSS_INVESTOR_DISCOVERY: "跨投资者发现",
  CONSENSUS_STATE_CHANGE: "共识状态变化",
  MULTI_INVESTOR_ATTENTION: "多位投资者关注",
  THESIS_ACCELERATION: "投资逻辑加速",
  CONSENSUS_STATE_CHANGE_REASON: "共识状态变化"
};

export function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "—";
  const parts = Object.fromEntries(
    timeFormatter.formatToParts(date).map((part) => [part.type, part.value])
  );
  return String(parts.year) + "-" + String(parts.month) + "-" + String(parts.day) + " " + String(parts.hour) + ":" + String(parts.minute);
}

export function formatLag(days: number | null): string {
  if (days === null || Number.isNaN(days)) return "—";
  if (days === 0) return "同一时间";
  if (days < 1) return "+" + (days * 24).toFixed(1) + "小时";
  return "+" + days.toFixed(2) + "天";
}

export function formatEnum(value: string | null | undefined): string {
  if (!value) return "—";
  return enumLabels[value] ?? value.replaceAll("_", " ");
}

export function directionLabel(direction: Direction | null): string {
  if (!direction) return "暂无观点";
  return formatEnum(direction);
}

export function directionClass(direction: Direction | null): string {
  if (!direction) return "direction-muted";
  if (direction.includes("BULLISH")) return "direction-bullish";
  if (direction.includes("BEARISH")) return "direction-bearish";
  return "direction-neutral";
}

export function evidenceLabel(evidence: EvidenceType): string {
  if (evidence === "OPINION") return "观点证据";
  if (evidence === "EXPLICIT_MENTION") return "明确提及";
  return "转发证据";
}

export function thesisLabel(changeType: ThesisChangeType | null): string {
  if (!changeType) return "暂无对比";
  return formatEnum(changeType);
}

export function eventLabel(eventType: TimelineEvent["event_type"]): string {
  return formatEnum(eventType);
}

export function limitationLabel(flag: string): string {
  return formatEnum(flag);
}

export function localizeText(value: string | null | undefined): string {
  if (!value) return value ?? "";
  const exact: Record<string, string> = {
    "Observed evidence only.": "仅展示已观察证据。",
    "Historical completeness is UNKNOWN.": "历史完整性未知。",
    "Historical completeness is UNKNOWN; absence-sensitive Pattern output is not supported.": "历史完整性未知；不支持基于缺失推断模式。",
    "Available collection provenance does not establish historical completeness.": "现有采集来源不足以证明历史完整性。",
    "Absence inference is unsupported.": "不支持基于缺失的推断。",
    "Observed evidence only; no absence inference is made.": "仅展示已观察证据；不基于缺失推断。",
    "This view does not describe holdings, conviction, influence, or advice.": "此视图不描述持仓、确信度、影响力或建议。",
    "No active intelligence activity observed for 中国海洋石油": "未观察到中国海洋石油的进行中情报活动",
    "Historical observed Intelligence remains available.": "历史已观察情报仍可查看。",
    "No active cross-investor activity evidence is available in this projection.": "当前投影暂无进行中的跨投资者活动证据。",
    "No active attention evidence is available in this projection.": "当前投影暂无进行中的关注动态证据。",
    "No active thesis activity evidence is available in this projection.": "当前投影暂无进行中的投资逻辑活动证据。",
    "No active consensus-state activity evidence is available in this projection.": "当前投影暂无进行中的共识状态活动证据。",
    "Active evidence counts are zero for this narrative projection.": "当前情报叙述中的有效证据计数为零。",
    "No active observed time range is available.": "暂无进行中的已观察时间范围。",
    "No ACTIVE FeedItem source is available.": "暂无进行中的情报流来源。",
    "No ACTIVE FeedItem source is available for this Asset in the current observed sample.": "当前已观察样本中暂无该标的的进行中情报流来源。",
    "Comparison window is explicit, but historical evidence is insufficient.": "对比窗口明确，但历史证据不足。",
    "Observed evidence count is zero in both comparison windows.": "两个对比窗口中的已观察证据数量均为零。"
  };
  if (exact[value]) return exact[value];

  let match = value.match(/^The active evidence chain includes activity from (\d+) distinct monitored investor\(s\)\.$/);
  if (match) return `当前证据链包含 ${match[1]} 位不同的受监测投资者活动。`;
  match = value.match(/^An INVESTOR_VIEW_CHANGE event is present for (.+)\.$/);
  if (match) return `观察到 ${match[1]} 的投资者观点变化事件。`;
  match = value.match(/^A CROSS_INVESTOR_DISCOVERY event is present for (.+)\.$/);
  if (match) return `观察到 ${match[1]} 的跨投资者发现事件。`;
  match = value.match(/^A CONSENSUS_STATE_CHANGE event is present for (.+)\.$/);
  if (match) return `观察到 ${match[1]} 的共识状态变化事件。`;
  if (value === "No INVESTOR_VIEW_CHANGE event is present in this active candidate.") return "当前候选中暂无投资者观点变化事件。";
  if (value === "No CROSS_INVESTOR_DISCOVERY event is present in this active candidate.") return "当前候选中暂无跨投资者发现事件。";
  if (value === "No CONSENSUS_STATE_CHANGE event is present in this active candidate.") return "当前候选中暂无共识状态变化事件。";
  match = value.match(/^Observed intelligence activity around (.+)$/);
  if (match) return `${match[1]} 周边的已观察情报活动`;
  match = value.match(/^In the current observed sample, (.+) is associated with (\d+) monitored investor\(s\), (\d+) aggregate event\(s\), (\d+) Signal\(s\), and (\d+) ACTIVE FeedItem\(s\)\.$/);
  if (match) return `当前已观察样本中，${match[1]} 关联 ${match[2]} 位受监测投资者、${match[3]} 个聚合事件、${match[4]} 个变化信号和 ${match[5]} 条进行中情报流记录。`;
  if (value.startsWith("Observed event types:")) {
    return value
      .replace("Observed event types:", "观察到的事件类型：")
      .replace("Discovery reasons:", "发现原因：")
      .replace("distinct Signals:", "不同变化信号：")
      .replace("distinct aggregate Events:", "不同聚合事件：")
      .replace("ACTIVE FeedItems:", "进行中情报流记录：")
      .replace(/\bnone\b/g, "无");
  }
  match = value.match(/^Observed time range: (.+) to (.+)\.$/);
  if (match) return `观察时间范围：${match[1]} 至 ${match[2]}。`;
  match = value.match(/^Observed (.+) increased from (\d+) to (\d+)\.$/);
  if (match) return `观察到${localizeTextLabel(match[1])}从 ${match[2]} 增加至 ${match[3]}。`;
  match = value.match(/^Observed (.+) decreased from (\d+) to (\d+)\.$/);
  if (match) return `观察到${localizeTextLabel(match[1])}从 ${match[2]} 减少至 ${match[3]}。`;
  match = value.match(/^Observed (.+) remained at (\d+)\.$/);
  if (match) return `观察到${localizeTextLabel(match[1])}保持为 ${match[2]}。`;
  if (value === "Investor attention observed") return "观察到投资者关注动态";
  if (value === "Thesis activity observed") return "观察到投资逻辑活动";
  if (value === "Multi-investor activity observed") return "观察到多投资者活动";
  if (value === "Cross-investor state observed") return "观察到跨投资者状态";
  if (value === "Consensus state observed") return "观察到共识状态";
  match = value.match(/^Signal type: (.+)\.$/);
  if (match) return `信号类型：${formatEnum(match[1])}。`;
  match = value.match(/^ThesisChange type: (.+)\.$/);
  if (match) return `投资逻辑变化类型：${formatEnum(match[1])}。`;
  match = value.match(/^Event type: (.+)\.$/);
  if (match) return `事件类型：${formatEnum(match[1])}。`;
  match = value.match(/^Alignment state: (.+)\.$/);
  if (match) return `方向一致性状态：${formatEnum(match[1])}。`;
  match = value.match(/^Consensus state: (.+)\.$/);
  if (match) return `共识状态：${formatEnum(match[1])}。`;
  if (value === "No active cross-investor evidence is present.") return "当前暂无进行中的跨投资者证据。";
  return value;
}

export function displayText(value: string | null | undefined): string {
  const localized = localizeText(value);
  return localized === (value ?? "") ? formatEnum(localized) : localized;
}

function localizeTextLabel(value: string): string {
  return value
    .replace("signal activity", "信号活动")
    .replace("attention evidence", "关注动态证据")
    .replace("thesis activity", "投资逻辑活动")
    .replace("investor activity", "投资者活动")
    .replace("evidence", "证据");
}
export function shortId(value: string | null): string {
  if (!value) return "—";
  return value.slice(0, 8) + "…";
}

export function filterAssets(assets: AssetListItem[], query: string): AssetListItem[] {
  const normalized = query.trim().toLocaleLowerCase();
  if (!normalized) return assets;
  return assets.filter((asset) =>
    [asset.asset_name, asset.market, asset.symbol].some((value) =>
      value.toLocaleLowerCase().includes(normalized)
    )
  );
}
