# Project Status

Last verified from the repository: 2026-09-10

This document is a repository-derived handoff for a new Codex session. The
current files, migrations, tests, and PostgreSQL verification are authoritative;
old chat descriptions are not.

## Current phase and sprint

The project is in Phase 2, Cross-Investor Intelligence.

- Latest completed sprint: **Sprint 2F.3.2 — Consensus Evidence Semantic Hardening**.
- Current checkpoint: 2F.3.2 is implemented and verified; v2 calibration is data-limited but now semantically separates Neutral mixes from direct divergence.
- Attention Momentum (2E.1) remains paused for temporal data calibration.
- No Signal, ranking, recommendation, or portfolio-performance engine is implemented.

The next candidate is a narrowly scoped Consensus/Divergence evidence design,
not a score or trading recommendation. Directional Alignment != Consensus.

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
  the LLM again. Current resolution is projected from the immutable Analysis
  payload; only extracted `structured_output.opinions` entries can materialize
  Opinions, while direct unresolved hints remain non-materializable.
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

Sprint 2F.1.2 adds complete `window_opinion_ids` and
`window_opinion_count` to each contribution. The policy version is now
`cross-investor-asset-snapshot-v2`; v1 snapshot rows remain immutable for
audit and are not overwritten.

### Sprint 2F.2 — Opinion Coverage & Directional Alignment V0

- `CrossInvestorAssetAlignment` is an immutable artifact derived from one
  `CrossInvestorAssetSnapshot`.
- Opinion Coverage is `NONE`, `PARTIAL`, or `COMPLETE`, only for snapshots
  with at least two Attention Investors.
- Directional Alignment uses one latest Opinion direction per Investor and
  emits `INSUFFICIENT_EVIDENCE`, `ALIGNED_BULLISH`,
  `ALIGNED_BEARISH`, `ALIGNED_NEUTRAL`, or `MIXED_DIRECTION`.
- Opinion Investors outside the Attention Investor set fail explicitly.
- Policy `cross-investor-directional-alignment-v1` is fingerprinted with the
  source snapshot identity; identical inputs reuse and policy changes append.
- No Consensus, Divergence Score, weighting, Momentum, Signal, or LLM logic
  was introduced.

### Sprint 2F.2.5 — Production Analysis Recovery & Intelligence Recalibration

- The approved production Opinion identity remains
  opinion-analysis-v3:794dc66ba5096337c3e2c0f85554887352f476e5f52ad55363b6b9420d5502a9.
- The provider adapter owns one bounded retry policy with request timeout,
  exponential backoff, and strict structured-output validation. It accepts the
  existing DeepSeek Responses JSON Schema path without free-text fallback.
- The first recovery pass processes only active FAILED Analysis rows. Missing
  active Analysis rows remain explicitly unprocessed for a later, separately
  authorized backfill.
- Existing deterministic Opinion projection, Attention, ThesisChange,
  CrossInvestorAssetSnapshot, and CrossInvestorAssetAlignment services are
  orchestrated in that order after recovery. No new Intelligence semantics,
  score, ranking, Momentum, Signal, or migration was added.
- Data Reality Audit v2 is available at
  scripts/audit_intelligence_data.py.

### Sprint 2F.2.6 — Full Production Analysis Backfill & Recalibration

- Preflight selected the missing active Analysis set dynamically; it was 569
  RawEvents at run start.
- All 569 missing analyses completed successfully under the unchanged
  production identity. The run issued 617 Opinion-analysis calls, including
  48 bounded retries, and retained zero FAILED rows.
- Deterministic Asset recovery processed 249 active resolvable/partially
  resolved analyses and created one additional Opinion without guessing any
  Asset identity.
- Effective Opinion projection, Attention, ThesisChange, CrossInvestor
  Snapshot v2, and Alignment v1 were rebuilt. No new Intelligence semantic,
  score, ranking, Momentum, or Signal was introduced.
- Data Reality Audit v3 reports the complete active Analysis coverage and the
  remaining Asset/overlap/Portfolio limitations.

