# Xueqiu Investor Intelligence System

## Data Model Specification

Version: 1.3

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

## Portfolio

记录完整组合。

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
