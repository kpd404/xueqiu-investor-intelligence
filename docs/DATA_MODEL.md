# Xueqiu Investor Intelligence System

## Data Model Specification

Version: 1.4

---

# 1. Data Design Philosophy

## 1.1 Core Principle

本系统的数据设计围绕 Investor Behavior Intelligence Graph。

核心关系：

```text
Investor
    ↓
Content
    ↓
Opinion
    ↓
State Change
    ↓
Market Signal
```

系统不是存储股票观点列表，而是记录投资者如何随着时间变化而改变认知和行为。

## 1.2 Fact vs Intelligence Separation

系统必须严格区分三类数据。

### Fact Layer

事实层，来源于外部数据。

例如：

- 大 V 发布帖子
- 发布时间
- 组合仓位

特点：不可修改。

对应实体：`RawEvent`。

### Interpretation Layer

解释层，来源于 AI 分析。

例如：

- 看多
- 投资逻辑
- 风险

特点：可以重新生成。

对应实体：`Opinion`。

### Intelligence Layer

情报层，来源于系统计算结果。

例如：

- 共识
- Signal Score
- Research Candidate

特点：动态计算。

对应实体：`Signal`。

---

# 2. Entity Overview

MVP 核心实体：

```text
Investor
Asset
RawEvent
Opinion
InvestorAssetState
Signal
```

Portfolio Fact Foundation additionally provides `Portfolio`, `PositionSnapshot`,
`PortfolioAction`, and `InvestorActionClaim` as an independent behavior-fact
stream; it does not change the Opinion lifecycle.

核心关系：

```text
Investor
    ↓
RawEvent
    ↓
Opinion
    ↓
InvestorAssetState
    ↓
Signal
```

---

# 3. Entity Definitions

## 3.1 Investor

### Purpose

记录被监控的投资者。

例如：

- 雪球大 V
- 投资账号
- 专业投资者

### Table

`investors`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `name` | string | 昵称 |
| `platform` | string | 来源平台 |
| `platform_user_id` | string | 平台 ID |
| `homepage_url` | string | 主页链接 |
| `investment_style` | string | 投资风格 |
| `expertise_domains` | JSON | 专业领域 |
| `quality_score` | float | 投资质量评分 |
| `created_at` | timestamp | 创建时间 |
| `updated_at` | timestamp | 更新时间 |

### Notes

`quality_score` 不是粉丝数量。

未来根据以下因素计算：

- 历史观点质量
- 行业专业度
- 观点行为一致性

## 3.2 Asset

### Purpose

统一管理投资标的。

支持：

- 股票
- ETF
- 指数
- 商品
- 行业主题

### Table

`assets`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `name` | string | 名称 |
| `symbol` | string | 代码 |
| `market` | string | 市场 |
| `industry` | string | 行业 |
| `themes` | JSON | 主题标签 |
| `created_at` | timestamp | 创建时间 |

### Example

```json
{
  "name": "腾讯控股",
  "symbol": "00700",
  "market": "HK",
  "themes": ["AI", "港股互联网"]
}
```

### Asset identity aliases

`Asset` stores one canonical `(market, symbol, name)` identity. It does not have
enough structure to store alternate names, display formats, or multiple
candidate matches. `AssetAlias` is therefore the minimal separate identity
table for deterministic resolution.

### AssetAlias

### Table

`asset_aliases`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `asset_id` | UUID | Canonical Asset |
| `alias` | string | Original alternate identity |
| `normalized_alias` | string | Deterministically normalized identity |
| `alias_type` | string | `NAME`, `SYMBOL`, or future explicit type |
| `market` | string nullable | Optional canonical market scope |

The unique identity is `(asset_id, normalized_alias)`. The same alias may
intentionally point to multiple assets so a future Resolver can return
`AMBIGUOUS` candidates instead of guessing.

## 3.3 RawEvent

### Purpose

保存原始事件。这是系统的事实数据库，任何后续分析必须来源于 `RawEvent`。

### Table

`raw_events`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `investor_id` | UUID | 事件产生者 |
| `event_type` | string | 事件类型 |
| `source` | string | 来源 |
| `url` | string | 原始链接 |
| `published_time` | timestamp | 发布时间 |
| `content` | text | 原文 |
| `raw_data` | JSON | 原始数据 |
| `hash` | string | 去重标识 |
| `collected_time` | timestamp | 采集时间 |

