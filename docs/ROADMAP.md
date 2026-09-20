# Project Roadmap

## Completed

### Phase 0 — Foundation ✅

Project bootstrap and the initial source-independent persistence/application
boundaries are complete.

### Phase 1 — Data / Intelligence Foundation ✅

RawEvent, real Analysis, deterministic resolution, Opinion, Investor × Asset
state, Attention, Thesis, and the evidence-backed derivation foundations are
complete.

### Phase 2 — Intelligence Product Foundation ✅ / FROZEN

Cross-Investor evidence, Signal, IntelligenceEvent, Priority, Feed, Product
Views, frontend, and Asset ↔ Investor navigation are implemented. Further
semantic expansion is frozen during Phase 3 except for proven correctness
bugs.

### Phase 0

- Sprint 0.5 — Project Bootstrap ✅

### Sprint 1

- 1A — Raw Event Pipeline ✅
- 1B — Opinion Processing ✅
- 1C — Investor Asset State ✅
- 1D — Asset Intelligence Aggregation ✅
- 1E — Core Intelligence Orchestrator ✅
- 1F — Temporal & Processing Hardening ✅

### Sprint 2A

- Xueqiu Collector Foundation ✅

### Sprint 2B

- Real LLM Opinion Extraction ✅
- 2B.1 — Generic OpenAI-Compatible Provider ✅

### Sprint 2C

- 2C.1 — Following Feed Contracts & Architecture ✅
- 2C.2 — Following Feed Browser Runtime ✅
- 2C.3-A — Following Feed Ingestion Wiring ✅
- 2C.3-B — Following Feed Production Wiring ✅
- 2C.4 — Following Feed Historical Pagination Reliability Hardening ✅

### Sprint 2D

- Asset Resolution Contracts & Design ✅
- Deterministic Asset Resolver ✅
- AssetAlias ✅
- Evidence-backed Asset Master ✅
- Unresolved Asset Recovery ✅
- Analysis-scoped Opinion Correctness ✅
- Cross-listing / alias safety hardening ✅

### Sprint 2E.0

- Behavior Evidence Foundation ✅
- AttentionOccurrence ✅
- `OPINION` / `EXPLICIT_MENTION` / `REPOST` evidence attribution ✅
- Effective-analysis semantics ✅
- Current-author attribution hardening ✅

### Sprint 2E.2-A

#### Opinion Attribution & Identity Hardening ✅

- `opinion-extraction-v5` ✅
- Current-author-only Opinion extraction ✅
- Quote/repost attribution isolation ✅
- Cross-listing identity hardening ✅

### Sprint 2E.2-B

#### Production Analysis Policy & Projection Provenance ✅

- Explicit production `AnalysisSpec` ✅
- Provider runtime default != production approval ✅
- Effective State / StateChange / Attention queries ✅
- v4/v5 policy isolation ✅
- v5 production rollout ✅

### Sprint 2E.2

#### Thesis Change V0 ✅

- Effective v5 Opinion timeline ✅
- Independent structured Thesis Comparator ✅
- Versioned ThesisChange artifact ✅
- Fact-time and late-recovery semantics ✅
- `NEW_THESIS` / `THESIS_UNCHANGED` / `THESIS_REINFORCED` / `THESIS_EXTENDED` /
  `THESIS_CHANGED` / `INSUFFICIENT_EVIDENCE` ✅

`NEW_THESIS` means the first thesis observed in the currently available
production-effective Opinion history for an Investor × Asset; it does not claim
to be the investor's first-ever formation of that thesis. Superseded late-history
predecessor pairings remain historical artifacts and are excluded from the
effective Thesis Change timeline.

### Sprint 2E.3-A — Portfolio Fact Foundation Bootstrap ✅

- Independent Portfolio and PositionSnapshot facts ✅
- Derived PortfolioAction contract and persistence ✅
- InvestorActionClaim with RawEvent provenance ✅
- Resolved / unresolved asset identity support ✅
- No Portfolio Collector or production action detection yet ✅

### Sprint 2E.3-B — Portfolio Snapshot Import Foundation ✅

