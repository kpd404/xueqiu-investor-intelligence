# Xueqiu Investor Intelligence System

## System Architecture Specification

Version: 1.6

---

# 1. Architecture Overview

## 1.1 System Purpose

本系统是一个 AI 驱动的投资情报分析系统。

核心目标是通过采集投资者公开行为，分析：

- 投资者关注变化
- 投资观点变化
- 投资逻辑变化
- 投资行为变化

最终生成 Research Intelligence。

## 1.2 Core Architecture Principle

系统必须遵循 Source Independent Architecture。

核心系统不能依赖任何单一数据来源。雪球只是第一个数据采集来源。

未来可以支持：

- 其他投资社区
- 新闻来源
- 财报数据
- 用户手工输入

## 1.3 Delivery Status

Phase 0 Foundation, Phase 1 Data / Intelligence Foundation, and Phase 2
Intelligence Product Foundation are complete or frozen, including the
collector, real LLM Analysis, Asset / Investor intelligence, Signal/Event/
Priority/Feed projections, Product Views, frontend, and cross-navigation.
Attention Momentum remains paused because historical completeness and temporal
coverage are insufficient for absence-sensitive inference.

The project is now in **Phase 3 — Operational MVP**. The UI and scheduled
refresh/status loop exist for the authenticated local CDP runtime, while
always-on deployment and restart hosting remain deferred. The current gap is
production hosting, not another Intelligence semantic layer.

## 1.4 Operational Architecture

The target Phase 3 path is:

```text
Xueqiu
↓
Collection
↓
Ingestion
↓
RawEvent
↓
Incremental Analysis
↓
Current Resolution
↓
Opinion Materialization
↓
Attention / State / Thesis
↓
Cross-Investor Snapshot / Alignment / Consensus Evidence
↓
Signal
↓
IntelligenceEvent / Evidence
↓
Priority
↓
Feed
↓
Feed Lifecycle
↓
Product Read Models
↓
API
↓
UI
```

The components above already exist in the repository. A thin
**Operational Refresh Orchestrator** now coordinates them in this order and
reports one structured result. Live collection has been proven through an
operator-started authenticated Edge CDP session at
`http://127.0.0.1:9222`; the verified runtime must pass that endpoint
explicitly.

### Operational Boundary Principles

- The Orchestrator coordinates existing semantics; it does not recompute
  semantic rules.
- Each stage remains idempotent and safe to rerun.
- There is no hidden fallback to inactive or failed Analysis identities.
- A failure identifies the exact stage and preserves individual-item failure
  isolation where existing policy allows it.
- Incremental selection is based on database state, never on expected cohort
  counts or hardcoded historical assumptions.
- Product verification reads existing Product services; it does not persist a
  new Product View.
- Historical completeness remains `UNKNOWN`; absence-sensitive inference is
  unsupported.

## 1.5 Scheduled Operational Runtime

Sprint 2 adds a lightweight scheduler around the existing
`OperationalRefreshService`:

```text
Scheduled Trigger
      ↓
OperationalRefreshService
      ↓
OperationalRefreshRun metadata
      ↓
Operational Status API
      ↓
Frontend freshness / failure indicator
```

The scheduler is an in-process, configuration-driven loop. It does not
duplicate refresh stages and does not introduce a workflow engine, queue,
worker, or platform scheduler. It requires the operator-started authenticated
Edge CDP endpoint and reports `CDP_UNAVAILABLE`, authentication, and source
limitation failures explicitly.

Manual and scheduled triggers call the same refresh service. A PostgreSQL
advisory lock prevents concurrent refreshes; a local process lock is used for
SQLite/test execution. A second trigger is recorded as
`SKIPPED_ALREADY_RUNNING`.

`OperationalRefreshRun` is execution metadata only. It stores trigger,
status, timing, failure stage/code, and the structured refresh summary. It
does not contain or calculate Intelligence semantics.

## 6.9 Sprint 2F.0 data reality check

Sprint 2F.0 adds only a read-only audit script; it introduces no domain model,
table, policy, score, or Signal. The latest PostgreSQL calibration reports 42
Investors, 188 RawEvents, 7.98 days of fact-time coverage, 22 effective
AttentionOccurrences, 14 effective Opinions, 14 effective ThesisChange
artifacts, and zero Portfolio facts. Active Analysis coverage is closed at
188/188 with explicit FAILED rows and no fallback. Five Assets are shared by two Investors;
none are shared by three or more. This is sufficient to discuss the shape of
Cross-Investor Intelligence, but not to claim production Consensus/Divergence
robustness or to activate Attention Momentum. Portfolio remains auxiliary until
real snapshot facts exist.

---

# 2. High-Level Architecture

整体架构：

```text
External Sources
       ↓
Data Source Layer
       ↓
Raw Event Layer
       ↓
Investment Understanding Layer
       ↓
Investor Asset State Layer
       ↓
Intelligence Aggregation Layer
       ↓
Signal Engine
       ↓
Application API
       ↓
User Interface
```

---

# 3. Data Source Layer

## 3.1 Responsibility

负责从外部来源获取原始投资者行为数据。

输出：Normalized Raw Events。

## 3.2 Design Principle

Data Source Layer 必须：

- 可替换
- 可扩展
- 与业务逻辑隔离

## 3.3 Adapter Pattern

所有数据来源必须实现统一接口。

例如：

```text
SourceAdapter
├── XueqiuAdapter
├── ManualImportAdapter
└── FutureSourceAdapter
```

---

# 4. Xueqiu Collector Architecture

## 4.1 Background

雪球没有官方开放 API，因此采用 Browser Automation Collector。

技术实现：Playwright。

## 4.2 Architecture

```text
Xueqiu Adapter
      ↓
Browser Manager
      ↓
Authentication
      ↓
Page Navigator
      ↓
Content Extractor
      ↓
Data Normalizer
      ↓
Raw Event
```

## 4.3 Xueqiu Adapter Responsibility

Xueqiu Adapter 只负责：

- 登录
- 页面访问
- 内容获取
- 页面解析
- 数据标准化

禁止负责：

- AI 分析
- 投资判断
- Signal 计算

## 4.4 Following Feed Architecture (Sprint 2C.1)

The formal Xueqiu collection path is the authenticated user's homepage and its
exact `关注` (Following) Feed tab. A profile URL, the `关注97` management page,
`关注精选`, recommendations, hot lists, and watchlists are different contexts
and must not enter this ingestion path.

```text
XueqiuAuthenticator
        ↓
PlaywrightXueqiuBrowser
        ↓
Following UI Context
        ↓
Following Feed Response Capture
        ↓
GET /v4/statuses/home_timeline.json
        ↓
payload["home_timeline"]
        ↓
XueqiuFollowingFeedParser
        ↓
FeedPostItem
        ↓
FeedIngestionService
        ↓
Investor + RawEvent
```

Only the conjunction of the following three observations permits a response to
enter Following Feed ingestion:

1. the browser is in the Following UI context;
2. the response is the confirmed `home_timeline` endpoint; and
3. the payload contains the `home_timeline` container.

The parser reads only `payload["home_timeline"]`; it must not recursively scan
other top-level arrays for status-like objects. Recommendation cards, hot-feed
items, watchlist items, and `关注精选` content are excluded by context, not by
guessing from an individual item's shape.