### Event Type

MVP：

```text
POST
ARTICLE
PORTFOLIO_SNAPSHOT
```

Future：

```text
COMMENT
REPOST
NEWS_REFERENCE
```

### Important Rule

`RawEvent` 禁止修改。

- 错误：更新原文。
- 正确：新增事件。

### Following Feed provenance

For the Xueqiu Following Feed, the top-level status `id` is retained as
`RawEvent.raw_data["source_event_id"]`; it is the current feed event identity,
not `retweet_status_id`. A repost keeps its nested `retweet_status_id` and
`retweeted_status` object in `raw_data`. The current author's top-level status
text remains the only `RawEvent.content`; the nested repost text is not merged
into it. No dedicated database column is required for this source identity in
the current MVP.

## 3.4 Opinion

### Purpose

来源于 `RawEvent` 的 AI 结构化投资观点。

### Asset resolution boundary

The extraction layer produces provider-neutral identity hints. A deterministic
resolution layer may normalize those hints and consult canonical Assets and
AssetAliases, but it must never create an Asset from an unverified mention.

Resolution outcomes are `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`, and `INVALID`.
When identity resolution fails, the full extracted opinion semantics (direction,
strength, confidence, thesis, catalysts, risks, and time horizon) remain in the
unresolved record so a later resolution can create an Opinion without rerunning
the LLM.

### Table

`opinions`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `event_id` | UUID | 来源事件 |
| `investor_id` | UUID | 观点所属投资者 |
| `asset_id` | UUID | 观点涉及的投资标的 |
| `direction` | string | 观点方向 |
| `strength` | float | 观点强度 |
| `confidence` | float | AI 结果置信度 |
| `thesis` | JSON | 投资逻辑 |
| `catalysts` | JSON | 催化因素 |
| `risks` | JSON | 风险因素 |
| `time_horizon` | string | 投资期限 |

### Direction

```text
STRONG_BEARISH
BEARISH
NEUTRAL
BULLISH
STRONG_BULLISH
```

### Example

```json
{
  "asset": "Tencent",
  "direction": "BULLISH",
  "strength": 85,
  "thesis": ["AI 商业化", "广告恢复"]
}
```

## Thesis Change Artifact

`ThesisChange` is a versioned derived comparison between two effective Opinions for one
Investor × Asset. It is not a replacement for Opinion or State.

### Table

`thesis_changes`

### Fields

| Field | Description |
| --- | --- |
| `investor_id` / `asset_id` | Investor and canonical Asset |
| `previous_opinion_id` / `current_opinion_id` | Compared effective Opinions; previous is nullable for the first Opinion |
| `previous_event_id` / `current_event_id` | Source RawEvents |
| `effective_time` | Current RawEvent.published_time |
| `change_type` | Versioned V0 comparison category |
| `confidence` / `summary` / `evidence` | Structured comparison result |
| `opinion_analysis_version` | Active Opinion interpretation identity |
| `comparison_version` | Independent comparator identity |
| `calculated_at` | Comparison calculation time |
| `input_identity` | Deterministic previous/current/comparison identity |

The first effective Opinion produces `NEW_THESIS` without an LLM comparison. Here “first” means the first
observed thesis in the currently available production-effective Opinion history; it does not claim to be the
investor's first-ever formation of that thesis. Later Opinions compare only with the immediately prior effective
Opinion ordered by fact time. Missing catalysts, risks, or time horizon are `UNKNOWN`/`NOT_EXTRACTED`, not
removal or weakening. A late historical Opinion may create a new comparison pair while preserving the original
`published_time`; superseded predecessor pairings remain historical artifacts but are excluded from the effective
Thesis Change timeline.

## Portfolio Fact Foundation (Sprint 2E.3-A)

Portfolio is an independent fact domain. It is not an Opinion, ThesisChange, or AttentionOccurrence and does not
depend on an LLM:

```text
Portfolio Source
      ↓
PositionSnapshot
      ↓
PortfolioAction
```

`Portfolio` identifies one Investor-owned portfolio by `(source, external_id)`; one Investor may have multiple
portfolios. `PositionSnapshot` records an observed portfolio state at `snapshot_time` and supports either a resolved
`asset_id` or an opaque unresolved `asset_reference_id`, but never both or neither. `created_at` is the system
recording time and is not the fact time.