- External snapshot import contract ✅
- Deterministic AssetResolver integration ✅
- Resolved and unresolved PositionSnapshot persistence ✅
- Repeat-import idempotency ✅
- No Portfolio Collector, Action Diff, or Consistency Engine yet ✅

### Sprint 2E.3-C — Portfolio Snapshot Provenance Layer ✅

- PortfolioSnapshotBatch parent fact ✅
- PositionSnapshot batch ownership ✅
- Batch-aware repository and UnitOfWork ✅
- Deterministic batch / position idempotency ✅
- No PortfolioAction diff generation yet ✅

### Sprint 2E.3-D — Portfolio Position Change Detection V0 ✅

- Deterministic two-batch position comparison ✅
- `POSITION_ADDED` / `POSITION_REMOVED` ✅
- `POSITION_INCREASED` / `POSITION_DECREASED` / `POSITION_UNCHANGED` ✅
- Complete batch and position provenance ✅
- Resolved / unresolved identity isolation ✅
- No BUY/SELL intent inference ✅

### Sprint 2E.3-E — Opinion × Action Consistency V0 ✅

- Independent consistency domain ✅
- Active Opinion and PortfolioAction fact-time matching ✅
- Positive / negative alignment and no-direction semantics ✅
- Versioned, provenance-complete consistency artifact ✅
- Idempotent persistence ✅
- No skill, profitability, ranking, or investment recommendation ✅

### Sprint 2E.3-F — Investor Behavior Snapshot Foundation ✅

- Window-scoped InvestorBehaviorSnapshot aggregation ✅
- Active artifact and fact-time filtering ✅
- Attention, Opinion, ThesisChange, PortfolioAction, and Consistency metrics ✅
- Deterministic snapshot identity and idempotent persistence ✅
- No scoring, ranking, prediction, Signal, or Dashboard ✅

### Sprint 2E.3-G — Effective Derived Artifact & Snapshot Provenance Hardening ✅

- Effective adjacent PortfolioAction timeline ✅
- Snapshot completeness and unknown weight semantics ✅
- Effective Opinion × PortfolioAction consistency selection ✅
- Input-fingerprinted immutable BehaviorSnapshot versions ✅
- Late-data and recovery isolation ✅

### Sprint 2E.3-H — Behavior Input Dependency & Policy Closure ✅

- Explicit production Attention policy ✅
- Attention policy isolation in effective queries ✅
- Historical first-attention dependency fingerprint ✅
- FULL / UNKNOWN absence-inference closure ✅
- 2E single-investor foundation correctness closure ✅

### Sprint 2F.0 — Data Reality Check / Intelligence Calibration ✅

- Read-only PostgreSQL coverage audit ✅
- Effective Attention / Opinion / Thesis / Portfolio inventory ✅
- Cross-Investor overlap and sample-bias calibration ✅
- One bounded browser-native Following Feed backfill (no LLM analysis) ✅
- No new business models, tables, scores, or Signals ✅

The current calibration dataset has 42 Investors, 188 RawEvents, and 7.98
days of observed fact time. It has overlap across five Assets (two Investors
each), but no three-Investor overlap and no Portfolio facts. Sprint 2F.0.1
closed active Analysis coverage at 188/188 and added only two evidence-backed
Assets through deterministic recovery. The audit supports 2F design
discussion only; Momentum still requires natural multi-week data.

### Sprint 2F.1 — Cross-Investor Asset Evidence Snapshot Foundation ✅

- Asset-centric fact-time snapshot ✅
- Effective Attention / Opinion / Thesis / Portfolio / Consistency aggregation ✅
- Per-Investor contribution provenance ✅
- Deterministic SHA-256 input identity and immutable versions ✅
- No Consensus score, Divergence, Momentum, Ranking, Signal, or LLM ✅

### Sprint 2F.1.2 — Cross-Investor Contribution Provenance Closure ✅

- Complete window Opinion IDs and counts per Investor contribution ✅
- `cross-investor-asset-snapshot-v2` with v1 preservation ✅
- Aggregate-count reconstruction and repeated-input idempotency validation ✅

### Sprint 2F.2 — Opinion Coverage & Directional Alignment V0 ✅