Following responses are consumed as batches. A batch limit counts valid response
batches, not scroll gestures or page numbers. Pagination remains browser-native:
the Collector observes response-driven progress (new relevant batches, cursor
advancement, and new source event IDs) while the page consumes the next cursor.
Idle scrolling has a finite bound, but a few scrolls without a request do not
imply that pagination has stopped. A scroll is never assumed to produce exactly
one batch. Cursor progression is logged only as sanitized debug metadata.

Following batch parsing is item-isolated. Valid items are retained even when a
single item cannot be normalized. Such item failures carry an index, optional
source event ID, stable error code, and safe structural context; the batch
cursor is still preserved. Only an unrecognizable `home_timeline` container or
invalid batch cursor semantics fail the whole batch.

Every valid feed item is retained as a fact; unnormalizable items remain
represented by batch-level diagnostics. Original posts, reposts, and columns
are not filtered in the Collector layer. `FeedPostItem.content` contains only
the current top-level status text. When a repost contains a nested
`retweeted_status`, that provenance remains in `RawEvent.raw_data`; the nested
text must never be concatenated into the current author's content.

## 4.4.1 Following Feed Runtime and Ingestion Boundary (Sprint 2C.3)

`PlaywrightXueqiuBrowser` and `XueqiuFeedAdapter` remain persistence-free. They
return bounded, de-duplicated `FeedPostItem` values to the application-layer
`FeedIngestionService`. Only that service may resolve
`platform + platform_user_id` to an `Investor`, build a `RawEventDTO`, and call
the database repositories.

```text
PlaywrightXueqiuBrowser
        ↓
XueqiuFeedAdapter
        ↓
FeedIngestionService  (application boundary)
        ↓
InvestorRepository + RawEventRepository
```

The smoke runner supports a real browser dry-run. Dry-run executes the full
Following UI, response capture, parser, and adapter path but does not open a
database session or commit. Normal mode performs only a bounded ingestion run;
the same source event remains idempotent through the existing RawEvent hash.

## 4.5 Browser Automation Rules

Playwright 相关代码必须限制在：

```text
collectors/xueqiu/
```

禁止业务代码直接调用 Playwright。

错误：

```text
SignalService
      ↓
Playwright
```

正确：

```text
XueqiuCollector
      ↓
RawEvent
      ↓
SignalService
```

---

# 5. Raw Event Layer

## 5.1 Responsibility

保存系统观察到的原始事实。

## 5.2 Principle

Raw Event 是系统事实来源。

后续的 AI 分析、状态计算和 Signal 生成全部依赖 Raw Event。

## 5.3 Flow

```text
Collector
    ↓
Raw Event Storage
    ↓
Processing Queue
    ↓
AI Pipeline
```

---

# Portfolio Fact Foundation (Sprint 2E.3-A)

Portfolio is an independent fact stream and must not depend on Opinion,
ThesisChange, AttentionOccurrence, or an AI provider:

```text
Portfolio Source
      ↓
PositionSnapshot
      ↓
PortfolioAction
```

The first import workflow is deliberately small:

```text
External Portfolio Snapshot Input
        ↓
PortfolioSnapshotImportService
        ↓
AssetResolver (deterministic, no creation)
        ↓
PositionSnapshotRepository
        ↓
Portfolio Fact Storage
```

Repeated imports use the same portfolio, snapshot time, and asset identity;
database partial unique indexes protect resolved and unresolved positions from
duplicate facts.

`InvestorActionClaim` is a separate RawEvent-linked text claim. It is not a
portfolio fact and does not modify Opinion. `Portfolio`, `PositionSnapshot`,
`PortfolioAction`, and `InvestorActionClaim` are composed through the dedicated
Portfolio repositories and UnitOfWork. Resolved snapshots reference `asset_id`;
unresolved snapshots retain an opaque `asset_reference_id` without creating an
Asset. The foundation intentionally does not implement a Portfolio Collector
or Signal workflow. V0 position-change detection is deterministic and fact-only;
it does not infer BUY/SELL intent. Opinion × PortfolioAction Consistency is a
separate analysis boundary documented below.

## Sprint 2E.3-C Snapshot Provenance

`PortfolioSnapshotBatch` is the deterministic parent fact for one observed
portfolio snapshot. The import workflow first gets or creates the batch using
`portfolio_id + snapshot_time + source + external_id`, then attaches every
`PositionSnapshot` to that batch. Batch and position persistence are protected
by database uniqueness.

## Sprint 2E.3-E Opinion × PortfolioAction Consistency

Consistency is an independent analysis boundary between two existing domains:

```text
active production Opinion ─┐
                           ├─→ OpinionActionConsistencyService
fact-derived PortfolioAction ┘             ↓
                              InvestorActionConsistency
```

The service reads only active Opinion timelines and PortfolioAction facts. It
does not call AI, modify either source entity, infer BUY/SELL intent, evaluate
performance, or produce Signal. Matching uses the latest Opinion at or before
the Action `effective_time`; an Action before any eligible Opinion is left
unmatched. The artifact retains the active Opinion analysis version and a
versioned consistency policy.

## Sprint 2E.3-D Position Change Detection V0

`PositionChangeDetectionService` compares two batches belonging to the same
Portfolio. It matches resolved positions by `asset_id` and unresolved positions
by `asset_reference_id`; resolved and unresolved identities never cross-match.
The result is persisted as `PortfolioAction` with both batch IDs and previous /
current PositionSnapshot provenance. `effective_time` is the current batch's
`snapshot_time`; `calculated_at` is calculation time. The V0 action taxonomy is
`POSITION_ADDED`, `POSITION_REMOVED`, `POSITION_INCREASED`,
`POSITION_DECREASED`, `POSITION_UNCHANGED`, and `POSITION_CHANGE_UNKNOWN`; it makes no trading-intent
claim and does not depend on Opinion, ThesisChange, Attention, LLM, or Signal.

# 6. Investment Understanding Layer

## 6.1 Responsibility

负责将非结构化文本转换为投资信息。

- 输入：Raw Event
- 输出：Opinion

## 6.2 Components

```text
AI Processing
├── Content Filter
├── Asset Recognition
├── Opinion Extraction
├── Thesis Extraction
└── Report Generation
```

## 6.3 AI Boundary

AI 负责：

- 语言理解
- 信息抽取
- 总结生成

AI 不负责：

- 状态判断
- 数学评分
- 业务规则

## 6.4 Asset Resolution Boundary (Sprint 2D.1–2D.2)

Asset identity is resolved after language extraction and before Opinion
persistence by the source-neutral deterministic `AssetResolver`:

```text
LLM asset mention
        ↓
AssetReference (name/symbol/market hints)
        ↓
AssetResolver
        ├── deterministic normalization
        ├── Canonical Asset + AssetAlias lookup
        └── AssetResolutionResult
                ↓
        Opinion or preserved unresolved semantics
```

`AssetReference` is source-neutral and contains no platform-specific identity.
The Resolver must use explicit canonical and alias matches; it must not infer a
market from symbol length, use external model knowledge, or create an Asset.
Multiple matches produce `AMBIGUOUS`, while missing matches produce
`UNRESOLVED` and retain the complete extracted opinion semantics for later
reprocessing.