`PortfolioAction` is a derived difference between two Snapshot Batches. Its `effective_time` is the current batch's
`snapshot_time`; `calculated_at` records when the difference was calculated. Sprint 2E.3-D detects only factual
position changes (`POSITION_ADDED`, `POSITION_REMOVED`, `POSITION_INCREASED`, `POSITION_DECREASED`,
`POSITION_UNCHANGED`, `POSITION_CHANGE_UNKNOWN`) and does not infer BUY/SELL intent.

Each action stores both batch IDs and the available previous/current PositionSnapshot IDs. Resolved positions match
by `asset_id`; unresolved positions match by `asset_reference_id`; the two identity kinds never match each other.

`InvestorActionClaim` is a separate textual claim made by an Investor and is always linked to its source RawEvent.
It is not Portfolio Fact and does not modify Opinion. An unresolved claim may retain an opaque
`asset_reference_id`; no Asset is automatically created.

The foundation tables are `portfolio`, `position_snapshots`, `portfolio_actions`, and `investor_action_claims`.
Portfolio Fact persistence is intentionally separate from the Opinion and Attention lifecycles.

Sprint 2E.3-B adds a source-neutral `PortfolioSnapshotImportCommand` and import service. The service reuses the
deterministic `AssetResolver`, writes one `PositionSnapshot` per input position, and turns unresolved hints into a
stable opaque reference identity without creating an Asset. Snapshot import identity is scoped to
`portfolio_id + snapshot_time + (asset_id or asset_reference_id)` so repeating one external snapshot reuses its
position facts.

Sprint 2E.3-C adds the explicit `PortfolioSnapshotBatch` parent. Sprint 2E.3-D compares two batches through the
deterministic `PositionChangeDetectionService`; no Portfolio Collector or BUY/SELL interpretation is included.

## Opinion × PortfolioAction Consistency (Sprint 2E.3-E)

`InvestorActionConsistency` is a derived analysis artifact linking one production-effective Opinion to one
fact-derived `PortfolioAction`. It does not change either source entity and does not evaluate investment skill,
profitability, or correctness.

### Table

`investor_action_consistencies`

### Identity and fields

The artifact stores `investor_id`, `asset_id`, `opinion_id`, `opinion_direction`, `portfolio_action_id`,
`action_type`, `consistency_type`, `confidence`, structured `evidence`, `effective_time`, `calculated_at`,
`opinion_analysis_version`, and `consistency_policy_version`. `input_identity` deterministically contains the
Opinion ID, Action ID, and consistency policy version and is unique.

Only active production Opinions are eligible. The service matches the latest Opinion whose
`RawEvent.published_time` is at or before the Action `effective_time`; Actions earlier than any eligible Opinion
remain unmatched. `effective_time` is the Action fact time and `calculated_at` is analysis time.

V0 maps bullish/bearish directions against increased/decreased position facts to `POSITIVE_ALIGNMENT` or
`NEGATIVE_ALIGNMENT`. Neutral or absent direction is `NO_DIRECTION`; unsupported/missing evidence is
`INSUFFICIENT_EVIDENCE`. Added, removed, and unchanged actions do not imply BUY/SELL intent.

Sprint 2E.3-C introduces `PortfolioSnapshotBatch` as the parent fact container. Its identity is
`portfolio_id + snapshot_time + source + external_id`; every `PositionSnapshot` must reference exactly one
batch and retain the batch's fact time. This makes the complete observed portfolio state and future
previous/current action provenance explicit without implementing action detection.

## Investor Behavior Snapshot (Sprint 2E.3-F)

`InvestorBehaviorSnapshot` is a derived aggregation for one Investor and one
inclusive fact-time window. It does not replace any source artifact and does
not assign a score or investment recommendation.

### Table

`investor_behavior_snapshots`

### Identity and metrics

The scope is
`investor_id + window_start + window_end`, while the immutable version identity
is the deterministic SHA-256 `input_identity` described below. Multiple input
versions may therefore coexist for one scope after late data or policy changes.
The snapshot stores attention asset/occurrence/new-attention counts, active
Opinion and bullish/bearish counts, ThesisChange/reinforced/changed counts,
PortfolioAction/increased/decreased counts, and positive/negative consistency
counts. `as_of` is the window end for this V0.

