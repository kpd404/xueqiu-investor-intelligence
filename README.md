# Xueqiu Investor Intelligence System

## Current phase

Phase 3 — Operational MVP and Phase 4 — Intelligence Yield Recovery are
complete. The current implementation is **Phase 5 — Always-On Product Runtime**;
P5-1 and P5-2 are complete. The Intelligence semantic layer is frozen except
for proven correctness bugs. The product is a **Browseable, manually refreshable
Intelligence Product** with durable local runtime and database recovery. It is
not Production Ready because cloud deployment, off-host backup, and centralized
secrets management remain deferred.

## One-command refresh

The verified canonical full refresh command is:

```powershell
python -m operations.refresh --cdp-endpoint http://127.0.0.1:9222
```

The endpoint must refer to an operator-started, authenticated Edge session.
The refresh command does not guess an endpoint, create a second authenticated
session, or automate login. `python -m operations.refresh` remains available
for the storage-state browser path, but the explicit CDP command is the
verified live runtime.

It runs the existing pipeline in order:

```text
Following Feed collection
→ RawEvent ingestion
→ missing current-production Analysis only
→ Current Analysis resolution / Opinion materialization
→ affected Investor × Asset state, Attention, and Thesis derivation
→ affected-Asset Cross-Investor Snapshot / Alignment / Consensus evidence
→ Signal
→ IntelligenceEvent and Evidence
→ Priority
→ Feed projection and Feed lifecycle
→ Asset / Investor Product View verification
```

Selection is database-driven and the command is safe to rerun. It does not
perform historical backfill, add semantic layers, add scheduler support, or
create orchestration persistence. Collection authentication and Xueqiu
risk-control failures are reported explicitly at the Collection stage.

The refresh summary is structured and includes counts, stage durations, LLM
request counts, affected entities, and the final `SUCCESS`,
`PARTIAL_FAILURE`, or `FAILED` result.

### OMVP-1 verification status

**COMPLETE.** On 2026-09-20, explicit CDP smoke returned one Following Feed
batch with 16 real items. The canonical refresh created 16 RawEvents,
processed all 16 under the unchanged production Analysis identity, issued 16
LLM requests, and produced 13 `NO_OPINION` plus 3
`PARTIALLY_RESOLVED` results with zero failures. No Asset was fabricated for
unresolved/no-opinion items. Product verification read four affected
Investor Product Views successfully.

A second identical CDP refresh observed the same 16 source items as existing,
created zero RawEvents, issued zero LLM requests, and produced no duplicate
Opinion, Attention, Thesis, Signal, Event, Priority, or Feed artifacts.

## Scheduled refresh

Sprint 2 adds a lightweight scheduler that calls the same canonical refresh
service:

```powershell
python -m operations.scheduler --cdp-endpoint http://127.0.0.1:9222
```

The default interval is 60 minutes and is configurable with
`OPERATIONAL_REFRESH_INTERVAL_MINUTES`. Freshness becomes stale after
`OPERATIONAL_REFRESH_STALE_AFTER_MINUTES` (default: 90 minutes).

For one scheduled tick:

```powershell
python -m operations.scheduler --cdp-endpoint http://127.0.0.1:9222 --once
```

The local operator must keep the authenticated Edge CDP session running.
The scheduler does not log in, start a browser farm, or bypass Xueqiu
verification.

Operational status is available at:

```text
GET /api/operations/status
```

The response supports user-facing states such as Healthy, Data stale, Xueqiu
login required, Source temporarily limited, and Refresh failed.

## Advanced / Debugging

Current delivery status includes Sprint 2E.3-G/H correctness closure and
Sprint 2F.0 Data Reality Check, Sprint 2F.1 Cross-Investor Asset Evidence
Snapshot Foundation, Sprint 2F.2 Opinion Coverage & Directional Alignment V0,
and Sprint 2F.2.6 Full Production Analysis Backfill & Recalibration, plus
Sprint 2F.2.7 Asset Resolution Reality Calibration & Safe Coverage Expansion.
Sprint 2F.3 Cross-Investor Consensus / Divergence Evidence V0 is also complete.
The latest calibration remains data-limited:
Attention Momentum remains paused pending natural multi-week coverage.

