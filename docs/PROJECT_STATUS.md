# Project Status

Last repository status reset: 2026-09-20

This document describes the current repository state. Existing semantic
contracts and historical sprint records remain authoritative for what was
implemented; the current engineering priority is operational execution.

## Current phase and sprint

**Phase 3 — Operational MVP is COMPLETE.**

- Phase 0 Foundation is complete.
- Phase 1 Data / Intelligence Foundation is complete.
- Phase 2 Intelligence Product Foundation is complete / frozen.
- The verified product is browseable and manually refreshable through an
  authenticated Edge CDP session.
- OMVP-1.1 — Authenticated CDP Live Collection Recovery & Source-to-Product
  Proof is **COMPLETE**.
- OMVP-2 — Scheduled Refresh + Freshness + Failure Visibility is
  **COMPLETE**.
- OMVP-3 — Daily Intelligence Inbox is **COMPLETE**.
- Attention Momentum remains paused because historical completeness and
  temporal coverage are `UNKNOWN` / insufficient for absence-sensitive
  inference.

## Product state

The current product is a **Scheduled Operational Intelligence Product with a
Recent Intelligence Inbox**, not Production Ready. The runtime requires an
operator-started authenticated Edge CDP endpoint.

Completed product-facing capability includes:

- real Xueqiu Following Feed collector foundation and collection provenance;
- real LLM Analysis with explicit production identity;
- deterministic Asset Resolution and Opinion materialization;
- Investor / Asset state, Attention, Thesis, Cross-Investor evidence,
  Signal, IntelligenceEvent, Priority, Feed, and Feed lifecycle;
- Asset Product View and Investor Product View;
- React frontend and Asset ↔ Investor cross-navigation;
- evidence traceability back to RawEvent and source artifacts.

The verified critical path is:

```text
Collect → Analyze → Materialize → Product
```

## Deliberately deferred after Phase 3

- notifications and since-last-visit logic;
- always-on production deployment and CI/CD.

Scheduled execution, freshness, failure visibility, manual/scheduled
consistency, and Recent Intelligence presentation are complete. User read
state, notifications, and always-on deployment remain deferred.

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
| `20260920_0024` | OperationalRefreshRun execution metadata |

Real PostgreSQL verification currently reports:

- Alembic revision: `20260920_0024 (head)`.
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
| RawEvents | 1615 |
| EventAnalyses | 1979 |
| Active Opinion Analysis rows | 1614 / 1615 |
| Effective Opinions | 236 |
| Effective AttentionOccurrences | 303 |
| Effective ThesisChange | 222 |
| Canonical Assets | 53 |
| Portfolio rows | 0 |
| PortfolioSnapshotBatch rows | 0 |
| PositionSnapshot rows | 0 |
| PortfolioAction rows | 0 |
| InvestorActionConsistency rows | 0 |
| CollectionRun rows | 19 |
| CollectionObservation rows | 262 |
| OperationalRefreshRun rows | 4 |
| CrossInvestorAssetSnapshot rows | 134 |
| CrossInvestorAssetAlignment rows | 72 |
| CrossInvestorConsensusEvidence rows | 75 |
| Signals | 342 |
| IntelligenceEvents | 96 |
| IntelligenceEventEvidence | 317 |
| Priorities | 68 |
| FeedItems | 68 |

The observed RawEvent range is 2026-08-11 through 2026-09-20, approximately
40.29 days. Active Analysis statuses for the approved production identity are:

- `NO_OPINION`: 1021
- `PARTIALLY_RESOLVED`: 460
- `SUCCESS`: 133
- `FAILED`: 1

The explicit authenticated CDP and scheduled refreshes added six real
RawEvents and six current production Analyses after the Sprint 1 checkpoint.
They created no Opinions because the source batches contained unresolved or
no-opinion references. No Asset was fabricated and no historical backfill was
performed.

The active evidence has 14 Assets observed by two or more Attention Investors,
three Assets observed by three or more Attention Investors, 11 Assets
observed by two or more Opinion Investors, and one Asset observed by three
Opinion Investors.
Sample-bias fields are not sufficiently populated to infer investor style or
industry concentration.

Historical 2F.3.2 calibration snapshot (before Phase 3):

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

- `pytest`: **625 passed**, with two non-failing environment warnings (FastAPI
  test-client deprecation and `.pytest_cache` permission).
- `ruff format --check .`: passed; 426 files formatted.
- `ruff check .`: passed.
- Alembic current/check against real PostgreSQL: `20260920_0024 (head)`, no drift.
- Frontend `npm run lint`: passed.
- Frontend `npm run test`: **38 passed**.
- Frontend `npm run build`: passed.
- Real scheduled `--once` execution: `SCHEDULED / SUCCESS`.
- Real CDP-unavailable scheduled failure: `CDP_UNAVAILABLE`.
- Real recovery scheduled execution: `SCHEDULED / SUCCESS`.
- Operational Status API: `HEALTHY / FRESH` after recovery.
- Real PostgreSQL Feed audit: 66 ACTIVE items, 2 STALE items; the rolling
  24-hour Inbox query currently returns zero items, so the product shows the
  explicit recent-window empty state rather than inferring no activity.