`new_attention_count` counts assets whose earliest effective occurrence for the
investor falls inside the requested window. Only active production Opinion
artifacts are included; old or failed analyses never fall back into the
snapshot. All input filtering uses `AttentionOccurrence.published_time`,
`RawEvent.published_time` for Opinion, and `effective_time` for ThesisChange,
`PortfolioAction`, and consistency. `calculated_at` and `created_at` are never
behavior timestamps.

The snapshot is an intelligence aggregation foundation, not Signal, ranking,
portfolio performance, prediction, or recommendation logic.

## Effective derived artifact semantics (Sprint 2E.3-G)

PortfolioAction rows remain append-only. Effective action queries rebuild the
PortfolioSnapshotBatch timeline by `snapshot_time` and deterministic identity
tie-breakers, then retain only adjacent previous/current batch pairs. A late
batch can therefore supersede an older `A -> C` action with `A -> B` and
`B -> C`; the old row remains available for audit.

PortfolioSnapshotBatch has `completeness = FULL | UNKNOWN`. Added/removed
position facts are emitted only for FULL-to-FULL comparisons. An incomplete
comparison emits `POSITION_CHANGE_UNKNOWN` rather than inferring a missing
position. Missing weights also emit `POSITION_CHANGE_UNKNOWN`; this is not a
BUY/SELL inference.

InvestorActionConsistency effective queries require an effective PortfolioAction,
an active Opinion, the latest Opinion at or before the action fact time, and the
current consistency policy. Superseded Opinion/action pairings remain
historical artifacts but are excluded from effective reads.

InvestorBehaviorSnapshot is versioned by a deterministic SHA-256
`input_identity`. The fingerprint includes the investor/window, behavior,
Attention, active Opinion, Thesis comparison, and Consistency policy versions,
and sorted effective upstream artifact IDs plus relevant first-Attention
history dependencies. Its database uniqueness is on `input_identity`, so late
facts create a new immutable snapshot version rather than reusing stale metrics.

## Attention policy and historical dependency closure (Sprint 2E.3-H)

Production BehaviorSnapshot uses the explicit application-approved Attention
policy version. Effective Attention queries filter that version and still
retain analysis-free `EXPLICIT_MENTION` / `REPOST` evidence; `OPINION` evidence
must reference the active Opinion analysis.

`new_attention_count` depends on the first effective Attention for each asset
represented in the requested window. The Snapshot fingerprint therefore
includes the complete effective Attention history up to `window_end` for those
assets, including each first occurrence ID and fact time. A late pre-window
occurrence can change the count and creates a new immutable Snapshot version;
an unrelated asset does not affect the fingerprint.

Snapshot completeness `FULL` / `UNKNOWN` only gates inference from absence.
When both snapshots explicitly contain the same position, known weights remain
eligible for increase, decrease, or unchanged classification even if either
batch is `UNKNOWN`.

## Cross-Investor Asset Evidence Snapshot (Sprint 2F.1)

`CrossInvestorAssetSnapshot` is an asset-centric, fact-time window aggregation
of effective Attention, Opinion, ThesisChange, PortfolioAction, and
InvestorActionConsistency artifacts. It is an evidence inventory, not a
consensus decision, score, ranking, Momentum state, Signal, or recommendation.

### Table and identity

`cross_investor_asset_snapshots`

The snapshot is identified by a deterministic SHA-256 `input_identity` over
the canonical Asset, `as_of`, window, all active upstream policy versions, and
sorted effective upstream artifact IDs. First-effective-Attention identities
and fact times for Investors represented in the window are also included so a
late historical Attention creates a new immutable version. The database
uniqueness constraint is on `input_identity`; old versions remain available.

### Metrics and contributions

The row stores Attention occurrence/Investor counts and first-attention counts;
Opinion counts plus distinct Investor direction counts (the last Opinion per
Investor in the window); ThesisChange counts and distinct Investor counts;
PortfolioAction and Consistency counts. Position-change metrics count only
explicit increased/decreased actions; `POSITION_CHANGE_UNKNOWN` is not counted
as either direction.

