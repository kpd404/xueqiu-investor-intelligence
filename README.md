# Xueqiu Investor Intelligence System

面向投资者行为变化的、数据源无关的 Investor Behavior Intelligence System。本仓库已完成 Sprint 2D Asset Resolution 主线，当前路线为 Sprint 2E.1：Attention Momentum MVP。

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

Provider 使用版本化 Prompt `opinion-extraction-v4` 和结构化
`OpinionExtractionResult`，只抽取 RawEvent 文本中的事件级观点；State、Consensus、
Signal 等仍由确定性领域层计算。Provider 错误会区分认证、限流、超时、不可用和结构化
输出失败，并标记是否可重试。

当前核心链路：

```text
RawEvent
→ EventAnalysis
→ Opinion
→ InvestorAssetState
→ InvestorAssetStateChange
→ Historical / Current AssetIntelligenceSnapshot
```


## Project status (Sprint 2D completed)

当前核心链路已离线跑通：

```text
RawEvent
→ EventAnalysis
→ Opinion
→ InvestorAssetState
→ InvestorAssetStateChange
→ Historical / Current AssetIntelligenceSnapshot
```

Sprint 2D keeps traceability, deterministic replay, retry-safe processing, analysis-scoped Opinions, and short
database transactions. The current Asset Intelligence implementation is a basic Asset Intelligence / Consensus
foundation, not a complete Intelligence Engine. Signal storage and evidence contracts exist, but there is no formal
Signal scoring engine; PositionStatus exists, but there is no Portfolio Fact Pipeline.

## Current capability boundary

已实现：

- Xueqiu Following Feed collection
- RawEvent persistence
- EventAnalysis lifecycle
- OpenAI-compatible real LLM extraction
- deterministic Asset Resolution
- AssetAlias
- unresolved semantics preservation
- unresolved recovery without rerunning LLM
- Opinion
- InvestorAssetState
- StateChange
- historical replay
- basic Asset Intelligence / Consensus

当前核心链路：

```text
Xueqiu Following Feed
→ RawEvent
→ EventAnalysis
→ structured Opinion Extraction
→ AssetReference
→ deterministic AssetResolver
→ Canonical Asset / AssetAlias
→ Opinion
→ InvestorAssetState
→ StateChange
→ AssetIntelligenceSnapshot
```

历史 unresolved analysis 可以在补充可信 Asset / Alias 后重新执行确定性 recovery：

```text
unresolved EventAnalysis
→ Asset / Alias added explicitly
→ deterministic recovery
→ Opinion
```

Recovery 不重新调用 LLM。

尚未完整实现：

- Attention Momentum
- Thesis Change
- Portfolio Fact Pipeline
- Position Change
- Opinion × Action Consistency
- Divergence Engine
- Industry / Theme Trend
- Research Signal / Research Candidate
- Scheduler
- Dashboard / Product API

本项目不是 Xueqiu crawler product、stock recommendation system、auto trading system 或 price prediction system；
它是 Investor Behavior Intelligence System，关注谁在关注什么、为什么关注、何时改变观点、是否采取行动，以及多位投资者是否形成共识或分歧。