- Explicit CDP smoke: one Following Feed batch, 16 items, `MAX_BATCHES`,
  no risk-control result.
- Explicit CDP canonical refresh: `SUCCESS`, 16 new RawEvents, 16 LLM
  requests, zero Analysis failures, Product verification passed.
- Identical CDP rerun: `SUCCESS`, 16 existing RawEvents, zero new RawEvents,
  zero LLM requests, no duplicate derived artifacts.
- CrossInvestor evidence tests are in
  `tests/integration/test_cross_investor_asset_snapshot.py` and
  `tests/test_cross_investor_consensus_evidence.py`; Coverage/Alignment A-K
  tests and Repository provenance tests are in
  `tests/integration/test_cross_investor_asset_alignment.py`; model metadata
  coverage is updated in `tests/test_models.py`.

The explicit CDP live and scheduled runs used the operator-started
authenticated Edge session at `http://127.0.0.1:9222`. The scheduler called
the same canonical refresh service, persisted `SCHEDULED` run metadata, and
recovered from a real `CDP_UNAVAILABLE` failure on the next successful run.

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
  Daily Intelligence Inbox, notifications, and always-on deployment remain
  planned. Product API, Operational Status API, and frontend Product Views
  already exist.
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
5. **Analysis quality:** Active Analysis coverage is 1614/1615; one existing
   FAILED Analysis remains explicit, and many outputs remain
   PARTIALLY_RESOLVED because the Asset Master does not cover all references.
6. **Runtime requirement:** The verified scheduled/manual live command requires
   an operator-started authenticated Edge CDP endpoint. The scheduler does not
   automate login.
7. **Environment-specific database tooling:** This Windows development setup
   requires the established temporary psycopg client-cursor compatibility shim
   when invoking Alembic; no source migration drift was found.
8. **Working-tree hygiene:** The current branch contains uncommitted sprint
  changes, including the audit script and CrossInvestor 2F.1/2F.2 implementation. A new
   session must preserve them and must not reset, stash, or discard them.

## Current blockers

The Operational MVP Sprint 2 code and migration checks are clean. Remaining
project limitations are runtime/data readiness:

- Xueqiu browser-native pagination stops around the current history window;
  deeper historical coverage cannot be assumed or forced.
- The verified live runtime depends on the operator-started authenticated CDP
  session; always-on deployment/restart hosting remains deferred.
- Asset Master coverage limits the number of resolved Opinions and Attention
  facts.
- No real Portfolio snapshot stream exists.
- Only one Asset has 3+ Investor overlap; broader overlap is still needed.
- Asset resolution is the primary current data bottleneck.
- OMVP-1.1, OMVP-2, and OMVP-3 are complete; do not start a new phase in this
  task.

These are data/product-readiness limits, not reasons to add fallback inference,
scores, or provider-specific logic.

## Recommended next task

Hold the project at the completed Phase 3 boundary. The next decision is
post-MVP hosting/restart reliability versus deeper data readiness; do not
start either in this task. Do not add new Intelligence semantics, ranking,
scoring, recommendations, or portfolio analytics without real Portfolio
facts.

## Phase 4 — Intelligence Yield Recovery

### IYR-1 — Monitored Investor Direct Collection

Status: **COMPLETE**.

The existing bounded Xueqiu Investor profile-history collector is now included
inside the canonical OperationalRefreshService collection stage. It reuses
the authenticated Edge CDP browser context/page, selects a bounded cohort of
registered Xueqiu Investors from current database evidence, and checks a
48-hour recent window with a two-page / 30-second per-Investor bound.

Following Feed and profile collection continue to use the same RawEvent hash
deduplication and existing CollectionObservation provenance. Profile-only
observations are distinguished through the existing ENTITY_HISTORY /
xueqiu_profile_history_cdp CollectionRun identity and collection strategy
metadata. No Watchlist UI, new collection table, migration, Asset Resolution
change, or Intelligence semantic was added.

Real validation on the authenticated CDP runtime:

- bounded cohort: 8 Investors;
- successful probes: 8/8;
- Profile items: 108;
- Profile mix: 37 ORIGINAL, 68 REPOST, 3 other;
- Profile-only new RawEvents: 52;
- current database RawEvents: 1,707;
- Opinion rows: 245;
- effective production Opinions: 213;
- AttentionOccurrences: 313;
- ThesisChanges: 233;
- Signals: 366;
- FeedItems: 68;
- Product verification: successful.

The Feed remained a valid historical projection; IYR-1 does not promise that
every source improvement creates a new FeedItem. Historical completeness
remains UNKNOWN.

### IYR-2 — Safe Asset Resolution Yield Recovery

Status: **COMPLETE**.

IYR-2 adds deterministic `CN` venue normalization only when an explicit
six-digit symbol maps to a supported SH/SZ prefix. Controlled Asset Master
enrichment added two listing identities and two market-scoped symbol aliases:

- 中际旭创 — `SZ:300308`;
- 新易盛 — `SZ:300502`.

No fuzzy matching, name guessing, US expansion, Index model, migration, or
Intelligence semantic change was introduced. Unsupported-market, index,
sector/theme/product, commodity, private-company, historical, and ambiguous
references remain unresolved.

The existing production-analysis maintenance runner now exposes a narrow
`--resolution-only` mode. Its execution boundary is:

    AssetResolver → CurrentAnalysisResolution projection → Opinion materialization → STOP

It does not construct Analysis/Thesis LLM providers or enter downstream
Attention/Thesis/Signal/Event/Priority/Feed stages. Focused first-time
integration proof used the real resolver and persistence UoW with zero LLM
calls. The 45-event production rerun created zero Assets, Aliases, Opinions,
or downstream artifacts; every audited database count remained unchanged.


### IYR-3 — Yield Re-validation & Phase 4 Exit Gate

Status: **COMPLETE**.

One real canonical refresh was executed on 2026-09-21 through the authenticated
CDP endpoint with the default bounded cohort. Collection produced 46 new
RawEvents from 16 Following Feed items and 63 direct-profile items. Direct
collection attempted eight Investors and succeeded for all eight; 30 of the
new RawEvents were profile-only, with no Feed/profile event overlap.

The current new-event cohort contained 15 ORIGINAL, 29 REPOST, and 2 other
events. Analysis yielded 6 SUCCESS, 10 PARTIALLY_RESOLVED, 30 NO_OPINION,
and 0 FAILED rows. It produced 6 effective Opinions, 7 AttentionOccurrences,
6 ThesisChanges, and 13 new Signals. Five of the six ThesisChanges were
material under the existing policy.

The strict pre-IYR 24-hour window contained 22 RawEvents from four Investors,
0 ORIGINAL and 22 REPOST, with an 18.2% Opinion-bearing Analysis rate. The
current new cohort reached a 34.8% Opinion-bearing rate and 32.6% ORIGINAL
content. The strict pre-window had zero Attention and Thesis artifacts at the
boundary; the current cohort produced both continuously.

The downstream audit found 0 new Event identities, 13 new Event evidence
links, 0 new Priorities, and 0 new FeedItems in this refresh. This is expected
aggregation/idempotency behavior under the existing policies, not a surfacing
failure: all 249 effective ThesisChanges had a Signal, the 26 Signals without
Event evidence were non-eligible single-investor NEW_ATTENTION signals, all
Priorities had FeedItems, and the rolling 24-hour Inbox contained 11 items
across 7 Assets and 9 Investors.

The active unresolved inventory contains 814 occurrences. The current
post-IYR source cohort is mainly UNKNOWN or legitimate deferred categories;
the deterministic safe-resolution queue is not the dominant current blocker.
SZ:300308 and SZ:300502 remain present as unique Asset Master identities with
persisted Opinion evidence. Asset and Investor Product Views returned recent
traceable evidence for the affected verification cohort.

Phase 4 is therefore **COMPLETE**. The system has moved from technically
working but structurally starved to a useful but bounded intelligence producer.
The next primary mainline is **Always-On Hosting / Restart Recovery**. No
cohort expansion or hosting work was implemented in IYR-3.

## Phase 5 - Always-On Product Runtime

### P5-1 - Durable Local Runtime & Restart Recovery

Status: **COMPLETE**.

Implemented local runtime capabilities:

- canonical start-runtime.ps1, stop-runtime.ps1, and runtime-status.ps1;
- optional interactive-user Task Scheduler registration;
- backend, scheduler, and frontend process checks with PID ownership;
- bounded runtime log rotation;
- explicit ACTION_REQUIRED CDP state;
- no embedded secrets or authentication automation;
- PostgreSQL-backed Operational Status persistence;
- existing PostgreSQL advisory lock retained.

The tested process topology is PostgreSQL -> Backend -> Scheduler/Frontend,
with Scheduler -> authenticated Edge CDP as the external collection
dependency. The scheduler itself remains an application cadence loop and does
not supervise OS processes.

Real local recovery tests passed for:

- backend startup and /health;
- persisted /api/operations/status;
- frontend availability;
- second-start idempotency;
- scheduler stop/start recovery;
- backend stop/start recovery;
- full stop-all/start-all recovery;
- Feed, Asset Product View, and Investor Product View reads after restart;
- advisory-lock exclusivity;
- CDP-unavailable refresh with persisted CDP_UNAVAILABLE and
  ACTION_REQUIRED.

P5-1 Closure completed after Windows restart. Edge CDP was restored on
127.0.0.1:9222 using the existing authenticated interactive profile. The
read-only smoke observed one Following Feed batch with 16 valid items, then
the allowed SCHEDULED refresh completed successfully. Operational Status is
HEALTHY / FRESH; the historical CDP_UNAVAILABLE failure remains preserved.
The local runtime is durable, but this is not a cloud Production Ready claim.