### Sprint 2F.2.7 — Asset Resolution Reality Calibration & Safe Coverage Expansion

- Added a deterministic unresolved-reference taxonomy and multi-factor
  prioritization audit at scripts/audit_asset_resolution.py.
- Added 17 evidence-backed Assets and 17 market-scoped symbol Aliases. No
  unsupported-market, fuzzy, name-only, or LLM-driven identity was added.
- Deterministic recovery created 53 new Opinions without calling the Opinion
  extractor; existing Attention, ThesisChange, CrossInvestor Snapshot v2, and
  Alignment v1 artifacts were rebuilt.
- Data Reality Audit v3 now reflects 31 canonical Assets, 45 Aliases, 75
  effective Opinions, 111 Attention occurrences, 75 effective ThesisChange
  artifacts, 13 Assets with 2+ Investors, and one Asset with 3+ Investors.
- No Consensus, Momentum, Warming, Score, Ranking, Signal, or migration was
  introduced.

### Sprint 2F.3 — Cross-Investor Consensus / Divergence Evidence V0

- Added immutable, idempotent CrossInvestorConsensusEvidence derived from one
  Snapshot v2 and its Alignment v1.
- Eligibility is explicitly policy-versioned at three Opinion Investors.
  Each Investor contributes only one latest window Opinion direction.
- Source Asset, Snapshot, Alignment, contribution counts, membership, coverage,
  and direction-count integrity are validated before persistence.
- Real calibration processed 14 current overlap Snapshots, all
  INSUFFICIENT_EVIDENCE, with zero eligible three-Opinion-Investor cases and
  no Consensus/Divergent state. The database retains 15 immutable evidence
  rows including one historical source.
- No score, weighting, ranking, Momentum, Warming, Signal, or Research
  Candidate logic was added.

### Sprint 2F.3.2 — Consensus Evidence Semantic Hardening

- Added active policy `cross-investor-consensus-evidence-v2` while preserving
  all `cross-investor-consensus-evidence-v1` artifacts.
- V1 retains its historical broad `DIVERGENT` rule; v2 reserves `DIVERGENT`
  for direct bullish/bearish conflict.
- V2 adds `MIXED_WITH_NEUTRAL` for bullish/neutral or bearish/neutral mixes
  without the opposite directional side.
- Strong bullish/bearish directions still map to bullish/bearish, and only the
  latest window Opinion per Investor contributes one direction.
- Real recalibration classifies `招商轮船 (SH:601872)` with
  `BULLISH / NEUTRAL / NEUTRAL` as `MIXED_WITH_NEUTRAL`.
- No LLM, score, weighting, ranking, Momentum, Warming, Signal, or Research
  Candidate logic was added.

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
- `resolution/`: deterministic AssetResolver plus immutable resolution
  projection/Opinion materialization services. It never calls an LLM or creates
  Asset master data automatically, and Asset recovery cannot rewrite
  `EventAnalysis`.
- `pipeline/`: application orchestration, including core processing and recovery
  reconciliation. External waits are outside database transactions.
- `intelligence/policies/`: pure deterministic reducers/matchers/aggregation
  policies.
- `intelligence/services/`: StateUpdate, AttentionOccurrence, ThesisChange,
  AssetIntelligence, CrossInvestorAssetSnapshot, and CrossInvestorAssetAlignment
  services.
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

11. **Directional Alignment is not Consensus.** 2F.2 emits a deterministic
    coverage/alignment view from one immutable snapshot; it does not select a
    consensus winner or calculate a score.

12. **Analysis-time status is immutable during Asset recovery.**
    `EventAnalysis.status`, `calculated_at`, `structured_output`, and Analysis
    identity metadata remain the persisted Analysis-time record. Current Asset
    resolution is a query-time projection, and missing Opinions may be
    materialized idempotently without rewriting that record.

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
| `20260905_0017` | CrossInvestorAssetAlignment |
| `20260910_0018` | CrossInvestor Consensus/Divergence Evidence |