## 6.5 Behavior Evidence Boundary (Sprint 2E.0)

Interpretation-based State, historical replay, Asset Intelligence, and Opinion attention consume only the configured
active Opinion AnalysisSpec. Selection is exact by `analysis_version`; there is no generated-time selection or
fallback to older analyses when the active result is missing or failed.

```text
RawEvent + effective Opinion + deterministic mention/repost evidence
        ↓
AttentionOccurrence
```

One Investor × Asset × RawEvent creates at most one occurrence per attention policy version. `OPINION`,
`EXPLICIT_MENTION`, and `REPOST` are merged evidence types. Mention matching and attention policies are pure; ORM and
transaction orchestration remain in repositories and application services.

## 6.6 Investor Behavior Snapshot Foundation (Sprint 2E.3-F)

Behavior Snapshot is an independent aggregation boundary over existing
effective artifacts:

```text
AttentionOccurrence ─┐
Opinion              ├─→ InvestorBehaviorSnapshotService
ThesisChange         │              ↓
PortfolioAction      │     InvestorBehaviorSnapshot
Consistency          ┘
```

The service receives an Investor and an inclusive fact-time window, reads only
active interpretation artifacts plus portfolio facts, and persists one
versioned snapshot per identity. It does not call AI, modify source artifacts,
infer intent, calculate a score, rank investors, or produce Signal.
`published_time` / `effective_time` are behavior times; `calculated_at` is
derived calculation time. Repository and UnitOfWork wiring stay in the
application/infrastructure layer while the behavior service depends only on
provider-neutral contracts.

## 6.7 Effective derived artifact selection (Sprint 2E.3-G)

Derived artifacts are preserved as an append-only history and queried through
deterministic effective selectors:

```text
late PortfolioSnapshotBatch ─┐
late active Opinion          ├─→ effective selectors
policy / fact-time replay    ┘          ↓
                              BehaviorSnapshot aggregation
```

PortfolioAction selection uses adjacent SnapshotBatch fact-time pairs. Consistency
selection requires both an effective action and the latest active Opinion at or
before that action. Behavior Snapshot consumes only these effective inputs and
uses an upstream-ID fingerprint for immutable versioning. No selector falls back
to superseded artifacts or uses calculation time as business time.

## 6.8 Sprint 2E.3-H policy closure

Production Attention policy is explicit and independent from the active Opinion
analysis policy. BehaviorSnapshot carries all active policy versions in its
provenance and never discovers or combines Attention policies from database
rows. Its first-attention metric includes only relevant Investor × Asset
history up to the requested `window_end`, so late historical evidence changes
the input fingerprint without allowing future leakage. Snapshot completeness
only gates absence-based added/removed inference; explicit positions with
known weights remain comparable in an `UNKNOWN` batch.

## 6.10 Cross-Investor Asset Evidence Snapshot (Sprint 2F.1)

Cross-Investor aggregation remains inside the Intelligence layer. It is an
asset-centric, fact-time window over effective AttentionOccurrence, Opinion,
ThesisChange, PortfolioAction, and InvestorActionConsistency artifacts:

```text
effective artifacts + explicit production policies
                    ↓
CrossInvestorAssetSnapshotService
                    ↓
CrossInvestorAssetSnapshot
                    └── per-Investor contributions
```

The snapshot stores artifact counts and structured Investor contributions,
including source IDs, first Attention identity/time, latest window Opinion, and
Thesis/Portfolio/Consistency provenance. Its SHA-256 input identity includes
the Asset, window/as-of, all active policy versions, sorted effective IDs, and
first-Attention history dependencies. Late facts or policy changes create a
new immutable version; unchanged inputs are reused.

This is evidence aggregation only. It does not calculate consensus direction,
divergence, warming, Momentum, scores, rankings, or Signals. The existing
Sprint 1D `AssetIntelligenceSnapshot` remains compatible and is a separate
Asset-level state/consensus foundation; it is not replaced by this cross-
Investor provenance artifact.

Sprint 2F.1.2 closes contribution provenance by storing every effective Opinion
ID in the window per Investor (`window_opinion_ids` and count), while retaining
the latest Opinion separately for direction aggregation. This is a new
`cross-investor-asset-snapshot-v2` artifact version; v1 rows remain historical.

---

## 6.11 Cross-Investor Asset Alignment (Sprint 2F.2)

The cross-investor layer has two separate deterministic artifacts:

```text
CrossInvestorAssetSnapshot
        │
        └── Evidence Aggregation
                    ↓
        CrossInvestorAssetAlignment
        Deterministic Coverage + Directional Alignment
```

`CrossInvestorAssetAlignment` reads exactly one immutable source snapshot.
Its service depends on provider-neutral snapshot views and a UnitOfWork port;
ORM/SQLAlchemy remains in the repository adapter. The artifact keeps the
source snapshot ID, alignment policy version, and a SHA-256 fingerprint of
the source snapshot `input_identity` plus that policy.

Only snapshots with at least two Attention Investors are classified. The
service validates that the distinct Investor set with window Opinions is a
subset of the distinct Attention Investor set before classification. Coverage
is `NONE`, `PARTIAL`, or `COMPLETE`. Directional alignment uses one latest
Opinion direction per Investor: bullish/strong bullish, bearish/strong
bearish, or neutral. Multiple Opinions from one Investor do not add votes.

The states are `INSUFFICIENT_EVIDENCE`, `ALIGNED_BULLISH`,
`ALIGNED_BEARISH`, `ALIGNED_NEUTRAL`, and `MIXED_DIRECTION`.
Directional Alignment != Consensus. This boundary does not calculate
Consensus, Divergence Score, Strength, Probability, Heat, Warming, Momentum,
Investor weighting/ranking, Signal, Research Candidate, or LLM output.

---

# 7. Investor Asset State Layer

## 7.1 Responsibility

维护 Investor × Asset 的动态状态。

## 7.2 Example

```text
Investor A × Tencent

Before: Neutral
       ↓
New Event: Bullish
       ↓
State Transition: Opinion Upgrade
```

## 7.3 Design

状态更新由 Business Logic Engine 负责，而不是 LLM。

---

# 8. Intelligence Aggregation Layer

## 8.1 Responsibility

将单个投资者行为聚合为市场情报。

## 8.2 Modules

```text
Intelligence Engine
├── Attention Momentum
├── Consensus Engine
├── Divergence Engine
├── Position Confirmation
└── Industry Trend
```

---

# 9. Signal Engine

## 9.1 Responsibility

生成研究信号。

## 9.2 Input

Asset Intelligence。

## 9.3 Output

Research Signal。

## 9.4 Rule

Signal 必须可解释，并且必须输出：

- Score
- Evidence
- Reason
- Risk

---

# 10. Application Layer

## 10.1 Responsibility

提供用户访问接口。

## 10.2 API Example

```http
GET /signals
GET /assets/{id}
GET /investors/{id}
GET /timeline/{asset}
```

---

# 11. Storage Architecture

## 11.1 Primary Database

负责存储结构化数据，包括：

- Investor
- Asset
- RawEvent
- Opinion
- State
- Portfolio Fact Foundation
- Signal

## 11.2 Future Storage

未来可能增加 Vector Database，用于：

- 语义搜索
- 相似观点
- 历史研究

---

# 12. Service Boundary

