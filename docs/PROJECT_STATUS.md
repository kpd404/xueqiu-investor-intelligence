# Project Status

Last verified from the repository: 2026-09-05

This document is a repository-derived handoff for a new Codex session. The
current files, migrations, tests, and PostgreSQL verification are authoritative;
old chat descriptions are not.

## Current phase and sprint

The project is in Phase 2, Cross-Investor Intelligence.

- Latest completed sprint: **Sprint 2F.1 — Cross-Investor Asset Evidence Snapshot Foundation**.
- Current checkpoint: 2F.1 is implemented and verified; 2F.2 has not started.
- Attention Momentum (2E.1) remains paused for temporal data calibration.
- No Signal, ranking, recommendation, or portfolio-performance engine is implemented.

The next candidate is a narrowly scoped Consensus/Divergence evidence design,
not a score or trading recommendation.

## Completed functionality

### Phase 0 and Sprint 1

- Phase 0 / Sprint 0.5 project bootstrap.
- Sprint 1A RawEvent persistence and ingestion pipeline.
- Sprint 1B structured Opinion processing.
- Sprint 1C InvestorAssetState projection and state changes.
- Sprint 1D basic Asset Intelligence / Consensus aggregation foundation.
- Sprint 1E core intelligence orchestration.
- Sprint 1F temporal, processing, provenance, idempotency, and transaction-boundary hardening.

### Sprint 2A–2C: Xueqiu Following Feed

- Authenticated homepage Following Feed collector using Playwright and the exact
  Following UI context.
- The formal endpoint is the browser-observed
  `/v4/statuses/home_timeline.json`; only `home_timeline` is parsed.
- `FeedPostItem` preserves source-event identity and ORIGINAL/REPOST/COLUMN/
  UNKNOWN post kind.
- Feed ingestion creates or reuses Investor and persists immutable RawEvent facts.
- Browser-native, response-driven pagination with bounded `NO_PROGRESS` handling.
- Item-level parser isolation: one invalid item does not discard valid items in
  the same batch.
- No legacy profile collector is part of the production Following Feed path.

### Sprint 2B: real Opinion extraction

- Provider-neutral `OpinionExtractor` port.
- `OpenAICompatibleOpinionExtractor` using Responses API and JSON Schema
  Structured Output.
- `OpinionExtractionResult` is validated by the shared Pydantic contract.
- Prompt versions are stored under `prompts/opinion_extraction/`.
- Current production extraction identity is `opinion-extraction-v5` /
  `opinion-analysis-v3`.
- Current-author attribution boundary excludes quoted and nested repost text from
  the current author's Opinion.
- Provider errors are mapped to neutral retryable/non-retryable semantics.
- Provider usage/provenance is stored in `EventAnalysis.provider_metadata`.

### Sprint 2D: deterministic Asset Resolution

- `AssetReference` and `AssetResolutionResult` contracts.
- Deterministic market and symbol normalization.
- Canonical Asset and market-scoped/global AssetAlias lookup.
- `RESOLVED`, `UNRESOLVED`, `AMBIGUOUS`, and `INVALID` semantics.
- Cross-listing safety and canonical-name scope closure.
- Unresolved asset recovery reuses saved extraction semantics and does not call
  the LLM again.
- Evidence-backed minimal Asset Master seeding is idempotent.

### Sprint 2E: single-investor intelligence foundation

- `AttentionOccurrence` with `OPINION`, `EXPLICIT_MENTION`, and `REPOST`
  evidence types.
- Explicit production Attention policy and effective Attention queries.
- Current-author/repost attribution hardening.
- Effective Analysis policy and no-fallback behavior for inactive/failed analyses.
- Versioned ThesisChange V0 with fact-time predecessor pairing and structured
  comparator contract.
- Independent Portfolio Fact Foundation:
  `Portfolio`, `PortfolioSnapshotBatch`, `PositionSnapshot`, `PortfolioAction`,
  and `InvestorActionClaim`.
- Deterministic position-change detection with `POSITION_CHANGE_UNKNOWN`; no
  BUY/SELL inference.