Real PostgreSQL verification currently reports:

- Alembic revision: `20260910_0018 (head)`.
- `alembic check`: no new upgrade operations.
- Tables `cross_investor_asset_snapshots` and
  `cross_investor_asset_alignments` exist.
- Fourteen current v2 overlap snapshots have corresponding immutable alignment
  artifacts.

## Current real PostgreSQL data snapshot

The latest read-only audit of the development `snowball` database reports:

| Entity/metric | Count or value |
| --- | ---: |
| Investors | 42 |
| RawEvents | 1173 |
| EventAnalyses | 1537 |
| Active Opinion Analysis rows | 1173 / 1173 |
| Effective Opinions | 76 |
| Effective AttentionOccurrences | 122 |
| Effective ThesisChange | 76 |
| Canonical Assets | 31 |
| AssetAlias rows | 45 |
| Portfolio rows | 0 |
| PortfolioSnapshotBatch rows | 0 |
| PositionSnapshot rows | 0 |
| PortfolioAction rows | 0 |
| InvestorActionConsistency rows | 0 |
| CrossInvestorAssetSnapshot rows | 81 (51 prior + 30 recalculated) |
| CrossInvestorAssetAlignment rows | 40 (26 prior + 14 recalculated) |
| CrossInvestorConsensusEvidence rows | 43 (29 v1 + 14 v2) |

The observed RawEvent range is 2026-08-11 through 2026-09-10, approximately
30.64 days. Active Analysis statuses for the approved production identity are:

- `NO_OPINION`: 808
- `PARTIALLY_RESOLVED`: 317
- `SUCCESS`: 48
- `FAILED`: 0

The 2F.3.1 targeted expansion added 555 RawEvents for one selected Investor;
all 555 active Analyses succeeded with 610 Opinion-analysis calls including
55 bounded retries. The active data has 47 Investor × Asset Attention pairs,
11 Assets observed by two Investors, three Assets observed by three or more
Investors, and one Asset observed by three or more Opinion Investors. There
are 541 unresolved asset entries over 278 names; Portfolio facts remain
absent.

The active evidence has 14 Assets observed by two or more Attention Investors,
three Assets observed by three or more Attention Investors, 11 Assets
observed by two or more Opinion Investors, and one Asset observed by three
Opinion Investors.
Sample-bias fields are not sufficiently populated to infer investor style or
industry concentration.

2F.3.2 calibration of the active Snapshot v2 / Alignment v1 inputs:

Latest alignment coverage is COMPLETE=10, PARTIAL=3, and NONE=2.
Directional alignment includes ALIGNED_BULLISH=4, ALIGNED_BEARISH=1, and
MIXED_DIRECTION=6; no ALIGNED_NEUTRAL case is present. Consensus evidence
contains 29 immutable v1 artifacts and 14 immutable v2 artifacts for the same
14 current overlap sources. V2 states are INSUFFICIENT_EVIDENCE=13 and
MIXED_WITH_NEUTRAL=1; there is no current v2 Consensus or DIVERGENT case.
The one eligible Asset is 招商轮船 (SH:601872), whose latest directions are
BULLISH / NEUTRAL / NEUTRAL. Its v1 historical artifact remains DIVERGENT;
its v2 artifact is MIXED_WITH_NEUTRAL.

## Tests and verification

The current repository verification is:

- `pytest`: **450 passed**, with two non-failing environment warnings (FastAPI
  test-client deprecation and `.pytest_cache` permission).
- `ruff format --check .`: passed; 263 files formatted.
- `ruff check .`: passed.
- Alembic current/check against real PostgreSQL: `20260910_0018 (head)`, no drift.
- CrossInvestor evidence tests are in
  `tests/integration/test_cross_investor_asset_snapshot.py` and
  `tests/test_cross_investor_consensus_evidence.py`; Coverage/Alignment A-K
  tests and Repository provenance tests are in
  `tests/integration/test_cross_investor_asset_alignment.py`; model metadata
  coverage is updated in `tests/test_models.py`.

