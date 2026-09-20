# Intelligence Read API V0

The Intelligence Read API exposes existing effective read models through a
thin FastAPI boundary. It does not collect data, call an LLM, create Assets,
persist a new artifact, calculate a score, or rank Assets.

## Semantics

Responses describe observed evidence in the monitored sample. Historical
profile completeness is always UNKNOWN. The API makes no causality,
influence, follower, influencer, or absence inference.

The latest direction field means latest observed Opinion only. It does not
mean current belief, current holding, or current conviction.

Equal timestamps use deterministic serialization order only. Serialization
order is not causal order.

## Endpoints

### GET /api/v1/intelligence/assets

Returns a bounded, stable-order list of Asset summaries. It does not return
full Investor views or the unified timeline.

Query parameters:

- market
- min_attention_investors
- min_opinion_investors
- window_start
- window_end
- limit (default 50, maximum 100)
- offset (default 0)

The minimum-investor parameters are query filters, not production thresholds.
Default ordering is asset_name, market, symbol, and asset_id.

The response contains items, total, limit, offset, and has_more.

### GET /api/intelligence/investors/{investor_id}/view

Returns the query-time `InvestorIntelligenceView` Product composition for one
Investor. It includes listing-level observed Assets, Attention occurrence
counts, effective persisted Opinion counts/latest direction, persisted
ThesisChange state, fact-time activity, data-quality limitations, and source
reference counts.

Investor Attention is not Opinion, repeated Attention is not conviction, and
Opinion direction is not a recommendation. Historical completeness remains
UNKNOWN; the endpoint does not infer historical absence from an empty window
or missing current artifact. Unknown Investors return 404. An existing
Investor with Attention but no Opinion still returns a valid view.

Investor Detail uses this endpoint once per opened Investor. Investor
Discovery continues to use its collection endpoint and does not request one
Product View per card. Asset links in the Product View use `asset_id` and
preserve market/symbol listing identity.

### GET /api/v1/intelligence/assets/{asset_id}

Returns the complete CombinedAssetIntelligenceView, including Attention,
Investor views, Opinion/Thesis context, nullable Alignment and Consensus, and
data-quality limitations.

### GET /api/v1/intelligence/assets/{asset_id}/timeline

Returns a thin projection of the Combined View event timeline:

- ATTENTION_FIRST_OBSERVED
- ATTENTION_OBSERVED
- OPINION_OBSERVED
- THESIS_CHANGE_OBSERVED

Each event retains evidence and provenance identifiers.

## Data-quality flags

The API preserves machine-readable limitations including:

- HISTORICAL_COMPLETENESS_UNKNOWN
- ABSENCE_INFERENCE_UNSUPPORTED
- MISSING_THESIS_COMPARISON
- CROSS_INVESTOR_LINEAGE_UNAVAILABLE

## Errors

- 404: unknown Asset, or no intelligence evidence in the requested detail/timeline window.
- 422: invalid UUID, timezone-naive or reversed window, invalid filters, or invalid pagination.
- 500: unexpected read failure; internal database/provider details are not exposed.

An existing Asset with no effective evidence in the requested window returns
404 with the no-evidence detail. It is never mapped to bullish, bearish,
neutral, or no-interest semantics.

## Read-only lifecycle

Each request composes the Combined Asset Intelligence service with a
rollback-only UoW. The lifecycle is:

open → read → rollback → close

GET handlers never commit.

## Example

GET /api/v1/intelligence/assets?market=HK&limit=2&offset=0

The list response contains summary fields only. Detail and timeline requests
are required to obtain the full nested read models.
