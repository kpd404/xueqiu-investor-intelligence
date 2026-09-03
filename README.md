# Xueqiu Investor Intelligence System

面向投资者行为变化的、数据源无关的 Investor Behavior Intelligence System。本仓库已完成 Sprint 2E.0 Behavior Evidence Foundation、Sprint 2E.2-A Opinion Attribution & Identity Hardening、Sprint 2E.2-B Production Analysis Policy & Projection Provenance 和 Sprint 2E.2 Thesis Change V0。Attention Momentum 当前进入数据校准暂停阶段。

## Local setup

```powershell
py -3.12 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
alembic upgrade head
uvicorn backend.app.main:app --reload
```

默认未配置 `.env` 时使用本地 SQLite；`.env.example` 提供 PostgreSQL 开发配置。

## Verification

```powershell
pytest
ruff check .
```

API 启动后可访问 `GET /health` 检查应用与数据库连通性。


## Xueqiu Following Feed collector

首次使用时启动可见浏览器，并在浏览器中手动完成登录：

```powershell
python -m collectors.xueqiu.smoke --authenticate
```

Following Feed 运行路径固定为：

```text
用户本人登录
→ https://xueqiu.com/
→ 首页精确「关注」Tab
→ /v4/statuses/home_timeline.json
→ home_timeline
→ FeedPostItem
→ Investor + RawEvent
```

先执行真实 dry-run（会启动 Playwright，但不会打开数据库或写入任何数据）：

```powershell
python -m collectors.xueqiu.smoke --feed --headless --max-batches 1 --dry-run
```

确认 dry-run 输出正常后，再执行小批量入库：

```powershell
python -m collectors.xueqiu.smoke --feed --headless --max-batches 1
```

只采集指定雪球作者时，使用 Following Feed 返回的 platform user ID：

```powershell
python -m collectors.xueqiu.smoke `
  --feed `
  --headless `
  --max-batches 1 `
  --only-investor-ids <XUEQIU_AUTHOR_ID_1> <XUEQIU_AUTHOR_ID_2> `
  --dry-run
```

`max-batches` 表示最多接收的有效 response batch，不表示滚动次数。
dry-run 会输出 batch、received、unique、duplicates 和少量脱敏帖子摘要；正式模式才会
创建或复用 Investor 并写入 RawEvent。认证状态默认保存在已被 Git 忽略的
`.local/xueqiu/storage_state.json`。

Collector 默认通过 Playwright `channel="msedge"` 启动系统 Edge，无需配置固定路径。
如雪球显示登录失效、滑动验证或访问限制页面，Collector 会停止并返回明确错误，
不会尝试绕过。

## Core intelligence pipeline demo

无需实时雪球采集，使用 Manual Import 与 Mock Extractor 运行完整核心链路：

```powershell
python -m pipeline.demo
```

## Generic LLM opinion extraction smoke test

系统支持 OpenAI-compatible Responses API providers。离线测试使用 Fake Client，不会访问公网或消耗
token。真实 smoke test 只从通用环境配置读取，不会回退到 Mock：

```powershell
$env:LLM_PROVIDER_ID="example-provider"
$env:LLM_BASE_URL="https://llm.example.com/v1"
$env:LLM_API_KEY="<secret>"
$env:LLM_MODEL="<provider-model-id>"
$env:LLM_API_STYLE="responses"
$env:LLM_STRUCTURED_OUTPUT="json_schema"
$env:LLM_TIMEOUT_SECONDS="60"
$env:LLM_MAX_RETRIES="2"
python -m ai.smoke
```

例如可以将 `LLM_PROVIDER_ID`、`LLM_BASE_URL`、`LLM_API_KEY` 和 `LLM_MODEL` 替换为任意兼容服务，
不需要修改 Python 代码。缺少必填配置时命令会返回 `CONFIGURATION_ERROR`，不会打印、保存或提交
API Key。建议使用本地 `.env` 时确认该文件已被 `.gitignore` 忽略。

Provider 使用版本化 Prompt `opinion-extraction-v5`、`analysis_policy_version = opinion-analysis-v3` 和结构化 `OpinionExtractionResult`，只抽取 RawEvent 文本中的事件级观点；State、
Consensus、Signal 等仍由确定性领域层计算。Provider 错误会区分认证、限流、超时、不可用和结构化输出失败，
并标记是否可重试。

Opinion extraction receives a minimal current-author analysis view. For reposts
and quote chains, text after the first `//@` marker and nested repost content
are excluded from the LLM input. Quoted speakers are never inherited as the
current author's asset, thesis, catalyst, risk, or direction. Missing
catalysts, risks, or time horizon are recorded as unknown/not extracted; they
are not evidence of removal or weakening.

当前核心链路：

```text
RawEvent
→ CurrentAuthorEventView
→ EventAnalysis
→ Opinion
→ InvestorAssetState
→ InvestorAssetStateChange
→ AttentionOccurrence
→ Historical / Current AssetIntelligenceSnapshot
```


## Project status

当前已完成的核心链路可以离线重放，并且生产解释使用显式批准的 AnalysisSpec：