`contributions` is structured JSON with one entry per contributing Investor.
Each entry preserves Attention occurrence IDs and first identity/time, the
lifetime window Opinion IDs/count plus the latest window Opinion ID/direction/
time, ThesisChange IDs/types, PortfolioAction IDs/types, and Consistency
IDs/types. This keeps the aggregate answerable as
“which Investors produced this evidence?” without reading `Investor.quality_score`
or introducing weighting.

Sprint 2F.1.2 versions this contribution schema as
`cross-investor-asset-snapshot-v2`. Existing v1 snapshot rows remain immutable
and readable; recalculation writes a v2 row with complete
`window_opinion_ids`/`window_opinion_count` provenance. The latest Opinion is
still used only for direction aggregation.

Only production-effective policy versions are read. Attention uses the active
Attention policy; Opinion and ThesisChange use the active Opinion and
comparison policies; PortfolioAction and Consistency use their effective
fact-time selectors. `published_time` / `effective_time` are behavior times,
while `calculated_at` is calculation time. This snapshot is distinct from the
Sprint 1D `AssetIntelligenceSnapshot`: the latter is an Asset-level state/
consensus foundation, whereas Sprint 2F.1 preserves the cross-Investor
evidence contributions and window provenance needed before any consensus or
divergence logic.

## Cross-Investor Asset Alignment (Sprint 2F.2)

`CrossInvestorAssetSnapshot` is the evidence aggregation input. It cannot
also carry a recomputable policy-specific coverage/alignment result without
mixing evidence inventory with deterministic interpretation, so
`CrossInvestorAssetAlignment` is a separate immutable derived artifact.

### Table

`cross_investor_asset_alignments`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `asset_id` | UUID | Canonical Asset |
| `source_snapshot_id` | UUID | Immutable `CrossInvestorAssetSnapshot` provenance |
| `opinion_coverage_state` | string | `NONE`, `PARTIAL`, or `COMPLETE` |
| `directional_alignment_state` | string | Directional alignment V0 state |
| `alignment_policy_version` | string | `cross-investor-directional-alignment-v1` |
| `input_identity` | string | SHA-256 of source snapshot identity + policy |
| `calculated_at` | timestamp | Deterministic calculation time |
| `created_at` | timestamp | Persistence time |

The table has foreign keys to the Asset and source snapshot, a unique
`input_identity`, and a unique source-snapshot/policy pair. Old artifacts are
kept; identical source snapshot + policy input is reused, while a new source
snapshot or policy creates a new row.

### Opinion Coverage

Only snapshots with `attention_investor_count >= 2` are classified.
`NONE` means zero distinct Opinion Investors, `PARTIAL` means more than
zero but fewer Opinion Investors than Attention Investors, and `COMPLETE`
means the two distinct Investor counts are equal. The Opinion Investor set
must be a subset of the Attention Investor set; otherwise calculation fails
with an integrity error.

### Directional Alignment

Directional alignment is independent of Consensus. It uses only
`latest_window_opinion_direction` once per Investor contribution:
`BULLISH`/`STRONG_BULLISH` map to bullish, `BEARISH`/`STRONG_BEARISH`
map to bearish, and `NEUTRAL` maps to neutral. Fewer than two Opinion
Investors produces `INSUFFICIENT_EVIDENCE`; otherwise all one side produces
`ALIGNED_BULLISH`, `ALIGNED_BEARISH`, or `ALIGNED_NEUTRAL`, and multiple
sides produce `MIXED_DIRECTION`. Multiple Opinion artifacts from one
Investor never add votes.

Directional Alignment != Consensus. This entity does not store a score,
weight, probability, Momentum, Signal, ranking, Divergence Score, or research
recommendation.

## 3.5 InvestorAssetState

### Purpose

核心状态对象，表示某投资者当前如何看待某资产。

### Table

`investor_asset_states`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `investor_id` | UUID | 投资者 |
| `asset_id` | UUID | 投资标的 |
| `attention_level` | string | 关注程度 |
| `direction` | string | 当前观点方向 |
| `conviction` | float | 当前确信程度 |
| `mention_count` | integer | 累计提及次数 |
| `position_status` | string | 当前持仓状态 |
| `last_activity_time` | timestamp | 最近观点时间 |
| `last_material_change_time` | timestamp | 最近状态变化时间 |

