# Xueqiu Investor Intelligence System

## System Architecture Specification

Version: 1.1

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

## 4.4 Browser Automation Rules

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

`NO_OPINION`, partial resolution, and failed extraction are valid lifecycle outcomes. A completed analysis is reused on the same identity. A failed analysis may be retried and updated; no Scheduler, Job, PipelineRun, Lease, or attempt-history infrastructure is introduced here.

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