系统服务划分：

```text
Backend
├── Collector Service
├── AI Processing Service
├── Intelligence Service
├── Signal Service
└── API Service
```

---

# 13. Dependency Rules

## Rule 1: Collector Service

可以写入 Raw Event，不能生成 Signal。

## Rule 2: AI Processing Service

可以读取 Raw Event 并生成 Opinion，不能直接修改 State。

## Rule 3: Intelligence Service

可以读取 Opinion 并更新状态。

## Rule 4: Signal Service

可以读取 Intelligence 并生成 Signal。

---

# 14. Data Flow

完整流程：

```text
User defines Investor
        ↓
Collector collects content
        ↓
Raw Event created
        ↓
AI Analysis
        ↓
Opinion created
        ↓
Investor Asset State updated
        ↓
Aggregation
        ↓
Signal generated
        ↓
Dashboard display
```

---

# 15. Future Scalability

## 15.1 More Platforms

例如：

- Eastmoney
- Weibo
- Reddit
- Research Reports

## 15.2 More Assets

支持：

- Stocks
- ETFs
- Funds
- Commodities
- Themes

## 15.3 More Intelligence

未来支持：

- RAG Research Agent
- Historical Performance Evaluation
- Personal Investment Assistant

---

# 16. Architecture Anti-Patterns

## 16.1 Source Coupling

禁止核心业务直接依赖雪球。

## 16.2 AI Coupling

禁止业务逻辑依赖某个特定 LLM。

## 16.3 Raw Data Mutation

禁止修改历史原始数据。

## 16.4 Black Box Signal

禁止输出无法解释的分数。

---

# Final Architecture Principle

本系统不是雪球分析工具，雪球只是一个数据入口。

真正的核心资产，是通过长期积累形成的 Investor Behavior Intelligence Graph。

系统必须能够回答：

> 谁在什么时候，因为什么原因，改变了对什么资产的看法，以及这种变化是否正在形成市场趋势？

---

## Sprint 1F Processing Hardening

### Analysis boundary

The Investment Understanding layer persists one `EventAnalysis` per `RawEvent + AnalysisSpec.analysis_version` before writing zero or more `Opinion` rows. `AnalysisSpec` is a neutral immutable contract; it carries model, prompt, schema, and logical analysis versions without introducing a live Prompt Registry.

`NO_OPINION`, partial resolution, and failed extraction are valid lifecycle outcomes. A completed analysis is reused on the same identity. A failed analysis may be retried through the Analysis-ingestion path; post-analysis Asset recovery is not allowed to update an existing `EventAnalysis` row.

### Immutable Analysis resolution materialization

`EventAnalysis` is an analysis-time immutable artifact after persistence. Asset
Master expansion is a separate deterministic boundary: the current Asset
catalog is applied to the immutable `structured_output` to produce a
query-time resolution projection, and only extracted entries from
`structured_output.opinions` can be materialized as missing Opinions. Direct
unresolved hints remain non-materializable. This path preserves the persisted
Analysis status (including `PARTIALLY_RESOLVED`) and all Analysis metadata.

The materialization service supports dry-run planning, explicit listing/Asset
allowlists, and RawEvent/Analysis delta scopes. Opinion writes retain the
existing `event_id + asset_id + analysis_id` idempotency boundary. There is no
resolution persistence table or new migration in this V0.

### State boundary

The State layer owns deterministic reduction. `InvestorAssetState` is the latest projection. `InvestorAssetStateChange` is an append-only ledger for material transitions and is written in the same transaction as the projection update. Its unique identity is `triggering_opinion_id + state_policy_version`.

The reducer exposes separate `projection_changed` and `material_change` semantics. `last_activity_time` and `last_material_change_time` both use `RawEvent.published_time`; `generated_time` and `calculated_at` remain provenance/calculation timestamps.

### Historical calculation

Asset Intelligence never uses the latest projection as a historical shortcut. For `asset_id + as_of`, it groups Opinion timelines, applies `RawEvent.published_time <= as_of`, rebuilds each Investor × Asset state with the deterministic reducer, and aggregates those transient states. The current projection is never mutated by replay.

### Processing outcomes

The application Pipeline returns a stable `ProcessingOutcome`: `SUCCEEDED`, `PARTIALLY_SUCCEEDED`, `RETRYABLE_FAILED`, or `PERMANENTLY_FAILED`. Warnings carry a stable code, stage, and retryable flag; messages are diagnostic only. Programming errors are not converted into warnings. Missing RawEvents remain typed terminal errors.

### Transaction boundary

`DataPipeline` commits each RawEvent (or future small batch) before awaiting the next external Collector DTO. Browser, Playwright, and network waits never hold an open database transaction. Collector adapters remain source-only and Xueqiu verification behavior is unchanged.

### Explicit non-goals

Sprint 1F does not implement Real LLM providers, Prompt Registry, Signal Score, Research Candidate, Scheduler, Job/Lease/Heartbeat, Dashboard, Portfolio, Alerts, RAG, Backtesting, or Xueqiu verification bypass.

## Sprint 2B.1 Generic LLM Provider Boundary

The Investment Understanding layer uses one provider-neutral adapter:

```text
OpinionExtractor
├── MockOpinionExtractor
└── OpenAICompatibleOpinionExtractor
```

The adapter treats the OpenAI Python SDK as a protocol client. `LLMProviderConfig` supplies the
provider ID, public base URL, API key, model, Responses API style, JSON Schema mode, timeout, retry
limit, and the small capability profile. Provider names and model names are never special-cased in
business code.

Structured output uses the standard Responses `text.format.type=json_schema` request and validates the
returned JSON with the shared Pydantic `OpinionExtractionResult`. The adapter does not use Chat
Completions, free-text JSON fallback, tool calling, or provider-specific reasoning fields.

`AnalysisSpec.analysis_version` is a deterministic identity derived from provider ID, model, prompt
version, schema version, and analysis policy version. Runtime credentials and transport settings are
excluded. `EventAnalysis.provider_metadata` remains the only persistence extension for provider/base
URL/response/usage metadata; no new provider table is introduced.

## Sprint 2E.2-B Production Analysis Policy

Normal application composition obtains the active Opinion interpretation from
the neutral `ProductionAnalysisPolicy` source (`analysis_type =
OPINION_EXTRACTION`). The approved `analysis_version` is checked against the
semantic identity derived from the configured provider and model; provider
defaults alone do not switch production behavior. Historical or experimental
callers may pass an explicit `EffectiveAnalysisPolicy`.

State projections, effective StateChange queries, AttentionOccurrence queries,
historical replay, and Asset Intelligence all consume the same active
`analysis_version`. A database-present Analysis is not automatically effective,
and a failed active Analysis never falls back to an older one.

StateChange provenance is resolved through
`triggering_opinion_id → Opinion.analysis_id → EventAnalysis.analysis_version`.
The active-ledger repository query applies this join; v4 ledger rows remain
append-only historical data and are excluded from the production view.

## Sprint 2E.2 Thesis Change V0