### Attention Level

```text
UNKNOWN
DISCOVERED
TRACKING
FOCUS
CORE_FOCUS
ABANDONED
```

### Position Status

```text
NO_POSITION
WATCHING
SMALL_POSITION
CORE_POSITION
REDUCING
EXITED
```

## 3.6 Signal

### Purpose

最终研究信号。

### Table

`signals`

### Fields

| Field | Type | Description |
| --- | --- | --- |
| `id` | UUID | Primary Key |
| `asset_id` | UUID | 投资标的 |
| `signal_score` | float | 信号分数 |
| `signal_level` | string | 信号等级 |
| `tags` | JSON | 信号标签 |
| `reasons` | JSON | 信号依据 |
| `risks` | JSON | 风险因素 |
| `created_at` | timestamp | 创建时间 |

### Signal Level

```text
STRONG_SIGNAL
HIGH_PRIORITY_RESEARCH
WATCH
LOW_PRIORITY
```

---

# 4. Relationship Model

## Investor → RawEvent

一个 Investor 可以拥有多个 RawEvent：

```text
Investor 1:N RawEvent
```

## Investor → Portfolio

一个 Investor 可以拥有多个独立组合：

```text
Investor 1:N Portfolio
```

## RawEvent → Opinion

一个 RawEvent 可以生成多个 Opinion：

```text
RawEvent 1:N Opinion
```

## Asset → Opinion

一个 Asset 可以拥有多个 Opinion：

```text
Asset 1:N Opinion
```

## Investor × Asset

Investor 与 Asset 之间的多对多关系通过 `InvestorAssetState` 实现。

---

# 5. Data Lifecycle

```text
Raw Event Created
        ↓
AI Analysis
        ↓
Opinion Generated
        ↓
State Updated
        ↓
Signal Calculated
        ↓
Dashboard Display
```

---

# 6. AI Data Rules

所有 AI 生成数据必须包含：

```text
confidence
source_event_id
generated_time
model_version
```

这些字段用于支持：

- 模型升级
- 重新计算
- 结果追踪

---

# 7. Future Extension

以下内容暂不实现：

## Portfolio Collector / Action Detection

Portfolio Fact Foundation、Snapshot provenance 和 V0 持仓变化检测已建立；完整组合采集及生产级编排流程仍未实现。

## Industry Trend

记录行业趋势。

## Investor Historical Performance

记录投资能力评价。

## Alert Rules

记录用户提醒规则。

## User Preference

记录个性化排序偏好。

---

# 8. Database Principle

数据库设计优先级：

1. 可追溯
2. 可重新计算
3. 可扩展
4. 性能优化

禁止为了短期开发速度破坏数据结构。

---

# Final Principle

数据模型必须支持几年后仍然能够回答：

> 某个投资者为什么在某一天改变了对某个资产的看法？

这是本系统最核心的数据价值。

---

## Sprint 1F Temporal Processing Model

### Analysis lifecycle

The interpretation layer now distinguishes an analysis result from its zero-to-many Opinions:

```text
RawEvent
    ↓
EventAnalysis
    ↓
0..N Opinion
```

`EventAnalysis` is a recomputable derived result. Its identity is `event_id + analysis_version`, where `AnalysisSpec` centrally carries `analysis_version`, `model_version`, `prompt_version`, and `schema_version`.

`EventAnalysis.status` is one of `SUCCESS`, `NO_OPINION`, `PARTIALLY_RESOLVED`, or `FAILED`. `NO_OPINION`, unresolved assets, and failures are persisted. Failed results are retryable and may be updated by a later attempt; this Sprint intentionally does not create an attempt-history table.

`PARTIALLY_RESOLVED` and `SUCCESS` describe the current resolution completeness of that analysis. Deterministic recovery may update the resolution status and `calculated_at`, but never changes the original LLM `generated_time` or extraction provenance.

New Opinions reference `EventAnalysis.id` through nullable `analysis_id`. The column remains nullable for legacy Opinions created before Sprint 1F; no synthetic historical EventAnalysis rows are created. All new Opinions written by `OpinionProcessingService` have a non-null `analysis_id`.

### State projection and change ledger

`InvestorAssetState` is the current projection. `InvestorAssetStateChange` is an append-only derived ledger because the projection cannot preserve `before`, `after`, transition evidence, or retry identity.

