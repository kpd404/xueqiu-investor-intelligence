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

## Current / Next

### Sprint 2E.2 — Thesis Change V0

Status: `DESIGN / NEXT`

The attribution prerequisite (2E.2-A) and production policy prerequisite (2E.2-B) are complete. Thesis Change
comparator and persistence are not implemented.

Current V0 design candidates:

- `NEW_THESIS`
- `THESIS_UNCHANGED`
- `THESIS_REINFORCED`
- `THESIS_EXTENDED`
- `THESIS_CHANGED`
- `INSUFFICIENT_EVIDENCE`

Missing catalysts, risks, or `time_horizon` are `UNKNOWN / NOT_EXTRACTED`; they must not be interpreted as removed,
weakened, or invalidated. `THESIS_WEAKENED`, `THESIS_INVALIDATED`, and thesis-removed semantics remain Future / Later
options.

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

Momentum data calibration and Thesis Change design can proceed in parallel; 2E.1 does not have to be completed before
2E.2 design work.

## Planned

### Sprint 2E.3 — Portfolio Fact Pipeline

- Portfolio snapshot
- New position
- Increase
- Reduce
- Exit

### Sprint 2E.4 — Opinion × Action Consistency

- Opinion confirmation
- Opinion/action divergence

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
