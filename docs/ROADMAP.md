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
- Sprint 2B.1 — Generic OpenAI-Compatible Provider ✅
- Sprint 2C.1 — Following Feed Contracts & Architecture ✅
- Sprint 2C.2 — Following Feed Browser Runtime ✅
- Sprint 2C.3-A — Following Feed Ingestion Wiring ✅
- Sprint 2C.3-B — Following Feed Real Smoke & Production Wiring ✅

## Current

Sprint 2C is complete through the verified production wiring boundary:

```text
Manual Login
→ Xueqiu Homepage Following Feed
→ home_timeline
→ FeedPostItem
→ FeedIngestionService
→ Investor + RawEvent
```

The current runtime includes bounded batch capture, no-progress stopping, dry-run
isolation, Investor identity reuse, RawEvent idempotency, and no Xueqiu
verification bypass. Asset Resolution, LLM Analysis, Signal, Scheduler,
Dashboard, Portfolio, alerts, RAG, and Agent workflows remain outside this
completed boundary.

## Planned

- Sprint 2C — Deterministic Signal MVP
- Sprint 2D — Scheduler MVP
- Phase 3 — Signal Engine expansion
- Phase 4 — Productization

Future work remains subject to the product boundary in `AGENTS.md`; Signal output is research priority, not Buy/Sell advice.