- Immutable `CrossInvestorAssetAlignment` derived from one source snapshot ✅
- Deterministic `NONE` / `PARTIAL` / `COMPLETE` Opinion Coverage ✅
- Deterministic latest-per-Investor Directional Alignment ✅
- Attention/Opinion Investor-set integrity validation ✅
- SHA-256 source-snapshot + policy identity and append-only idempotency ✅
- No Consensus, Divergence Score, weighting, Momentum, Signal, or LLM ✅

Directional Alignment != Consensus. Alignment `MIXED_DIRECTION` is a broad
multi-side state; Consensus v2 `DIVERGENT` requires direct
bullish/bearish conflict, while a directional side plus Neutral is
`MIXED_WITH_NEUTRAL`. Consensus Change Over Time still waits for repeated
eligible windows and longer time series.

### Sprint 2F.2.5 — Production Analysis Recovery & Intelligence Recalibration ✅

- Active FAILED Analysis recovery with bounded batches/concurrency ✅
- DeepSeek/OpenAI-compatible adapter timeout, retry, exponential backoff, and
  strict structured-output validation hardening ✅
- Existing Opinion, Attention, ThesisChange, CrossInvestorAssetSnapshot, and
  CrossInvestorAssetAlignment rebuild orchestration ✅
- Data Reality Audit v2 coverage/overlap/asset/portfolio reporting ✅
- No production identity, Opinion contract, RawEvent, historical Snapshot, or
  new Intelligence feature changes ✅

### Sprint 2F.2.6 — Full Production Analysis Backfill & Recalibration ✅

- Dynamically selected and processed all missing active Analysis rows ✅
- Preserved valid analyses and real FAILED semantics with bounded resume-safe
  batches ✅
- Rebuilt existing Asset, Opinion, Attention, ThesisChange, Snapshot v2, and
  Alignment v1 artifacts ✅
- Added Data Reality Audit v3 calibration metrics ✅
- No Consensus, Momentum, Warming, Score, Ranking, or Signal implementation ✅

### Sprint 2F.2.7 — Asset Resolution Reality Calibration & Safe Coverage Expansion ✅

- Deterministic unresolved taxonomy and multi-factor prioritization ✅
- 17 evidence-backed Assets and 17 market-scoped symbol Aliases ✅
- Deterministic Opinion/Attention/Thesis/CrossInvestor recovery without Opinion
  LLM reprocessing ✅
- Real 3+ Investor overlap and MIXED_DIRECTION calibration surfaced ✅
- No Consensus, Momentum, Warming, Score, Ranking, or Signal implementation ✅

### Sprint 2F.3 — Cross-Investor Consensus / Divergence Evidence V0 ✅

- Immutable evidence artifact sourced from Snapshot v2 and Alignment v1 ✅
- Three Opinion-Investor eligibility boundary ✅
- Latest Opinion direction per Investor, with no Opinion-count voting ✅
- Provenance, membership, aggregate-count, idempotency, and policy-version
  validation ✅
- Real calibration processed 14 current overlap Snapshots as
  INSUFFICIENT_EVIDENCE; no eligible production Consensus/Divergence case yet ✅
- No score, weighting, ranking, Momentum, Warming, Signal, or Research
  Candidate implementation ✅

### Sprint 2F.3.2 — Consensus Evidence Semantic Hardening ✅

- Added active policy `cross-investor-consensus-evidence-v2` ✅
- Preserved all v1 immutable artifacts and v1 classification semantics ✅
- Reserved `DIVERGENT` for direct bullish/bearish conflict ✅
- Added `MIXED_WITH_NEUTRAL` for bullish/neutral or bearish/neutral mixes ✅
- Kept latest-per-Investor direction and strong-direction mapping unchanged ✅
- Real calibration reclassified 招商轮船 from v1 `DIVERGENT` to v2
  `MIXED_WITH_NEUTRAL` ✅
- No LLM, score, weighting, ranking, Momentum, Signal, or Research Candidate
  implementation ✅

## Current phase — Phase 3 — Operational MVP

Phase 0 Foundation, Phase 1 Data / Intelligence Foundation, and Phase 2
Intelligence Product Foundation are completed or frozen. The UI exists, but
the product is not yet operationally self-running. The critical gap is the
operational loop, not additional Intelligence semantics.

