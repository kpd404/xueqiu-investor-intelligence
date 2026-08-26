# Project Roadmap

## Completed

- Phase 0 / Sprint 0.5 — Project Bootstrap ✅
- Sprint 1A — Raw Event Pipeline ✅
- Sprint 1B — Opinion Processing ✅
- Sprint 1C — Investor Asset State ✅
- Sprint 1D — Asset Intelligence Aggregation ✅
- Sprint 1E — Core Intelligence Orchestrator ✅
- Sprint 2A Foundation — Offline architecture and collector foundation ✅

## Current

- Sprint 1F — Temporal & Processing Hardening ← current

Scope:

- EventAnalysis lifecycle
- AnalysisSpec provenance
- StateChange append-only ledger
- Projection change versus material change
- Activity and material-change timestamps
- Historical `as_of` replay
- Pipeline outcome and retry semantics
- Short database transactions around external collection
- Migration and architecture guard verification

Sprint 1F does not include Real LLM, Signal Engine, Scheduler, Dashboard, Portfolio, alerts, RAG, or Xueqiu verification bypass.

## Planned

- Sprint 2A — Production Opinion Extraction (live work starts after 1F)
- Sprint 2B — Deterministic Signal MVP
- Sprint 2C — Scheduler MVP
- Phase 3 — Signal Engine expansion
- Phase 4 — Productization

Future work remains subject to the product boundary in `AGENTS.md`; Signal output is research priority, not Buy/Sell advice.