The pytest suite is offline and does not call real LLM providers or Xueqiu.
Real provider/collector validation has been performed manually through the
existing production entry points, outside pytest.

## Unfinished work

- Attention Momentum (`NEW`, `RISING`, `STABLE`, `COOLING`, `DORMANT`) remains
  paused; no thresholds or score are implemented.
- Cross-investor Consensus/Divergence evidence v2 is implemented and
  semantically calibrated. The current dataset has one eligible
  `MIXED_WITH_NEUTRAL` case, but no v2 Consensus or direct v2 DIVERGENT case.
  Consensus Change Over Time, warming, Industry Trend, and Theme Trend are not
  implemented.
- `CrossInvestorAssetSnapshot` remains an evidence foundation and
  `CrossInvestorAssetAlignment` remains a coverage/alignment view only; neither
  chooses a consensus winner or ranks Investors/Assets.
- Portfolio Collector, real Portfolio snapshot ingestion, and broader Portfolio
  Intelligence are not implemented; the current database has no Portfolio facts.
- Opinion × Action expansion, performance analysis, Research Signal/Candidate,
  Scheduler, Dashboard, and Product API remain planned.
- Bounded unresolved-asset recovery and safe expansion exist, but no large
  securities master or automated external identity source exists.
- No additional LLM prompt or model routing work is part of the current state.

## Known issues and technical debt

1. **Temporal sparsity:** Following Feed history currently covers about 30.64
   days but still has date gaps. This is not yet sufficient for robust
   multi-week Momentum calibration.
2. **Asset coverage:** 541 unresolved entries remain across 278 names.
   Name-only, partial-symbol,
   cross-listing, concept, and extraction-error cases must not be guessed.
3. **Portfolio absence:** Zero Portfolio rows means Portfolio evidence cannot
   yet validate Opinion × Action behavior at real-data scale.
4. **Sparse overlap:** Thirteen Assets have two-Investor overlap and one has
   3+ Investors; the sample is still too small for production-level
   Consensus/Divergence validation.
5. **Analysis quality:** Active Analysis coverage is complete and active
   failures are zero, but most outputs remain PARTIALLY_RESOLVED because the
   Asset Master does not yet cover the extracted references.
6. **Manual operational checks:** Real PostgreSQL and browser/provider smoke
   checks are command-line/manual workflows; they are not part of pytest.
7. **Environment-specific database tooling:** This Windows development setup
   requires the established temporary psycopg client-cursor compatibility shim
   when invoking Alembic; no source migration drift was found.
8. **Working-tree hygiene:** The current branch contains uncommitted sprint
  changes, including the audit script and CrossInvestor 2F.1/2F.2 implementation. A new
   session must preserve them and must not reset, stash, or discard them.

## Current blockers

There is no unresolved code or migration blocker for the implemented foundation.
The practical blockers are data readiness:

- Xueqiu browser-native pagination stops around the current history window;
  deeper historical coverage cannot be assumed or forced.
- Asset Master coverage limits the number of resolved Opinions and Attention
  facts.
- No real Portfolio snapshot stream exists.
- Only one Asset has 3+ Investor overlap; broader overlap is still needed.
- Asset resolution is the primary current data bottleneck.

These are data/product-readiness limits, not reasons to add fallback inference,
scores, or provider-specific logic.

## Recommended next task

The next implementation candidate is broader evidence calibration:

1. Keep the current Snapshot, Alignment, and Consensus evidence contracts
   frozen as the only inputs.
2. Wait for more 3+ Investor overlap and longer time series before adding
   broader Consensus/Divergence semantics.
3. Keep Momentum paused until natural 14d/28d data exists, and treat Portfolio
   as optional auxiliary evidence until real snapshots arrive.

Before that task, a new session should read `AGENTS.md`, this file, the current
contracts/services/repositories, and run `git status`, `pytest`, Ruff, and
Alembic checks. Do not start Signal, Scheduler, Dashboard, or Portfolio
Collector work unless explicitly requested.