```text
RawEvent
→ CurrentAuthorEventView
→ opinion-extraction-v5 / opinion-analysis-v3
→ AssetReference
→ deterministic AssetResolver
→ Canonical Asset / AssetAlias
→ Opinion
→ InvestorAssetState / StateChange
→ AttentionOccurrence
→ AssetIntelligenceSnapshot
```

## Production analysis policy

当前 production interpretation 明确使用：

- `prompt_version = opinion-extraction-v5`
- `analysis_policy_version = opinion-analysis-v3`
- explicit production `AnalysisSpec`

Provider runtime defaults 不等于 production approval。Provider 或 model 变化不会自动切换生产解释，必须显式更新批准的
production identity。`database-present Analysis` 也不等于 `production-effective Analysis`：State、StateChange、
historical replay、Attention 和 Asset Intelligence 只消费 active analysis policy；v4/v5 policy 彼此隔离。

## Current capability boundary

已实现：

- Xueqiu Following Feed collection
- Following Feed historical pagination reliability hardening
- RawEvent persistence
- EventAnalysis lifecycle
- OpenAI-compatible real LLM extraction
- `opinion-extraction-v5` current-author-only Opinion extraction
- quote/repost attribution isolation：首个 `//@` 之后的内容及 nested repost 不进入当前作者 Opinion
- deterministic Asset Resolution
- AssetAlias
- evidence-backed Asset Master
- cross-listing / alias safety hardening
- unresolved semantics preservation
- unresolved recovery without rerunning LLM
- Opinion
- InvestorAssetState
- StateChange
- historical replay
- effective State / StateChange / Attention queries
- Behavior Evidence Foundation / AttentionOccurrence
- `OPINION` / `EXPLICIT_MENTION` / `REPOST` evidence attribution
- versioned Thesis Change V0 (`NEW_THESIS` / `THESIS_UNCHANGED` / `THESIS_REINFORCED` /
  `THESIS_EXTENDED` / `THESIS_CHANGED` / `INSUFFICIENT_EVIDENCE`)
- basic Asset Intelligence / Consensus

历史 unresolved analysis 可以在补充可信 Asset / Alias 后重新执行确定性 recovery：

```text
unresolved EventAnalysis
→ Asset / Alias added explicitly
→ deterministic recovery
→ Opinion
```

Recovery 不重新调用 LLM。

## Current / Next

### Sprint 2E.2 — Thesis Change V0

Status: `IMPLEMENTED`

2E.2-A attribution prerequisite 和 2E.2-B production policy prerequisite 已完成。Thesis Change V0
现在支持 fact-time effective Opinion timeline、独立 structured comparator、版本化持久化 artifact 和幂等重算。

V0 已实现的比较类别：

- `NEW_THESIS`
- `THESIS_UNCHANGED`
- `THESIS_REINFORCED`
- `THESIS_EXTENDED`
- `THESIS_CHANGED`
- `INSUFFICIENT_EVIDENCE`

`missing catalysts / risks / time_horizon = UNKNOWN / NOT_EXTRACTED`，不能安全解释为 removed、weakened 或
invalidated。`THESIS_WEAKENED`、`THESIS_INVALIDATED` 和 `thesis removed` 可留作 Future / Later semantics。

`NEW_THESIS` 表示当前可用 production-effective Opinion history 中首次观察到该 Investor × Asset 的 thesis，
不表示投资者历史上第一次形成该观点。迟到历史 Opinion 重新建立 predecessor pairing 时，旧 comparison artifact
保留为历史记录，但 effective Thesis timeline 只返回当前 predecessor 匹配的 artifact。

### Sprint 2E.1 — Attention Momentum

Status: `PAUSED / DATA CALIBRATION / WAITING FOR TEMPORAL COVERAGE`

Momentum 的架构与 Behavior Evidence Foundation 已具备，但真实样本的跨日 / 跨周时间跨度仍不足，14d/28d baseline
尚未定稿。Momentum 需要等待自然积累更多时间序列数据，不是架构失败或工程阻塞。

产品目标保持为：

- recency
- frequency
- acceleration
- decay
- `NEW` / `RISING` / `STABLE` / `COOLING` / `DORMANT`

计算时必须区分 `occurrence_count` / `occurrence frequency`、`distinct active days` 和 `recency`。例如 `3 occurrences / 1 active day`
不能与 `3 occurrences / 3 active days` 视为相同的持续关注强度。当前不定义具体 7d / 14d / 28d 阈值。

2E.1 Momentum 数据校准与 Thesis Change V0 已分别收口；Momentum 仍需等待更长时间序列数据。

## Remaining planned capabilities

- Attention Momentum production logic
- Portfolio Fact Pipeline
- Position Change
- Opinion × Action Consistency
- enhanced Consensus / Divergence
- Multi-investor warming
- Industry / Theme Trend
- Research Signal / Research Candidate
- Scheduler
- Dashboard / Product API

本项目不是 Xueqiu crawler product、stock recommendation system、auto trading system 或 price prediction system；
它是 Investor Behavior Intelligence System，关注谁在关注什么、为什么关注、观点如何变化、是否发生行为，以及多位投资者是否形成共识或分歧。
产品核心原则是：**Change matters more than popularity.**