Thesis Change compares each current active Opinion with the immediately prior
active Opinion for the same Investor × Asset, ordered by
`RawEvent.published_time`, `RawEvent.id`, and `Opinion.id`. The first effective
Opinion deterministically produces `NEW_THESIS`; “first” means first observed
within the currently available production-effective history, not the investor's
first-ever formation of the thesis. Later pairs use a separate versioned
`ThesisComparator` structured-output port. If late history changes a predecessor,
the old artifact remains append-only but the effective query returns only the
pairing that matches the current predecessor timeline.

``BT@@text
Effective Opinion Timeline
        ↓
ThesisComparator (independent prompt/schema/policy)
        ↓
ThesisChange artifact
``BT@@

`ThesisChange` stores both Opinion/Event identities, effective and calculation
times, comparison version, input identity, summary, and evidence. Missing
catalysts, risks, or time horizon are `UNKNOWN`/`NOT_EXTRACTED`, never evidence
of removal or weakening. Historical `as_of` and late recovery use fact-time
predecessor selection; they do not create a new current behavior.

## Sprint 2E.2-A Opinion Attribution Boundary

The OpinionExtractor receives a minimal current-author analysis view from the
contracts layer. Original events use their author text; repost and quote-chain
events exclude text after the first `//@` marker and all nested
`retweeted_status` content. The RawEvent fact remains unchanged. Quoted or
nested speakers cannot supply the current author's asset, thesis, catalysts,
risks, time horizon, direction, or strength. Repost evidence remains owned by
the Attention layer.

`opinion-analysis-v3` and `opinion-extraction-v5` identify this attribution
policy. Missing catalysts, risks, or time horizon are
`UNKNOWN`/`NOT_EXTRACTED`, not thesis removal or weakening.

## Sprint 2F.3.2 Cross-Investor Consensus Evidence Semantic Hardening

Consensus/Divergence is a separate immutable evidence artifact derived from
exactly one CrossInvestorAssetSnapshot v2 and its CrossInvestorAssetAlignment
v1. It is separate because the Snapshot is an evidence inventory while this
artifact is a policy-versioned deterministic classification.

Both policy versions remain readable:

    CrossInvestorAssetSnapshot v2
                 +
    CrossInvestorAssetAlignment v1
                 ↓
    CrossInvestorConsensusEvidence v1 or v2

Only the latest window Opinion direction from each Investor contribution is
used. Three or more Opinion Investors are required for an eligible v2
classification; fewer produce INSUFFICIENT_EVIDENCE while retaining
the Attention/Opinion coverage. The artifact stores source IDs, contribution
IDs/directions, counts, coverage, and a deterministic input identity that
includes the Consensus policy version.

The original policy
`cross-investor-consensus-evidence-v1` classifies any combination of
multiple direction sides as `DIVERGENT` and is preserved as immutable
historical evidence. The active policy
`cross-investor-consensus-evidence-v2` reserves `DIVERGENT` for a
direct bullish/bearish conflict. Bullish or bearish combined only with
Neutral is `MIXED_WITH_NEUTRAL`; Neutral is not an opposing direction.

The Alignment state `MIXED_DIRECTION` remains broader: it means that
multiple direction sides are present in the Alignment view. It is not
equivalent to Consensus `DIVERGENT`.

This layer does not calculate a score, weight Investors, rank Assets, calculate
Momentum/Warming, call an LLM, or produce a Signal or Research Candidate.

## Intelligence Query Layer V0

The Intelligence Query Layer is a read-only adapter over the existing effective RawEvent, EventAnalysis, Opinion, AttentionOccurrence, ThesisChange, and Cross-Investor artifacts. It exposes Investor and Asset projections without creating a second semantic pipeline or persistence model.

The Asset projection reads persisted Snapshot, Alignment, and Consensus state; it does not recompute Consensus from Opinion counts. Thesis entries are ordered by fact-time published/effective time and retain their existing change type. Historical completeness remains UNKNOWN and absence inference remains unsupported.

The Query Layer exposes /api/intelligence/investors/{investor_id}, /api/intelligence/assets/{asset_id}, and /api/intelligence/search. Search uses bounded batch identity queries and preserves market+symbol listing identity.

SignalCandidateView is a non-persisted, deterministic projection of existing Attention, ThesisChange, Cross-Investor, and Consensus evidence. No Signal table, score, ranking, recommendation, or LLM call is part of this layer.

## Signal Engine V0

The Signal Layer sits after the immutable fact and Query layers:

    RawEvent / EventAnalysis / Opinion / Attention / Thesis / Cross-Investor
                                      ↓
                              Intelligence Query Layer
                                      ↓
                              Signal Engine V0

Signal is derived observable intelligence, not a source fact and not a recommendation. V0 generates only deterministic evidence-backed types: NEW_ATTENTION from the first effective Investor × Asset AttentionOccurrence, THESIS_CHANGE from effective ThesisChange artifacts, CROSS_INVESTOR_ALIGNMENT from non-insufficient persisted Alignment artifacts, and CONSENSUS_CHANGE from persisted Consensus states that are DIVERGENT or a Consensus state.

Each Signal stores its Asset, optional Investor, source artifact type and ID, observed time, lifecycle state, severity field, and metadata. The unique identity is (signal_type, source_id), so repeated generation reuses the same Signal. The source artifacts are never rewritten.

The legacy score-oriented signals table was empty and is replaced by the Signal evidence schema through migration 20260916_0020 with a non-empty safety guard. No signal_score, ranking, recommendation, or LLM logic is part of Signal Engine V0. Signal lifecycle state is persisted, while future resolution/supersession policy remains a separate explicit step.

## Intelligence Event Aggregation V0

IntelligenceEvent is an aggregate derived from existing atomic Signal rows. The aggregation layer reads active Signals and creates only four deterministic event types: ASSET_ACTIVITY_SPIKE, INVESTOR_VIEW_CHANGE, CROSS_INVESTOR_DISCOVERY, and CONSENSUS_STATE_CHANGE.

Each aggregate is scoped by event type and Asset and is linked to every contributing Signal through IntelligenceEventEvidence. The complete audit chain is IntelligenceEvent → Signal → source artifact. Signal, Opinion, Attention, Thesis, and Cross-Investor artifacts are never rewritten.

The aggregation layer has no LLM, recommendation, ranking, score, or trading semantics. Event state is ACTIVE or RESOLVED; V0 materializes ACTIVE events and leaves later lifecycle transitions to an explicit policy.

## Intelligence Priority Layer V0

Intelligence Priority is a derived observation-priority classification over IntelligenceEvent. It does not alter Signal or any upstream fact/interpretation artifact.

V0 assigns a fixed PriorityLevel and PriorityReason from deterministic event facts: an ASSET_ACTIVITY_SPIKE with at least three observed Investors is MULTI_INVESTOR_ATTENTION/HIGH; an INVESTOR_VIEW_CHANGE with multiple ThesisChange evidence is THESIS_ACCELERATION/MEDIUM; CROSS_INVESTOR_DISCOVERY is LOW; and CONSENSUS_STATE_CHANGE is HIGH. These levels are explainable observation classes, not scores, rankings, recommendations, or trading advice.

Each IntelligenceEvent has at most one priority row and the row stores the linked event and its evidence count. The persistence identity is event_id; repeated materialization reuses the existing row.

## Intelligence Feed Projection V0

The Intelligence Feed is a presentation projection over IntelligenceEvent and IntelligenceEventPriority. Each FeedItem is keyed by one Priority and retains its Asset, event type, reason, observed time, deterministic title, and compact context counts.