面向投资者行为变化的、数据源无关的 Investor Behavior Intelligence System。本仓库已完成 Sprint 2E.0 Behavior Evidence Foundation、Sprint 2E.2-A Opinion Attribution & Identity Hardening、Sprint 2E.2-B Production Analysis Policy & Projection Provenance、Sprint 2E.2 Thesis Change V0 和 Sprint 2E.3-A–F Portfolio / Behavior foundations。Attention Momentum 当前进入数据校准暂停阶段。

## Frontend language

Chinese UI is the default presentation language for the React frontend. API contracts, internal enum values, and backend intelligence semantics remain unchanged.

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


### Xueqiu Following Feed collector

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

### Core intelligence pipeline demo

无需实时雪球采集，使用 Manual Import 与 Mock Extractor 运行完整核心链路：

```powershell
python -m pipeline.demo
```

### Generic LLM opinion extraction smoke test

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

### Production analysis recovery

Full backfill 只处理当前 production AnalysisSpec 下缺少 Analysis 的 RawEvent；已经存在的有效 Analysis
不会重跑，FAILED 会保留真实失败状态。命令支持通过重复执行从 remaining missing set 断点续跑；完成后会按
既有边界依次重建 Opinion projection、Attention、ThesisChange、CrossInvestorAssetSnapshot 和
CrossInvestorAssetAlignment：

    python -m scripts.recover_production_analysis --batch-size 8 --analysis-concurrency 4 --attention-concurrency 6

该命令不新增表、不删除旧 Analysis 或 Snapshot，也不实现 Consensus、Momentum、Ranking 或 Signal。

Unresolved Asset taxonomy and the bounded safe expansion manifest can be
reviewed with:

    python -m scripts.audit_asset_resolution
    python -m scripts.seed_asset_resolution_expansion --dry-run

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


### Project status

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
- Portfolio Fact ingestion foundation
- Portfolio SnapshotBatch provenance
- deterministic Portfolio Position Change Detection V0
- Opinion × PortfolioAction Consistency V0
- InvestorBehaviorSnapshot aggregation foundation
- Sprint 2F.0 Data Reality Check / Intelligence Calibration (read-only audit)
- CrossInvestorAssetSnapshot evidence aggregation foundation
- CrossInvestorAssetAlignment deterministic Opinion Coverage / Directional Alignment V0
- CrossInvestorConsensusEvidence deterministic Consensus / Divergence evidence V0

历史 unresolved analysis 可以在补充可信 Asset / Alias 后重新执行确定性 recovery：

```text
unresolved EventAnalysis
→ Asset / Alias added explicitly
→ deterministic recovery
→ Opinion
```

Recovery 不重新调用 LLM。

## Investor Behavior Snapshot Foundation (Sprint 2E.3-F)

`InvestorBehaviorSnapshot` is a deterministic, window-scoped aggregation of
active AttentionOccurrence, Opinion, ThesisChange, PortfolioAction, and
InvestorActionConsistency artifacts. All counters use their source fact times
(`published_time` or `effective_time`); `calculated_at` records only when the
snapshot was computed. Snapshot scope is the investor and inclusive window;
its immutable version identity is a deterministic SHA-256 fingerprint of active
policies and effective upstream artifact IDs, so identical inputs are reused
while late facts create a new version.

This is an intelligence aggregation foundation. It is not a score, ranking,
prediction, recommendation, Signal, or dashboard API. Portfolio Collector,
advanced Portfolio Intelligence, Attention Momentum, and other downstream
capabilities remain separate work.

## Effective derived artifacts (Sprint 2E.3-G)

PortfolioAction, InvestorActionConsistency, and InvestorBehaviorSnapshot are
append-only derived artifacts with explicit effective-selection rules. Late
SnapshotBatch or Opinion facts can supersede an earlier derived pairing without
deleting its historical row. Effective downstream queries select only current
adjacent batch transitions and current active Opinion/action matches.

