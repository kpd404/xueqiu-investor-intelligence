# Project Roadmap

## Completed

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

## Current / Next

### Sprint 2E.1 — Attention Momentum

Status: `PAUSED / DATA CALIBRATION / WAITING FOR TEMPORAL COVERAGE`

The architecture and Behavior Evidence Foundation are in place, but real samples do not yet provide enough cross-day /
cross-week temporal coverage. The 14d/28d baseline is not finalized. This is an intentional data-calibration state,
not an architecture failure or a blocked implementation.

Product goals remain:

- recency
- frequency
- acceleration
- decay
- `NEW` / `RISING` / `STABLE` / `COOLING` / `DORMANT`

Momentum must distinguish `occurrence_count` / occurrence frequency, distinct active days, and recency. For example, `3 occurrences / 1
active day` is not the same sustained attention intensity as `3 occurrences / 3 active days`. No concrete 7d/14d/28d
thresholds are defined yet.

Thesis Change V0 is available, but useful coverage remains limited by the current number of repeated effective Opinion
pairs.

Sprint 2E.3-H closes the single-investor Behavior Intelligence foundation.
The next engineering phase is Sprint 2F Cross-Investor Intelligence.

## Planned

### Remaining Sprint 2E.3 scope — Portfolio production orchestration

The Portfolio Fact Foundation bootstrap is complete in Sprint 2E.3-A. The
Snapshot Import Foundation is complete in Sprint 2E.3-B, Snapshot Provenance
is complete in Sprint 2E.3-C, and Position Change Detection V0 is complete in
Sprint 2E.3-D. The remaining scope
is intentionally not implemented yet:

- Portfolio Collector
- Production portfolio ingestion orchestration

### Sprint 2E.4 — Portfolio Intelligence / Performance Analysis

- Portfolio intelligence extensions
- Performance analysis (future)
- Position / opinion longitudinal analysis

### Sprint 2F — Cross-Investor Intelligence

- Enhanced Consensus / Divergence
- Multi-investor attention warming
- Industry Trend
- Theme Trend

### Sprint 2G — Research Signal / Candidate V0

- Research Priority
- Research Candidate

Inputs include Attention Momentum, Opinion Change, Thesis Change, Consensus / Divergence, and Position Confirmation.
These outputs are research prioritization, not Buy / Sell recommendations.

### Sprint 2H — Scheduler / Continuous Monitoring

Continuous collection, processing, and monitoring orchestration will be addressed here.

### Phase 3 — Productization

Product API, dashboard, reporting, and user-facing workflows follow the intelligence foundations.

## Product boundary

This project is an Investor Behavior Intelligence System, not a Xueqiu crawler product, stock recommendation
system, auto-trading system, or price prediction system. The roadmap prioritizes discovering who is watching what,
why they are watching it, when their views change, whether they act, and whether multiple investors form consensus
or divergence.