A StateChange is idempotent on `triggering_opinion_id + state_policy_version`. It records `effective_time`, `calculated_at`, `before`, `after`, `source_event_ids`, and the centralized policy version (`state-v1`).

`projection_changed` means any projection field changed. `material_change` means the current transition is `NEW_ATTENTION`, `OPINION_UPGRADE`, `OPINION_DOWNGRADE`, or `OPINION_REVERSAL`. A repeated direction with a new mention may have `projection_changed=true` and `material_change=false`.

The state projection uses `last_activity_time` for the latest effective Opinion business time and `last_material_change_time` for the latest material transition business time. Neither field uses database write time or AI generation time.

### Time semantics and replay

- `as_of`: upper bound on fact-effective time, using `RawEvent.published_time`.
- `generated_time`: time the extractor produced an Analysis/Opinion.
- `calculated_at`: time the system persisted or calculated a derived result.

Historical Asset Intelligence replays effective Opinion timelines through the deterministic State Reducer and does not mutate the current `InvestorAssetState`. This is fact-time replay using the current Analysis and Policy versions; it is not system-time reconstruction of what was known historically.

### Signal boundary

Signal remains outside Sprint 1F. When implemented, it must be an immutable derived snapshot with explicit `as_of`, `calculated_at`, engine version, confidence, and input identity. Existing Signal storage is not changed in this Sprint.

## Sprint 2B.1 Provider-aware analysis identity

`AnalysisSpec` now distinguishes the configured `provider_id` from the requested `model_version` and
also carries `analysis_policy_version`. For the generic Responses + JSON Schema adapter, the
`analysis_version` is derived from a canonical JSON payload containing:

```text
provider_id + model + prompt_version + schema_version + analysis_policy_version
```

The digest excludes API keys, base URL, timeout, retry count, timestamps, response IDs, and random
values. This keeps `event_id + analysis_version` idempotent while allowing multiple providers or models
to produce separate `EventAnalysis` rows for one RawEvent.

Provider response identity and usage are stored in the existing nullable
`event_analyses.provider_metadata` JSON field. No provider-specific table is introduced. A generic
`unresolved_assets` hint may preserve an ambiguous textual asset reference without creating an `Asset`.

### Production Analysis Policy

`ProductionAnalysisPolicy` is the single source for the normal
`OPINION_EXTRACTION` interpretation policy. It explicitly approves one
`AnalysisSpec`; provider runtime defaults do not implicitly activate a new
model or prompt. A database-present `EventAnalysis` is not necessarily
production-effective. State, historical replay, Attention, and Asset
Intelligence use the exact active `analysis_version` and never fall back to
older or failed analyses.

StateChange interpretation provenance is recoverable through
`triggering_opinion_id → Opinion.analysis_id → EventAnalysis.analysis_version`.
The production repository query follows this chain and excludes inactive or
failed analyses; the append-only v4 ledger remains available only to explicit
historical queries.

## Sprint 2E.0 Behavior Evidence Foundation

`AttentionOccurrence` is a recomputable derived record for one Investor × Asset × RawEvent behavior occurrence.
Attention is not the same as Opinion: `OPINION`, `EXPLICIT_MENTION`, and `REPOST` are evidence types that may support
the same occurrence, not three separate behaviors. Identity is `event_id + asset_id + attention_policy_version`.

Interpretation-based downstream reads only the single active `AnalysisSpec.analysis_version`. It never chooses an
analysis by `generated_time`, and a missing or failed active analysis does not fall back to older analyses.

Time semantics remain distinct: `published_time` is behavior effective time, `generated_time` is AI interpretation
time, and `calculated_at` is derived calculation or reconciliation time.

### Current-author opinion attribution

Opinion extraction uses a minimal, provider-neutral current-author view. For an
original event this is the author's text; for a repost or quote chain it stops
at the first `//@` marker and never includes nested
`retweeted_status` text. Quoted speakers are not evidence for the current author's asset, direction,
thesis, catalysts, risks, or time horizon. Repost attention may still be
recorded separately. Missing catalysts, risks, or time horizon mean
UNKNOWN/NOT_EXTRACTED and must not be interpreted as removed, weakened, or
invalidated in future thesis comparisons.