Behavior snapshots use a SHA-256 input identity containing the active policy
versions and effective upstream artifact IDs. If late data changes those
inputs, a new snapshot version is created; an identical input reuses the
existing version. Snapshot completeness is `FULL` or `UNKNOWN`, and missing
weights produce `POSITION_CHANGE_UNKNOWN`, never an inferred trade.

## Sprint 2E.3-H closure

Production BehaviorSnapshot reads one explicit Attention policy together with
the active Opinion, Thesis comparison, and Consistency policies. Its
`new_attention_count` fingerprint includes the first effective Attention
identity for each asset represented in the window, so a late pre-window fact
creates a new snapshot version and recalculates the metric. The 2E
single-investor intelligence foundation is now correctness-closed; the next
engineering phase is Cross-Investor Intelligence (Sprint 2F).

## Sprint 2F.0 data reality check

The read-only calibration audit is available at
`scripts/audit_intelligence_data.py` and runs with:

```powershell
python scripts/audit_intelligence_data.py
```

The latest real PostgreSQL snowball audit (after one bounded Following Feed
backfill and active-analysis closure) contains 42 Investors, 188 RawEvents,
364 EventAnalyses, 14 canonical Assets, 22 effective AttentionOccurrences,
14 effective Opinions, 14 effective ThesisChange artifacts, and no
Portfolio/Snapshot/Action or Consistency facts. The observed `published_time` span is 7.98 days
(2026-08-27 through 2026-09-04); the browser-native Feed stopped after one
batch with `NO_PROGRESS`, so no deeper history was forced.

Five Assets are currently observed across two Investors, while no Asset has
three or more Investors. This is a calibration-scale overlap foundation, not
yet a robust production Consensus/Divergence dataset. Portfolio evidence is
currently absent and therefore auxiliary. Attention Momentum remains paused
until natural multi-week coverage is available; this audit does not implement
Momentum, scoring, ranking, or Signal.

Sprint 2F.0.1 closed active Opinion coverage at 188/188 (including explicit
FAILED results without fallback). The two new evidence-backed Assets were
resolved deterministically and produced two Opinions; no additional LLM
analysis was run after recovery.

## Sprint 2F.1 Cross-Investor Asset Evidence Snapshot

`CrossInvestorAssetSnapshot` is an asset-centric, fact-time aggregation of
effective Attention, Opinion, ThesisChange, PortfolioAction, and Consistency
artifacts. It preserves the per-Investor contribution IDs, latest window
Opinion direction, first Attention identity/time, and active policy versions.
Its deterministic SHA-256 input identity creates an immutable new version when
late facts or policy inputs change, and reuses the same row for identical input.

This is an evidence foundation only. It does not calculate consensus direction,
divergence, warming, Momentum, scores, ranking, Signal, or Research Candidate.
The Sprint 1D `AssetIntelligenceSnapshot` remains a separate Asset-level state
and basic Consensus foundation; it is not replaced by this cross-Investor
snapshot.

Sprint 2F.1.2 adds complete `window_opinion_ids` and
`window_opinion_count` provenance to each Investor contribution. This is
versioned as `cross-investor-asset-snapshot-v2`; v1 snapshots remain preserved
for audit and are not overwritten.

Portfolio Fact ingestion now groups imported positions under a deterministic
`PortfolioSnapshotBatch`. Repeating the same portfolio snapshot reuses both the
batch and its position facts. Portfolio Collector、完整生产级 PortfolioAction
编排、Performance Analysis 和 Signal 仍未实现。

Position Change Detection V0 已实现两个 SnapshotBatch 之间的事实差异比较，输出
`POSITION_ADDED`、`POSITION_REMOVED`、`POSITION_INCREASED`、`POSITION_DECREASED` 或
`POSITION_UNCHANGED`、`POSITION_CHANGE_UNKNOWN`，不推断 BUY/SELL 意图。完整 Portfolio Collector 与生产编排仍未实现。