Context is derived from the linked IntelligenceEventEvidence and Signal rows: investor_count is the distinct Investors represented by the Signals, signal_count is the linked Signal count, and source_count is the distinct source artifact identity count. The full chain remains FeedItem → Priority → IntelligenceEvent → Evidence → Signal → source artifact.

Feed state is NEW, ACTIVE, STALE, or RESOLVED. V0 creates NEW items and does not rank, score, recommend, predict, call an LLM, or mutate any upstream artifact.


## Intelligence Discovery Candidate V1

The Intelligence Discovery layer is a read-only, deterministic projection over
ACTIVE IntelligenceFeedItem rows and their Priority -> IntelligenceEvent ->
IntelligenceEventEvidence -> Signal chain. It emits one non-persisted candidate
per Asset with listing identity, distinct investor/signal/event/feed counts,
event and priority summaries, fact-time bounds, and explicit discovery reasons.

Discovery ordering is latest_observed_at descending for temporal browsing only.
It has no score, rank, weight, recommendation, investment-advice, or LLM
semantics, and it never mutates FeedItem or any upstream artifact.


## Intelligence Narrative Layer V0

The Narrative layer is a query-time, read-only template projection over an
existing DiscoveryCandidate. It describes observed Asset activity using the
existing FeedItem -> Priority -> IntelligenceEvent -> Evidence -> Signal chain.
It does not recompute Consensus, Alignment, ThesisChange, or Signal semantics.

Narratives contain listing identity, factual activity summaries, event/thesis/
cross-investor/consensus observations, evidence counts, observed time bounds,
and explicit data limitations. The layer has no persistence table, migration,
LLM rewrite, score, rank, weight, recommendation, prediction, or advice
semantics.

## Intelligence Context & Comparison Layer V0

The Context layer is a query-time comparison over existing Discovery, Feed,
Signal, ThesisChange, and Cross-Investor artifacts. It uses explicit current
and previous fact-time windows and reports only counts, participant identity
sets, persisted ThesisChange types, and persisted Cross-Investor states.

Context never recalculates Consensus, Alignment, Thesis classification, or
Signal generation. It has no persistence table, score, ranking, hotness,
importance, recommendation, prediction, advice, or LLM semantics.

## Intelligence Pattern Detection Layer V0

The Pattern layer is a query-time, deterministic classification over the
existing Context projection and persisted Intelligence artifacts. It emits
fact-based labels such as multi-investor expansion, thesis transition,
consensus formation/fragmentation, and insufficient history.

Pattern detection does not create persistence, recalculate Signal/Consensus/
Alignment/Thesis semantics, rank Assets, calculate a score, recommend, predict,
or call an LLM. The multi-investor threshold is configurable and the
comparison window reuses the Context window configuration.

## Intelligence Evolution Timeline Layer V0

Evolution is a query-time, read-only, fact-time ordered view over persisted
Signals, IntelligenceEvents, ThesisChanges, Attention evidence, and
Cross-Investor artifacts. It emits canonical EvolutionSteps with source
references and deterministic tie-breaks; it does not create phases or stories.

Pattern activity labels and historical data-quality limitations remain
separate: INSUFFICIENT_HISTORY is not an activity Pattern. Historical
completeness remains UNKNOWN, so Evolution never infers absence, cooling, or
dormancy.

## Intelligence Attention Classification V0 (Sprint 2I.26)

Attention Classification is a query-time presentation/review projection over
the existing effective IntelligenceEvent, Priority, ACTIVE FeedItem,
DiscoveryCandidate, Pattern, and Evolution views. It is a deterministic
answer to:

> What review priority should a human reader use for this observed
> Intelligence?

It is not Investment ranking, expected return, investment attractiveness,
recommendation, prediction, or trading advice. It creates no table, migration,
or persisted row and never modifies FeedItem, Priority, Pattern, Evolution, or
any upstream fact/artifact.

The contract is IntelligenceAttentionClassificationView:

- asset preserves canonical market + symbol listing identity.
- attention_class is one of IMMEDIATE_REVIEW, ACTIVE_REVIEW,
  BACKGROUND_MONITORING, or LIMITED_CONTEXT.
- reasons is a fixed ordered set of deterministic rule explanations.
- evidence_summary, evidence_refs, current Pattern/Alignment/Consensus
  state, latest observed time, and limitations preserve explainability.

The projection does not contain a score, rank, weight, hotness,
recommendation, prediction, buy/sell, target-price, or LLM field.

### Classification rule precedence

Rules are centralized in
intelligence/attention_classification/rules.py:

1. Explicit change evidence produces IMMEDIATE_REVIEW: a
   CONSENSUS_STATE_CHANGE, explicit CONSENSUS_FRAGMENTATION
   (MIXED_DIRECTION or DIVERGENT evidence), multi-investor expansion,
   thesis transition, or an existing HIGH Priority evidence.
2. Otherwise, any effective ACTIVE IntelligenceEvent, Priority, ACTIVE Feed,
   or DiscoveryCandidate produces ACTIVE_REVIEW.
3. Otherwise, a positive historical Signal/Attention/Thesis/Cross-Investor
   artifact produces BACKGROUND_MONITORING.
4. Otherwise the Asset returns LIMITED_CONTEXT.

LIMITED_CONTEXT is a data-quality/boundary expression, not a severity
override. Limitations remain attached when explicit evidence supports a higher
review class. INSUFFICIENT_EVIDENCE is preserved as insufficient coverage;
it is never converted into disagreement or evidence absence.

Historical completeness is still UNKNOWN. Classification never uses a zero
previous-window count to infer no previous Attention, dormancy, cooling,
reactivation, or historical newness. The existing Pattern producer was
hardened accordingly: absence-sensitive NEW_DISCOVERY and zero-baseline
acceleration are not emitted without positive prior-window evidence.

### Read API

GET /api/intelligence/assets/{asset_id}/attention-classification is a
read-only projection. Unknown Assets return 404. An Asset with insufficient
coverage returns LIMITED_CONTEXT or a higher evidence-backed class with an
explicit limitation; it is never synthesized or filled by inference.

## Derived Layer Architecture Audit (Sprint 2I.26)

| Layer | Independent responsibility | Storage |
| --- | --- | --- |
| Priority | Classify one persisted IntelligenceEvent into an explainable observation-priority class | persisted |
| Feed | Preserve one user-facing item and lifecycle state for one Priority | persisted |
| Discovery | Group only ACTIVE FeedItems by Asset for temporal browsing | query-time |
| Narrative | Render a deterministic fact-only textual projection of Discovery | query-time |
| Context | Compare explicit current/previous observed-time windows | query-time |
| Pattern | Label reusable fact patterns over Context and persisted states | query-time |
| Evolution | Order canonical fact/artifact references on a fact-time timeline | query-time |
| Attention Classification | Compose explicit change/active/history/data-boundary facts into human review semantics | query-time |

The boundaries are currently defensible: Priority and Feed are persisted
because they provide stable downstream identities and Feed lifecycle state;
Discovery, Narrative, Context, Pattern, Evolution, and Attention Classification
are projections and should remain non-persisted.

The audit found limited semantic overlap, not a correctness-breaking
dependency inversion:

- Priority's multi-investor/HIGH rule and Pattern's
  MULTI_INVESTOR_EXPANSION describe related evidence at different
  aggregation stages; Classification consumes both as existing evidence and
  does not recompute either.
- Pattern current labels and Evolution current_state.patterns expose the
  same current Pattern semantics, while Evolution additionally owns the
  ordered timeline. This is a duplication risk for future read APIs.
- Narrative is mostly deterministic field reformatting over Discovery and has
  limited independent semantic value. It can later be folded into a product
  presentation adapter.
- Evolution currently composes Context/Pattern/Discovery through multiple
  read scopes. A shared read snapshot can reduce repeated queries later, but
  that is a performance/consistency convergence task, not a reason for a
  broad refactor in this Sprint.

No existing persisted artifact should be merged or removed now. The next
Sprint should prefer architecture convergence and product consumption:
introduce a shared Asset Intelligence read scope, reduce repeated
query-service composition, and decide whether Narrative remains a standalone
consumer adapter. Do not add another backend semantic layer until these
consumers establish a concrete need.

## Asset Intelligence Product Read Model V0 (Sprint 2I.27)

Sprint 2I.27 introduces Product composition, not a new Intelligence semantic
layer. AssetIntelligenceView answers what the system currently knows about
one canonical listing-level Asset by composing the existing Discovery,
Narrative, Context, Pattern, Evolution, Feed/Event lifecycle, and Attention
Classification projections.

The Product View is query-time only and contains:

- canonical Asset identity;
- human review classification and reasons;
- Discovery eligibility and existing activity summary;
- persisted Alignment/Consensus plus current Pattern labels;
- existing Context and deterministic Narrative projections;
- bounded recent Evolution steps and the complete timeline range;
- separate Feed and IntelligenceEvent lifecycle-state summaries;
- explicit data-quality boundaries; and
- complete evidence references for traceability.

It does not calculate a score, ranking, weight, hotness, recommendation,
prediction, expected return, buy/sell action, or target price. The endpoint is:

    GET /api/intelligence/assets/{asset_id}/view

An existing Asset returns a Product View even when it has no ACTIVE FeedItem
or DiscoveryCandidate. Unknown Assets return 404.

### Shared Asset Intelligence Read Scope

AssetIntelligenceReadScope is an immutable, typed, read-only, Asset-scoped
input snapshot. It loads only the requested listing's Asset, Signals,
IntelligenceEvents, Event evidence, Priorities, FeedItems, effective
ThesisChanges, effective AttentionOccurrences, Cross-Investor Snapshots,
Alignments, and Consensus evidence.

The scope owns reading and canonical grouping only. It does not classify,
summarize, narrate, or create a new semantic. Discovery, Context, Evolution,
Narrative, and Attention Classification expose scope-based composition paths;
Pattern continues to consume the single Context result. Evolution receives
that same Pattern result and does not calculate a second Pattern semantic.

The real PostgreSQL query audit for one Asset changed from:

- old six-endpoint composition: 107 SELECT statements and 21 transaction SET
  statements (128 total);
- unified Product View: 12 SELECT statements and 3 transaction SET statements
  (15 total).

Repository reads are bounded by source type, not by the number of Event or
Signal rows, so the Product path has no per-artifact N+1 query.

### ACTIVE state semantics

The four related states are intentionally distinct:

1. IntelligenceEvent.state = ACTIVE means the persisted aggregate has not
   been explicitly RESOLVED. V0 creates Events as ACTIVE and currently has no
   automatic resolution transition. It does not establish current-time
   activity or freshness.
2. FeedItem.state = ACTIVE is Feed presentation/lifecycle eligibility. It is
   advanced from NEW and may become STALE or RESOLVED by the Feed lifecycle
   policy. It is not a claim about current market or investor behavior.
3. DiscoveryCandidate existence means the Asset is currently eligible for the
   Product Discovery surface because at least one FeedItem is ACTIVE. It does
   not mean the Asset has no historical Intelligence when absent.
4. ACTIVE_REVIEW is a human review class. It can follow current Product
   discovery/feed eligibility when no immediate trigger exists, but it is not
   equivalent to Event ACTIVE or Feed ACTIVE.

The previous rule treated Event ACTIVE alone as ACTIVE_REVIEW. This was a
semantic correctness bug because Event ACTIVE is an unresolved/default
lifecycle state. The rule now requires ACTIVE Feed/Discovery eligibility.
China National Offshore Oil Corporation (HK:00883), which has one ACTIVE
unresolved Event but no Priority, FeedItem, or DiscoveryCandidate, is therefore
BACKGROUND_MONITORING while retaining its Attention, Thesis, Evolution, and
Event-state evidence.

### Classification discrimination audit

Before semantic hardening, all 39 Discovery Assets were IMMEDIATE_REVIEW.
Twenty-three Assets were immediate only because every current ThesisChange,
including NEW_THESIS, THESIS_UNCHANGED, and INSUFFICIENT_EVIDENCE, was labeled
THESIS_TRANSITION.

THESIS_TRANSITION now consumes only the existing material ThesisChange
semantics THESIS_REINFORCED, THESIS_EXTENDED, and THESIS_CHANGED. It does not
reinterpret or rewrite ThesisChange artifacts. The resulting real-data
distribution is:

- Discovery: 39;
- IMMEDIATE_REVIEW: 35;
- ACTIVE_REVIEW: 4;
- BACKGROUND_MONITORING: 14;
- LIMITED_CONTEXT: 0;
- Discovery intersection Immediate: 35;
- Discovery minus Immediate: 4;
- Immediate minus Discovery: 0.

The change restores Product discrimination without targeting a desired class
distribution.

### Data-quality semantics

The Product View always states:

- historical_completeness = UNKNOWN;
- historical_comparison_supported = false; and
- absence_inference_supported = false.

The canonical provenance wording is:

> Available collection provenance does not establish historical completeness.

This acknowledges CollectionRun, CollectionObservation, and RawEvent
provenance without claiming that those partial records prove historical
coverage.

### Derived layer consolidation decisions

| Layer | Decision | Independent responsibility | Persistence | Future consolidation |
| --- | --- | --- | --- | --- |
| Priority | KEEP | Persisted Event presentation classification | persisted | keep |
| Feed | KEEP | Presentation lifecycle and stable Product eligibility | persisted | keep |
| Discovery | COMPOSE | ACTIVE Feed grouping and Product discovery eligibility | query-time | compose from shared scope |
| Narrative | COMPOSE | Deterministic Product copy/presentation | query-time | future merge into presentation adapter is allowed |
| Context | KEEP | Explicit fact-time window comparison | query-time | compose from shared scope |
| Pattern | KEEP | Reusable current semantic labels | query-time | keep one implementation |
| Evolution | KEEP | Chronological evidence timeline | query-time | compose the existing Pattern result |
| Attention Classification | KEEP | Human review semantics | query-time | compose from shared scope |
| Product View | COMPOSE | Stable consumer contract over existing layers | query-time | not an Intelligence semantic layer |

Backend Intelligence semantic-layer expansion should stop at this boundary.
The next product step should consume this API from the existing Product V0 UI,
while historical completeness remains the primary data-readiness limitation.

## Product Intelligence UI Integration V0 (Sprint 2J.0)

