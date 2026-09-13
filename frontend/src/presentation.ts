import type {
  AssetListItem,
  Direction,
  EvidenceType,
  ThesisChangeType,
  TimelineEvent
} from "./types";

const timeFormatter = new Intl.DateTimeFormat("zh-HK", {
  dateStyle: "medium",
  timeStyle: "short",
  hour12: false
});

export function formatTime(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "—" : timeFormatter.format(date);
}

export function formatLag(days: number | null): string {
  if (days === null || Number.isNaN(days)) return "—";
  if (days === 0) return "Same time";
  if (days < 1) return "+" + (days * 24).toFixed(1) + "h";
  return "+" + days.toFixed(2) + "d";
}

export function directionLabel(direction: Direction | null): string {
  if (!direction) return "No Opinion";
  return direction.replaceAll("_", " ");
}

export function directionClass(direction: Direction | null): string {
  if (!direction) return "direction-muted";
  if (direction.includes("BULLISH")) return "direction-bullish";
  if (direction.includes("BEARISH")) return "direction-bearish";
  return "direction-neutral";
}

export function evidenceLabel(evidence: EvidenceType): string {
  if (evidence === "OPINION") return "Opinion";
  if (evidence === "EXPLICIT_MENTION") return "Mention";
  return "Repost";
}

export function thesisLabel(changeType: ThesisChangeType | null): string {
  if (!changeType) return "No comparison";
  return changeType.replace("THESIS_", "").replaceAll("_", " ");
}

export function eventLabel(eventType: TimelineEvent["event_type"]): string {
  return eventType
    .replace("ATTENTION_FIRST_OBSERVED", "First observed")
    .replace("ATTENTION_OBSERVED", "Attention observed")
    .replace("OPINION_OBSERVED", "Opinion observed")
    .replace("THESIS_CHANGE_OBSERVED", "Thesis change");
}

export function limitationLabel(flag: string): string {
  const labels: Record<string, string> = {
    HISTORICAL_COMPLETENESS_UNKNOWN: "Historical completeness is unknown",
    ABSENCE_INFERENCE_UNSUPPORTED: "Absence-based inference is unsupported",
    MISSING_THESIS_COMPARISON: "One thesis comparison is unavailable",
    CROSS_INVESTOR_LINEAGE_UNAVAILABLE: "No active cross-investor lineage for this window",
    NO_OPINION_COVERAGE: "No effective Opinion coverage for this Asset",
    LATEST_DIRECTION_IS_LATEST_OBSERVED_ONLY:
      "Direction is the latest observed Opinion only"
  };
  return labels[flag] ?? flag.replaceAll("_", " ").toLowerCase();
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