## Sprint 2F.2 Opinion Coverage & Directional Alignment V0

`CrossInvestorAssetAlignment` is a deterministic, immutable derived artifact
from one `CrossInvestorAssetSnapshot`. It classifies only snapshots with at
least two Attention Investors:

- `OpinionCoverageState`: `NONE`, `PARTIAL`, or `COMPLETE`
- `DirectionalAlignmentState`: `INSUFFICIENT_EVIDENCE`,
  `ALIGNED_BULLISH`, `ALIGNED_BEARISH`, `ALIGNED_NEUTRAL`, or
  `MIXED_DIRECTION`

Coverage compares distinct Opinion Investors with distinct Attention
Investors. Direction uses only each Investor contribution's latest window
Opinion; `STRONG_BULLISH`/`STRONG_BEARISH` map to the corresponding side, and
multiple Opinions from one Investor never create extra votes. An Opinion
Investor outside the Attention Investor set is an explicit integrity error.

The policy is `cross-investor-directional-alignment-v1`. Its SHA-256
`input_identity` contains the immutable source snapshot `input_identity` and
the alignment policy version. Repeating the same source/policy reuses the
artifact; a new source snapshot or policy appends a new artifact.

Directional Alignment != Consensus. This sprint implements no Consensus,
Divergence Score, weighting, ranking, Momentum, Signal, or Research Candidate.

## Sprint 2F.3 Consensus / Divergence Evidence V0

CrossInvestorConsensusEvidence is an immutable, policy-versioned evidence
artifact derived from one Snapshot v2 and its Alignment v1. It uses one latest
Opinion direction per Investor and requires at least three Opinion Investors
for an eligible classification. Lower coverage remains
INSUFFICIENT_EVIDENCE while preserving the Attention/Opinion coverage.

The original `cross-investor-consensus-evidence-v1` policy treats every
combination of multiple direction sides as `DIVERGENT`. V1 artifacts remain
immutable historical evidence and are never overwritten.

## Sprint 2F.3.2 Consensus Evidence Semantic Hardening

The active policy is
`cross-investor-consensus-evidence-v2`. It still uses exactly one
`latest_window_opinion_direction` per Investor and preserves the same
provenance, counts, coverage, and source Snapshot/Alignment identity.

V2 reserves `DIVERGENT` for a direct bullish-versus-bearish conflict.
`BULLISH + NEUTRAL` and `BEARISH + NEUTRAL` are classified as
`MIXED_WITH_NEUTRAL`; Neutral is not an opposing direction. `MIXED_DIRECTION`
from Sprint 2F.2 remains the broader Alignment state meaning that multiple
direction sides are present.

The real calibration has one eligible Asset:
`招商轮船 (SH:601872)`, with latest directions
`BULLISH / NEUTRAL / NEUTRAL`, now classified as
`MIXED_WITH_NEUTRAL`. There is no real v2 Consensus and no real v2
`DIVERGENT` case. V1 and V2 artifacts coexist immutably through the policy
version in their input identity.

This boundary does not implement Consensus scores, Investor weighting,
Ranking, Momentum, Warming, Signal, or Research Candidate.

## Historical semantic status (frozen reference)

The following sections preserve completed semantic work and known data
calibration facts. They are not the current implementation roadmap; Phase 3
Operational MVP is the active direction.

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
- Portfolio Collector
- Portfolio position-change production orchestration
- Portfolio Intelligence / Performance Analysis
- broader Consensus / Divergence semantics
- Multi-investor warming
- Industry / Theme Trend
- Research Signal / Research Candidate
- Daily Intelligence Inbox and since-last-visit workflows
- notifications and always-on deployment
- always-on runtime and production deployment

本项目不是 Xueqiu crawler product、stock recommendation system、auto trading system 或 price prediction system；
它是 Investor Behavior Intelligence System，关注谁在关注什么、为什么关注、观点如何变化、是否发生行为，以及多位投资者是否形成共识或分歧。
产品核心原则是：**Change matters more than popularity.**