The existing React/TypeScript/Vite Product V0 now consumes the unified Product
View on the existing Asset Detail route. Asset Detail calls exactly one
Product View request:

    GET /api/intelligence/assets/{asset_id}/view

Asset Discovery continues to use its bounded collection endpoint and does not
request one Product View per card. Discovery answers which observed Assets can
be opened; Asset Detail explains the complete composed Intelligence.

The UI presents Review Classification as human review priority, never as an
Investment Rating. Alignment and Consensus remain separate fields. Feed ACTIVE
and IntelligenceEvent ACTIVE are labeled as lifecycle states and are not
described as current investor activity. Data quality remains quiet, explicit,
and non-blocking:

- historical completeness is UNKNOWN;
- historical comparison is unsupported for this Product View V0; and
- absence inference is unsupported.

Evolution renders recent fact-time steps, not synthetic phases. Traceability
renders source counts and persisted source references. Listing identity is
always Asset ID + market + symbol; Asset name is never used as a UI key or
cache identity, preserving A/H isolation.

## Investor Intelligence Product Read Model V0 (Sprint 2J.1)

Sprint 2J.1 adds the query-time `InvestorIntelligenceView` as the product
composition counterpart to `AssetIntelligenceView`. It answers what the
system has observed about one Investor without adding a new Intelligence
semantic layer or rewriting the existing Investor API.

The read path is:

```text
InvestorIntelligenceReadScope
        ↓
effective Attention / Opinion / ThesisChange + Asset identity
        ↓
InvestorIntelligenceView
        ↓
existing Investor Detail Product V0
```

`InvestorIntelligenceReadScope` is immutable, Investor-scoped, typed,
read-only, and bounded to one request. It loads the Investor, effective
AttentionOccurrences, effective Opinion timeline, effective ThesisChanges,
and the referenced listing-level Assets once. It only reads and canonically
groups facts; it does not calculate Opinion, ThesisChange, Signal,
Cross-Investor state, Asset Intelligence, quality, or ranking semantics.

The Product View preserves the following distinctions:

- Investor Attention is an observed AttentionOccurrence, not an Opinion.
- Opinion is a persisted interpretation and its latest direction is read from
  the latest effective persisted Opinion only; it is not a recommendation.
- Repeated Attention is an occurrence count and does not establish conviction,
  skill, quality, influence, or a ranking.
- Attention-only means no effective persisted Opinion is present in this read
  scope. It does not mean disinterest, lack of conviction, or a negative view.
- `THESIS_UNCHANGED`, `INSUFFICIENT_EVIDENCE`, `NEW_THESIS`, and each other
  ThesisChange enum retain their source semantic. Product composition does not
  turn every ThesisChange into a material transition.
- Historical completeness remains UNKNOWN. Historical absence cannot be
  inferred from a zero previous window or a missing current artifact.

The endpoint is:

    GET /api/intelligence/investors/{investor_id}/view

Unknown Investors return 404. An existing Investor with Attention and no
Opinion still returns a valid Product View. The route is read-only and does
not persist the composition.

Investor Discovery remains a collection surface and does not request one
Product View per card. Investor Detail makes one Investor-specific Product
View request. Its Asset rows navigate to the existing Asset Detail using
`asset_id`; the page does not prefetch one Asset Product View for every row.
This completes the Investor → Asset half of the product navigation without
introducing a frontend N+1. Asset Evolution now resolves the Investor name
from the existing Investor catalog when available and falls back to a short
canonical ID; this is a presentation mapping, not a new backend semantic.
Sprint 2J.2 completes the direct Asset → Investor click-through using the
same catalog mapping and canonical Investor ID.

The real PostgreSQL query audit for Investor `管我财` changed from the legacy
Investor Detail composition's 342 SELECT statements and 15 transaction/setup
statements (357 total) to 6 SELECT statements and 3 transaction/setup
statements (9 total) for the unified Product View. The new path has no
Investor × Asset repository loop.

The Product UI is an evidence workspace. It exposes recorded counts,
listing-level Asset identity, latest persisted Opinion direction, ThesisChange
type, fact-time activity, data-quality limitations, and source-reference
counts. It never renders Investor score, ranking, recommendation, prediction,
expected return, buy/sell language, or target price.

## Product Cross-Navigation & Polish V0 (Sprint 2J.2)

The Product Navigation Graph is now:

```text
Asset Discovery
      ↓
Asset Intelligence Detail
      ↔
Investor Intelligence Detail
      ↑
Investor Discovery
```

Both directions use canonical IDs:

- Asset → Investor uses `investor_id` from Asset Evolution/source context.
- Investor → Asset uses `asset_id` and preserves market/symbol listing identity.

The frontend uses semantic deep-link anchors with SPA pushState handling for
normal clicks. Direct URL entry and browser Back remain valid because each
detail page independently requests its own Product View. No hover prefetch or
per-row Product View request is introduced.

Investor names come from the existing Investor catalog. If a name cannot be
resolved, the UI falls back to a short Investor ID; the route always retains
the full `investor_id`. Asset names never act as route or React identity.

The Product UI keeps full API contracts but reduces default information density:
Asset Narrative detail is collapsed behind a secondary disclosure, while
Review, Patterns, Context, Evolution, and Data Quality remain directly
available. Traceability remains count-first with technical IDs behind an
expandable section.

Empty-state policy is evidence-safe:

> No intelligence evidence is available for this Investor in the currently
> collected records.

This wording is used only for an existing Investor with no currently collected
Attention, Opinion, or Thesis artifact. It never claims that the Investor has
never discussed an Asset. Historical completeness remains UNKNOWN, historical
comparison remains unsupported, and absence inference remains unsupported.

Sprint 2J.2 changes only Product navigation and presentation. It adds no
backend endpoint, Intelligence semantic, persistence, migration, collection
scope, ranking, score, recommendation, or prediction.

## 1.6 Phase 4 Collection Coverage Extension

IYR-1 extends only the Data Source / Collection boundary:

    Authenticated Xueqiu CDP
            ├── Following Feed
            └── Monitored Investor Recent Profile History
                        ↓
              Existing RawEvent hash boundary
                        ↓
              Existing Analysis / Intelligence / Product pipeline

The profile branch reuses collectors.xueqiu.investor_history. It does not
create a second RawEvent pipeline, a Watchlist, or a new persistence model.
The cohort is selected from existing registered Xueqiu Investor identities and
bounded to eight Investors per refresh. The profile window is 48 hours with
two pages and a 30-second per-Investor duration bound.

CDP mode connects to the existing authenticated browser, reuses an existing
Xueqiu page, and navigates that page to each selected profile. It never creates
a fresh browser context, copies cookies, or launches a second browser. A
profile probe failure is reported per Investor; authentication, risk-control,
and CDP failures remain runtime-level collection failures.

Following Feed and profile runs use existing CollectionRun modes and
CollectionObservation edges. Their observations carry strategy provenance,
while RawEvent identity remains the canonical source-event hash. Both paths
therefore converge before Analysis and share all existing semantic stages.

IYR-1 does not modify Analysis, Opinion, Attention, Thesis, Cross-Investor,
Signal, Event, Priority, Feed, Product View, Asset Resolution, or historical
completeness semantics. IYR-2 Asset Resolution Yield Recovery remains
deferred.