### OMVP-1 — One-Command End-to-End Incremental Refresh

Current sprint. One canonical command must coordinate the existing path from
Following Feed collection through Product View verification, select work from
actual database state, expose stage failures, and be safe to rerun. No new
semantic layer, scheduler, or orchestration table is in scope.

Status: `COMPLETE`. An explicit authenticated Edge CDP smoke returned 16
real Following Feed items. The canonical command created 16 RawEvents,
processed them under the unchanged production Analysis identity, completed
all downstream stages, verified four affected Investor Product Views, and
passed an identical rerun with zero new RawEvents and zero LLM calls.

The verified runtime command is:

```powershell
python -m operations.refresh --cdp-endpoint http://127.0.0.1:9222
```

### OMVP-2 — Scheduled Refresh + Freshness + Failure Visibility

Status: `COMPLETE`.

The lightweight scheduled trigger calls the same canonical refresh service,
persists full-refresh execution metadata, exposes freshness/failure status at
`GET /api/operations/status`, and shows user-facing operational state in
the frontend shell. The verified scheduled runtime uses an authenticated Edge
CDP endpoint and configuration-driven interval/stale thresholds.

No second pipeline, heavy orchestration framework, or Intelligence semantic
was introduced.

### OMVP-3 — Daily Intelligence Inbox

Status: `COMPLETE`.

The Overview product entry now shows Recent Intelligence using the existing
FeedItem, Priority, Event, Signal, and evidence lineage. It uses a rolling
24-hour query-time window, does not create user read state, and preserves the
distinction between successful data refresh and no surfaced Intelligence.
No new semantic layer or persistence artifact was introduced.

## Post-MVP Productionization

Deferred until Operational MVP is complete:

- always-on deployment, CI/CD, restart recovery, metrics, alerts, backups,
  production secrets, and runbooks;
- deeper historical completeness, real portfolio acquisition, and a second
  source;
- RAG and advanced research workflows.

## Deferred / Frozen

The following are explicitly deferred or frozen during Phase 3:

- new semantic layers, ranking, scoring, recommendation, and advanced
  Pattern;
- Context V2, Narrative V2, and advanced Consensus;
- Momentum based on incomplete history;
- Portfolio analytics without real portfolio data;
- RAG and second-source expansion.

Attention Momentum remains `PAUSED / DATA CALIBRATION / WAITING FOR TEMPORAL
COVERAGE`; this is preserved as a data-readiness fact, not a reason to expand
the semantic layer now.

## Product boundary

This project is an Investor Behavior Intelligence System, not a Xueqiu crawler product, stock recommendation
system, auto-trading system, or price prediction system. The roadmap prioritizes discovering who is watching what,
why they are watching it, when their views change, whether they act, and whether multiple investors form consensus
or divergence.

## Phase 4 — Intelligence Yield Recovery

Phase 4 improves intelligence yield by increasing coverage of the already
monitored Xueqiu Investor cohort. It does not add a second source or change
the Intelligence semantic layer.

### IYR-1 — Monitored Investor Direct Collection ✅

The canonical Operational Refresh collection stage now runs:

    Following Feed
          +
    Monitored Investor Direct Recent Profiles
          ↓
    Existing FeedIngestion / Profile DataPipeline
          ↓
    One RawEvent hash boundary
          ↓
    Existing Analysis → Intelligence → Product path

The cohort is bounded at up to eight database-registered Xueqiu Investors,
selected from recent activity and existing effective evidence. The direct
profile path uses a 48-hour overlap, at most two pages, and a 30-second
per-Investor duration bound. It reuses the operator-authenticated CDP
context/page and records existing CollectionRun / CollectionObservation
provenance. Profile failure is isolated per Investor; authentication,
risk-control, and CDP failures stop the direct collection safely.

Real validation produced 52 Profile-only new RawEvents, with ORIGINAL and
REPOST observability, complete downstream processing, and successful Product
verification. No Asset Resolution semantic was changed.

### IYR-2 — Asset Resolution Yield Recovery

Deferred. No IYR-2 implementation is part of IYR-1.

### IYR-3 — Yield Re-validation

Deferred until IYR-2 decisions and additional direct-collection evidence exist.