## Phase 4 — Intelligence Yield Recovery / IYR-1–IYR-3 ✅

IYR-1 adds bounded Monitored Investor Direct Recent Collection to the existing
authenticated Xueqiu runtime. The canonical command remains:

    python -m operations.refresh --cdp-endpoint http://127.0.0.1:9222

The refresh now combines Following Feed collection with a dynamically selected
cohort of up to eight registered Xueqiu Investors. The cohort uses existing
Investor identities and recent/effective evidence; it is not a Watchlist or
user preference product. Direct profile collection uses a 48-hour overlap,
at most two pages and 30 seconds per Investor, reuses the authenticated CDP
context/page, and preserves historical_completeness=UNKNOWN.

Following Feed and Investor Profile observations use the existing
CollectionRun / CollectionObservation model and the same RawEvent hash
deduplication boundary. No new Intelligence semantic, Asset Resolution policy,
migration, scheduler pipeline, or persistence model was added.

The real IYR-1 validation increased RawEvents from 1,615 to 1,707. The
successful bounded direct-profile run attempted eight Investors, succeeded for
all eight, found 52 Profile-only new RawEvents, and produced 36 ORIGINAL,
68 REPOST, and 3 other profile items. Existing Production Analysis and
downstream Product verification completed successfully.

IYR-2 Safe Asset Resolution Yield Recovery is also complete. Asset references
with `market=CN` are normalized to SH or SZ only when an explicit six-digit
symbol has a supported deterministic exchange prefix. The controlled Asset
Master adds only `SZ:300308` (中际旭创) and `SZ:300502` (新易盛), with
market-scoped symbol aliases. US securities, indexes, themes, commodities,
unknown prefixes, and ambiguous A/H names remain unresolved.

Resolution maintenance uses the existing runner's narrow no-LLM mode:

    python -m scripts.recover_production_analysis --resolution-only --event-id <UUID>

This mode stops after AssetResolver, current-resolution projection, and
Opinion materialization. It does not construct Analysis or Thesis LLM
providers and does not run Attention, Thesis, Signal, Event, Priority, or
Feed stages. Production idempotency verification processed 45 Analysis rows
with zero LLM calls and zero database-count changes.

### IYR-3 — Yield Re-validation & Phase 4 Exit Gate ✅

Status: **COMPLETE**. A real authenticated canonical refresh was executed on
2026-09-21 using the bounded default profile cohort. The current refresh saw
79 source items and created 46 new RawEvents: 16 Following Feed events and 30
profile-only events. The eight direct probes succeeded 8/8. The new-event
cohort contained 15 ORIGINAL, 29 REPOST, and 2 other events, with 16
opinion-bearing Analyses, 6 effective Opinions, 7 AttentionOccurrences, and 6
ThesisChanges (5 material), plus 13 new Signals.

The strict pre-IYR 24-hour collection window contained 22 RawEvents from four
Investors, all REPOSTs, with 18 NO_OPINION and 4 PARTIALLY_RESOLVED
Analyses. The post-refresh new cohort therefore materially improved source
coverage, ORIGINAL content mix, Opinion-bearing yield, and downstream
Attention/Thesis/Signal production. Asset resolution safely retains
SZ:300308 and SZ:300502; recent unresolved references are predominantly
UNKNOWN or legitimate unsupported/index/concept/commodity categories.

The refresh completed all stages successfully. Event identity did not grow in
this run because the existing (event_type, asset_id) aggregates were reused;
13 new Signal-to-Event evidence links were added. Priority and Feed identities
were also reused under the existing policy. The rolling 24-hour Inbox was
non-empty with 11 FeedItems across 7 Assets and 9 Investors. Product View
verification succeeded for affected Assets and Investors. No correctness
blocker was found. Phase 4 is no longer structurally starved, although the
monitored cohort remains intentionally bounded at eight Investors.

The next primary mainline is **Always-On Hosting / Restart Recovery**. Cohort
expansion remains a later bounded-coverage option; it is not part of IYR-3.