- Opinion × PortfolioAction Consistency V0 with effective matching.
- Immutable, fingerprinted `InvestorBehaviorSnapshot` versions.
- Late-data/recovery reconciliation and effective derived-artifact selection.
- Fact-time semantics consistently use `RawEvent.published_time` or artifact
  `effective_time`; `generated_time` and `calculated_at` are not behavior time.

### Sprint 2F.0–2F.1: cross-investor evidence

- Read-only intelligence data calibration audit at
  `scripts/audit_intelligence_data.py`.
- Active Analysis backfill and evidence-backed minimal Asset expansion have been
  performed against the real development PostgreSQL database.
- `CrossInvestorAssetSnapshot` is an asset-centric, fact-time window aggregate
  over effective Attention, Opinion, ThesisChange, PortfolioAction, and
  Consistency artifacts.
- Per-Investor contribution provenance is retained in structured JSON, including
  source IDs, first Attention identity/time, latest window Opinion, and related
  derived artifact IDs/types.
- Snapshot input identity is a deterministic SHA-256 fingerprint containing
  policy versions, effective upstream IDs, and relevant first-Attention history.
- Identical inputs reuse an immutable snapshot; late facts or policy changes
  create a new version.
- No Consensus direction/score, Divergence, Momentum, Ranking, Signal, or LLM
  logic is part of 2F.1.

## Current architecture and responsibilities

The high-level dependency flow is:

```text
Source adapters / Xueqiu Following Feed
              ↓
           RawEvent
              ↓
       EventAnalysis (AI interpretation)
              ↓
            Opinion
              ↓
 InvestorAssetState / StateChange
              ↓
 Single-investor and cross-investor derived evidence
```

The independent Portfolio fact stream is:

```text
Portfolio source/import
        ↓
PortfolioSnapshotBatch
        ↓
PositionSnapshot
        ↓
PortfolioAction
```

The current modules are responsible for the following:

- `collectors/`: source-specific browser and feed adapters. They do not import
  database or intelligence policy code.
- `ingestion/`: application wiring from normalized feed items to Investor and
  RawEvent persistence.
- `contracts/`: provider/source-neutral Pydantic contracts and policy identities.
- `ai/`: extractor and comparator adapters. Provider SDK dependencies are kept
  here; the core pipeline does not know OpenAI wire formats or API keys.
- `resolution/`: deterministic AssetResolver and Asset recovery service. It
  never calls an LLM or creates Asset master data automatically.
- `pipeline/`: application orchestration, including core processing and recovery
  reconciliation. External waits are outside database transactions.
- `intelligence/policies/`: pure deterministic reducers/matchers/aggregation
  policies.
- `intelligence/services/`: StateUpdate, AttentionOccurrence, ThesisChange,
  AssetIntelligence, and CrossInvestorAssetSnapshot services.
- `behavior/`: InvestorBehaviorSnapshot aggregation boundary.
- `consistency/`: Opinion versus PortfolioAction analysis boundary.
- `portfolio/`: Portfolio snapshot import and position-change detection boundary.
- `database/models/`, `database/repositories/`, and `database/unit_of_work.py`:
  persistence adapters and transaction scopes.
- `signal_engine/`: storage/evidence foundation only; there is no production
  Signal scoring engine.

Normal downstream interpretation consumes the explicitly active Opinion
AnalysisSpec and effective artifact selectors. Database presence alone does not
make an Analysis effective, and missing/failed active Analysis never falls back
to an older version.

## Important implementation and design decisions

1. **Facts are immutable; interpretations and derived artifacts are versioned.**
   RawEvent is preserved. Opinion, StateChange, AttentionOccurrence,
   ThesisChange, PortfolioAction, Consistency, and snapshots carry provenance
   and can be recomputed or superseded without deleting history.

2. **Provider and model identity are separate.** `AnalysisSpec.analysis_version`
   is deterministic over provider, model, prompt, schema, and analysis policy;
   secrets, timestamps, response IDs, timeout, and retry settings are excluded.

