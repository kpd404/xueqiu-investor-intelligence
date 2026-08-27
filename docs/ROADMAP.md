# Project Roadmap

## Completed

- Phase 0 / Sprint 0.5 — Project Bootstrap ✅
- Sprint 1A — Raw Event Pipeline ✅
- Sprint 1B — Opinion Processing ✅
- Sprint 1C — Investor Asset State ✅
- Sprint 1D — Asset Intelligence Aggregation ✅
- Sprint 1E — Core Intelligence Orchestrator ✅
- Sprint 1F — Temporal & Processing Hardening ✅
- Sprint 2A Foundation — Offline architecture and collector foundation ✅
- Sprint 2B — Real LLM Opinion Extraction ✅
- Sprint 2B.1 — Generic OpenAI-Compatible Provider ← current

## Current

Scope:

- Provider ID/model separation
- OpenAI-compatible Responses API configuration
- JSON Schema Structured Output portability
- Provider capability validation
- Deterministic provider-aware AnalysisSpec identity
- Generic offline smoke and compatibility tests

Sprint 2B.1 does not include Signal Engine, Scheduler, Dashboard, Portfolio, alerts, RAG, Agent,
multi-model routing, fallback models, or Xueqiu verification bypass.

## Planned

- Sprint 2C — Deterministic Signal MVP
- Sprint 2D — Scheduler MVP
- Phase 3 — Signal Engine expansion
- Phase 4 — Productization

Future work remains subject to the product boundary in `AGENTS.md`; Signal output is research priority, not Buy/Sell advice.