## Phase 5 - Always-On Product Runtime

### P5-1 - Durable Local Runtime & Restart Recovery

Status: **COMPLETE**.

The local runtime now has canonical, idempotent Windows entry points:

    pwsh -NoProfile -File .\scripts\start-runtime.ps1 -StartEdge
    pwsh -NoProfile -File .\scripts\stop-runtime.ps1
    pwsh -NoProfile -File .\scripts\runtime-status.ps1

Optional interactive-login setup:

    pwsh -NoProfile -File .\scripts\install-runtime-task.ps1

The runtime topology is:

    PostgreSQL
        |-- Backend: uvicorn backend.app.main:app :8000
        |-- Scheduler: python -m operations.scheduler : no listener
        |       |-- authenticated Edge CDP :9222
        |-- Frontend: Vite :5173 -> Backend API

The scripts are process-scoped, use bounded rotating logs under
.local/runtime/logs, preserve the authenticated-CDP boundary, and never embed
credentials, cookies, tokens, or API keys. The application scheduler remains
the refresh cadence loop; Windows startup/task execution is separate OS-level
process orchestration. PostgreSQL remains the source of truth for refresh
status, freshness, failure stage, and failure code. The existing PostgreSQL
advisory lock remains the refresh-level single-instance protection.

The runtime procedure was exercised with real local processes. Backend,
scheduler, and frontend started; a second start reused existing processes;
scheduler crash recovery and backend crash recovery restarted through the
canonical entry point; full stop-all/start-all recovery restored the API,
Inbox, Asset Product View, and Investor Product View. A real CDP-unavailable
refresh recorded CDP_UNAVAILABLE and the Product status exposed
ACTION_REQUIRED. The rolling Inbox remained readable after backend restart.

P5-1 Closure was verified after Windows restart: canonical Edge CDP on
127.0.0.1:9222 used the existing authenticated interactive profile, the
bounded smoke observed one Following Feed batch with 16 valid items, and a
SCHEDULED refresh completed successfully. The final runtime status was
HEALTHY / FRESH. Historical CDP_UNAVAILABLE remains visible in Operational
Status history. This is durable local runtime work, not Cloud Production Ready
deployment.

### P5-2 - Backup / Restore & Secrets Safety

Status: **COMPLETE**.

The local PostgreSQL recovery boundary now has canonical operator scripts:

    pwsh -NoProfile -File .\scripts\backup-database.ps1
    pwsh -NoProfile -File .\scripts\restore-database.ps1 `
      -BackupPath .\.local\backups\<backup>.dump `
      -TargetDatabase snowball_restore_verify_<run-id>

Backups are PostgreSQL custom-format database artifacts plus a non-secret
manifest containing schema metadata, migration head, critical row counts, and
SHA-256. Restore requires a new `snowball_restore_verify_*` database, refuses
an existing target, never drops or overwrites a database, and runs Alembic,
integrity/identity, Product View, Inbox, and Operational Status verification.
The database remains the source of truth; browser profiles, cookies, tokens,
API keys, and `.env` values are not included in the backup.

The real drill restored `snowball-20260922-010401.dump` (2,949,289 bytes;
SHA-256 `7f2c9fb3c789531955f3ab3c954ca025fb1fda822961d6a320af08d6e5d95230`)
to `snowball_restore_verify_20260922_0104`. It matched 29 public tables, 172
indexes, 406 constraints, migration `20260920_0024`, all critical row counts,
zero checked integrity violations, zero checked identity collisions, Product
Views, a 70-item Inbox, and HEALTHY / FRESH status. A subsequent
`SCHEDULED` continuation succeeded with zero new business artifacts and zero
LLM calls, proving restart/restore idempotency. The live runtime was then
started canonically and completed a live `SCHEDULED` SUCCESS with HEALTHY /
FRESH status.

This is durable local backup/restore, not encrypted off-host backup,
centralized secret management, or a Production Ready deployment. See
`docs/RECOVERY_RUNBOOK.md` for operator procedure and boundaries.
