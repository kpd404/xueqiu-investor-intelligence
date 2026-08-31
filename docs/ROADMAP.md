# Project Roadmap

## Completed

- Phase 0 / Sprint 0.5 — Project Bootstrap ✅
- Sprint 1A — Raw Event Pipeline ✅
- Sprint 1B — Opinion Processing ✅
- Sprint 1C — Investor Asset State ✅
- Sprint 1D — Asset Intelligence Aggregation ✅
- Sprint 1E — Core Intelligence Orchestrator ✅
- Sprint 1F — Temporal & Processing Hardening ✅
- Sprint 2A — Xueqiu Collector Foundation ✅
- Sprint 2B — Real LLM Opinion Extraction ✅
- Sprint 2B.1 — Generic OpenAI-Compatible Provider ✅
- Sprint 2C.1 — Following Feed Contracts & Architecture ✅
- Sprint 2C.2 — Following Feed Browser Runtime ✅
- Sprint 2C.3-A — Following Feed Ingestion Wiring ✅
- Sprint 2C.3-B — Following Feed Real Smoke & Production Wiring ✅
- Sprint 2D.1 — Asset Resolution Contracts & Design ✅
- Sprint 2D.2 — Deterministic Asset Resolver MVP ✅
- Sprint 2D.3 — Minimal Asset Master Data & Real Resolution Validation ✅
- Sprint 2D.3.1 — Asset Mention Fidelity Hardening ✅
- Sprint 2D.4 — Unresolved Asset Recovery ✅
- Sprint 2D.4.1 — Analysis-scoped Opinion Correctness ✅

## Current

### Sprint 2E.1 — Attention Momentum MVP

Identify deterministic attention changes from Investor × Asset historical fact-time series:

- NEW attention
- RISING attention
- STABLE attention
- COOLING attention
- DORMANT attention

The guiding principle is: **change matters more than popularity**.

## Planned

### Sprint 2E — Investor Behavior Intelligence

#### 2E.1 Attention Momentum

- recency
- frequency
- acceleration
- decay

#### 2E.2 Thesis Change

- thesis added
- thesis removed
- thesis replaced
- thesis strengthened / weakened

#### 2E.3 Portfolio Fact Pipeline

- portfolio snapshot
- new position
- increase
- reduce
- exit

#### 2E.4 Opinion × Action Consistency

- opinion confirmation
- opinion/action divergence

### Sprint 2F — Cross-Investor Intelligence

- Consensus enhancement
- Divergence
- Multi-investor attention warming
- Industry Trend
- Theme Trend

### Sprint 2G — Research Signal / Candidate V0

Inputs:

- Attention Momentum
- Opinion Change
- Thesis Change
- Consensus / Divergence
- Position Confirmation

Outputs:

- Research Priority
- Research Candidate

These outputs are research prioritization, not Buy / Sell recommendations.

### Sprint 2H — Scheduler / Continuous Monitoring

Continuous collection, processing, and monitoring orchestration will be addressed here.

### Phase 3 — API / Dashboard / Productization

Product API, dashboard, reporting, and user-facing workflows follow the intelligence foundations.

## Product boundary

This project is an Investor Behavior Intelligence System, not a Xueqiu crawler product, stock recommendation
system, auto-trading system, or price prediction system. The roadmap prioritizes discovering who is watching what,
why they are watching it, when their views change, whether they act, and whether multiple investors form consensus
or divergence.