3. **Structured LLM output is mandatory.** The generic adapter sends a standard
   Responses JSON Schema request and validates the returned object with Pydantic;
   free-text JSON fallback and regular-expression extraction are not supported.

4. **Attribution is conservative.** Opinion extraction sees a
   `CurrentAuthorEventView`. Quoted/nested repost text can support REPOST
   Attention, but cannot supply the current author's asset, direction, or thesis.

5. **Asset resolution is deterministic-first.** Market+symbol is strongest;
   aliases are normalized and market-scoped. The system does not infer a market
   from code length, use world knowledge, or auto-create securities.

6. **Effective selection is explicit and fact-time based.** Effective timelines
   select the active policy/version and deterministic predecessor/transition.
   `published_time`/`effective_time` represent behavior; `generated_time` is AI
   interpretation time; `calculated_at` is derived calculation time.

7. **Attention is evidence, not Opinion.** One Investor × Asset × RawEvent is
   one AttentionOccurrence even when multiple evidence types are present.

8. **Portfolio facts remain independent.** Snapshot differences prove position
   changes, not BUY/SELL intent. Missing weights and incomplete absence evidence
   remain neutral/unknown.

9. **CrossInvestorAssetSnapshot is aggregation only.** It preserves which
   Investors contributed evidence and the active policy provenance. It does not
   assign consensus, divergence, quality, momentum, or investment scores.

10. **No quality weighting is used.** `Investor.quality_score` is not an input to
    the CrossInvestor snapshot.

## Database, schema, and migrations

The latest migration chain is:

| Revision | Purpose |
| --- | --- |
| `20260821_0001` | Initial schema |
| `20260824_0002` | Opinion idempotency |
| `20260826_0003` | Temporal processing hardening |
| `20260827_0004` | EventAnalysis provider metadata |
| `20260831_0005` | AssetAlias |
| `20260831_0006` | AttentionOccurrence |
| `20260903_0007` | ThesisChange |
| `20260903_0008` | Portfolio foundation |
| `20260903_0009` | Snapshot import idempotency |
| `20260903_0010` | Portfolio snapshot provenance |
| `20260904_0011` | PortfolioAction provenance |
| `20260904_0012` | Opinion × Action Consistency |
| `20260904_0013` | InvestorBehaviorSnapshot |
| `20260904_0014` | Effective artifact/snapshot provenance hardening |
| `20260904_0015` | Explicit Attention policy provenance |
| `20260904_0016` | CrossInvestorAssetSnapshot |

Real PostgreSQL verification currently reports:

- Alembic revision: `20260904_0016 (head)`.
- `alembic check`: no new upgrade operations.
- Table `cross_investor_asset_snapshots` exists.
- One real smoke snapshot row exists for an observed shared Asset.

No further schema change is required for the unimplemented 2F.2 design.

## Current real PostgreSQL data snapshot

The latest read-only audit of the development `snowball` database reports:

| Entity/metric | Count or value |
| --- | ---: |
| Investors | 42 |
| RawEvents | 188 |
| EventAnalyses | 364 |
| Active Opinion Analysis rows | 188 / 188 |
| Effective Opinions | 14 |
| Effective AttentionOccurrences | 22 |
| Effective ThesisChange | 14 |
| Canonical Assets | 14 |
| AssetAlias rows | 28 |
| Portfolio rows | 0 |
| PortfolioSnapshotBatch rows | 0 |
| PositionSnapshot rows | 0 |
| PortfolioAction rows | 0 |
| InvestorActionConsistency rows | 0 |
| CrossInvestorAssetSnapshot rows | 1 |

The observed RawEvent range is 2026-08-27 through 2026-09-04, approximately
7.98 days. Active Analysis statuses are:

- `NO_OPINION`: 137
- `PARTIALLY_RESOLVED`: 41
- `SUCCESS`: 7
- `FAILED`: 3

The database has five Assets observed across two Investors, but no Asset with
three or more Investors. Asset resolution still has 60 unresolved entries over
50 names. Sample-bias fields are not sufficiently populated to infer investor
style or industry concentration.

## Tests and verification

The current repository verification is:

- `pytest`: **375 passed**, with two non-failing environment warnings (FastAPI
  test-client deprecation and `.pytest_cache` permission).
- `ruff format --check .`: passed; 237 files formatted.
- `ruff check .`: passed.
- Alembic current/check against real PostgreSQL: `20260904_0016 (head)`, no drift.
- New CrossInvestor coverage is in
  `tests/integration/test_cross_investor_asset_snapshot.py`; model metadata
  coverage is updated in `tests/test_models.py`.

The pytest suite is offline and does not call real LLM providers or Xueqiu.
Real provider/collector validation has been performed manually through the
existing production entry points, outside pytest.

## Unfinished work

- Attention Momentum (`NEW`, `RISING`, `STABLE`, `COOLING`, `DORMANT`) remains
  paused; no thresholds or score are implemented.
- Cross-investor Consensus/Divergence, multi-investor warming, Industry Trend,
  and Theme Trend are not implemented.
- The current CrossInvestor snapshot is an evidence foundation only; it does not
  choose a consensus direction or rank Investors/Assets.
- Portfolio Collector, real Portfolio snapshot ingestion, and broader Portfolio
  Intelligence are not implemented; the current database has no Portfolio facts.
- Opinion × Action expansion, performance analysis, Research Signal/Candidate,
  Scheduler, Dashboard, and Product API remain planned.
- No unresolved-asset recovery automation or large securities master exists.
- No additional LLM prompt or model routing work is part of the current state.

## Known issues and technical debt

1. **Temporal sparsity:** Following Feed history currently covers only about
   eight days and has date gaps. This is insufficient for robust multi-week
   Momentum calibration.
2. **Asset coverage:** 60 unresolved entries remain. Name-only, partial-symbol,
   cross-listing, concept, and extraction-error cases must not be guessed.
3. **Portfolio absence:** Zero Portfolio rows means Portfolio evidence cannot
   yet validate Opinion × Action behavior at real-data scale.
4. **Sparse overlap:** Five Assets have two-Investor overlap; none have 3+
   Investors, limiting production-level Consensus/Divergence validation.
5. **Failed analyses:** Three active Analysis rows are explicitly FAILED. The
   system correctly does not fall back, but scheduler/retry orchestration is not
   implemented.
6. **Manual operational checks:** Real PostgreSQL and browser/provider smoke
   checks are command-line/manual workflows; they are not part of pytest.
7. **Environment-specific database tooling:** This Windows development setup
   requires the established temporary psycopg client-cursor compatibility shim
   when invoking Alembic; no source migration drift was found.
8. **Working-tree hygiene:** The current branch contains uncommitted sprint
   changes, including the audit script and CrossInvestor implementation. A new
   session must preserve them and must not reset, stash, or discard them.

## Current blockers

There is no unresolved code or migration blocker for the implemented foundation.
The practical blockers are data readiness:

- Xueqiu browser-native pagination stops around the current history window;
  deeper historical coverage cannot be assumed or forced.
- Asset Master coverage limits the number of resolved Opinions and Attention
  facts.
- No real Portfolio snapshot stream exists.
- No 3+ Investor overlap exists yet.

These are data/product-readiness limits, not reasons to add fallback inference,
scores, or provider-specific logic.

## Recommended next task

The next implementation candidate is **Sprint 2F.2 — Consensus/Divergence
Evidence V0**, with a deliberately small scope:

1. Freeze the current CrossInvestorAssetSnapshot contribution/effective-input
   contract as the only input.
2. Define deterministic, explainable evidence views for shared Assets without
   consensus scores, quality weighting, or recommendations.
3. Preserve per-Investor direction, Attention, Thesis, and provenance evidence;
   do not collapse disagreements into a winner.
4. Keep Momentum paused until natural 14d/28d data exists, and treat Portfolio
   as optional auxiliary evidence until real snapshots arrive.

Before that task, a new session should read `AGENTS.md`, this file, the current
contracts/services/repositories, and run `git status`, `pytest`, Ruff, and
Alembic checks. Do not start 2F.3, Signal, Scheduler, Dashboard, or Portfolio
Collector work unless explicitly requested.
