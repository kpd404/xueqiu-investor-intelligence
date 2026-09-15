"""Execute the approved Tier A Asset/Alias seed with a strict scope guard.

This operational wrapper reuses the existing idempotent ``seed_assets``
helper.  It does not analyze text, call an LLM, resolve fuzzy names, or run
downstream Intelligence.  Before committing, it compares every active
production unresolved reference before and after the seed in one transaction;
only the approved Tier A market+symbol occurrences may newly resolve.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import func, select

from config import get_production_analysis_policy
from contracts import (
    AssetReference,
    EventAnalysisStatus,
    UnresolvedAsset,
    normalize_asset_reference,
    normalize_market_hint,
)
from database.models import Asset, AssetAlias, EventAnalysis, Investor, RawEvent
from database.repositories import AssetRepository
from database.session import SessionFactory
from resolution import AssetResolver
from scripts.audit_tier_a_identity_integrity import (
    CANDIDATES,
    candidate_key,
    proposed_aliases,
    proposed_canonical_name,
)
from scripts.seed_assets import AliasSeed, AssetSeed, SeedSummary, seed_assets

EXPECTED_RAW_EVENTS = 1482
EXPECTED_ASSETS_BEFORE = 31
EXPECTED_ALIASES_BEFORE = 45
EXPECTED_APPROVED_OCCURRENCES = 62
EXPECTED_FAILED_EVENT_ID = "ae13276c-69ac-46eb-8672-2b3b3a854f9b"
EXPECTED_FAILED_CODE = "INVALID_STRUCTURED_OUTPUT"
ELIGIBLE_ANALYSIS_STATUSES = {
    EventAnalysisStatus.SUCCESS,
    EventAnalysisStatus.PARTIALLY_RESOLVED,
}

Row = dict[str, Any]


def _status(value: Any) -> str:
    return str(getattr(value, "value", value))


def _build_seeds() -> tuple[AssetSeed, ...]:
    seeds: list[AssetSeed] = []
    for candidate in CANDIDATES:
        symbol_alias = (
            candidate.symbol
            if candidate.market == "HK"
            else f"{candidate.market}{candidate.symbol}"
        )
        aliases = [AliasSeed(symbol_alias, "SYMBOL", candidate.market)]
        aliases.extend(
            AliasSeed(alias, "NAME", candidate.market) for alias in proposed_aliases(candidate)
        )
        seeds.append(
            AssetSeed(
                name=proposed_canonical_name(candidate),
                market=candidate.market,
                symbol=candidate.symbol,
                aliases=tuple(aliases),
                evidence=(
                    f"Approved Tier A identity {candidate.reference} {candidate_key(candidate)}; "
                    f"official evidence: {candidate.source_url}"
                ),
            )
        )
    return tuple(seeds)


SAFE_ASSET_SEEDS = _build_seeds()


class ExpansionDriftError(RuntimeError):
    """Raised when the approved preflight or resolution boundary is violated."""


def _load_current_analyses(session: Any, analysis_version: str) -> list[Any]:
    statement = (
        select(EventAnalysis, RawEvent, Investor.name)
        .join(RawEvent, EventAnalysis.event_id == RawEvent.id)
        .join(Investor, RawEvent.investor_id == Investor.id)
        .where(EventAnalysis.analysis_version == analysis_version)
        .order_by(RawEvent.published_time, RawEvent.id)
    )
    return list(session.execute(statement))


def _original_unresolved(analysis: EventAnalysis) -> tuple[UnresolvedAsset, ...]:
    output = analysis.structured_output if isinstance(analysis.structured_output, dict) else {}
    values: object = output.get("unresolved_assets", [])
    if not isinstance(values, list):
        return ()
    return tuple(UnresolvedAsset.model_validate(value) for value in values)


def _approved_candidate(item: UnresolvedAsset) -> Any | None:
    if not item.market or not item.symbol:
        return None
    if normalize_market_hint(item.market) is None:
        return None
    normalized = normalize_asset_reference(
        AssetReference(symbol_hint=item.symbol, market_hint=item.market)
    )
    for candidate in CANDIDATES:
        if (
            item.asset_name.strip() == candidate.reference
            and normalize_market_hint(item.market) == candidate.market
            and normalized.market == candidate.market
            and normalized.symbol == candidate.symbol
        ):
            return candidate
    return None


def _resolution_records(session: Any, analysis_version: str) -> list[Row]:
    resolver = AssetResolver(AssetRepository(session))
    records: list[Row] = []
    for analysis, event, investor_name in _load_current_analyses(session, analysis_version):
        if analysis.status not in ELIGIBLE_ANALYSIS_STATUSES:
            continue
        for item_index, item in enumerate(_original_unresolved(analysis)):
            result = resolver.resolve(item.to_asset_reference())
            records.append(
                {
                    "key": f"{analysis.id}:{item_index}",
                    "analysis_id": str(analysis.id),
                    "event_id": str(event.id),
                    "investor": str(investor_name),
                    "item_index": item_index,
                    "reference": item.asset_name,
                    "market": item.market,
                    "symbol": item.symbol,
                    "normalized_market": result.normalized_market,
                    "normalized_symbol": result.normalized_symbol,
                    "status": result.status.value,
                    "asset_id": str(result.asset_id) if result.asset_id else None,
                    "matched_by": result.matched_by,
                    "candidate": candidate_key(_approved_candidate(item))
                    if _approved_candidate(item)
                    else None,
                }
            )
    return records


def _catalog_counts(session: Any) -> dict[str, int]:
    return {
        "assets": int(session.scalar(select(func.count()).select_from(Asset)) or 0),
        "aliases": int(session.scalar(select(func.count()).select_from(AssetAlias)) or 0),
    }


def _exact_assets(session: Any) -> dict[str, list[Asset]]:
    result: dict[str, list[Asset]] = {}
    for candidate in CANDIDATES:
        rows = list(
            session.scalars(
                select(Asset).where(
                    func.upper(Asset.market) == candidate.market,
                    func.upper(Asset.symbol) == candidate.symbol,
                )
            )
        )
        result[candidate_key(candidate)] = rows
    return result


def _preflight(session: Any, analysis_version: str) -> dict[str, Any]:
    counts = _catalog_counts(session)
    if counts != {"assets": EXPECTED_ASSETS_BEFORE, "aliases": EXPECTED_ALIASES_BEFORE}:
        raise ExpansionDriftError(
            f"catalog drift before seed: expected 31/45, got {counts['assets']}/{counts['aliases']}"
        )
    exact = _exact_assets(session)
    collisions = {key: [str(row.id) for row in rows] for key, rows in exact.items() if rows}
    if collisions:
        raise ExpansionDriftError(f"approved exact identity collision before seed: {collisions}")
    analysis_rows = _load_current_analyses(session, analysis_version)
    event_ids = {str(event.id) for _analysis, event, _name in analysis_rows}
    if len(event_ids) != EXPECTED_RAW_EVENTS:
        raise ExpansionDriftError(
            f"current production Analysis coverage drift: {len(event_ids)}/{EXPECTED_RAW_EVENTS}"
        )
    failed = [
        {
            "event_id": str(analysis.event_id),
            "status": _status(analysis.status),
            "error_code": analysis.error_code,
        }
        for analysis, _event, _name in analysis_rows
        if analysis.status is EventAnalysisStatus.FAILED
    ]
    if failed != [
        {
            "event_id": EXPECTED_FAILED_EVENT_ID,
            "status": "FAILED",
            "error_code": EXPECTED_FAILED_CODE,
        }
    ]:
        raise ExpansionDriftError(f"remaining FAILED Analysis drift: {failed}")
    return {
        "catalog": counts,
        "raw_events": len(event_ids),
        "analysis_version": analysis_version,
        "analysis_rows": len(analysis_rows),
        "failed": failed,
        "exact_collisions": collisions,
    }


def _seed_summary(summary: SeedSummary) -> dict[str, Any]:
    return {
        "assets_created": summary.assets_created,
        "assets_reused": summary.assets_reused,
        "aliases_created": summary.aliases_created,
        "aliases_reused": summary.aliases_reused,
        "asset_ids": [str(value) for value in summary.asset_ids],
    }


def _run_seed(*, dry_run: bool) -> dict[str, Any]:
    policy = get_production_analysis_policy()
    analysis_version = policy.active_analysis_version
    with SessionFactory() as session:
        preflight = _preflight(session, analysis_version)
        before_records = _resolution_records(session, analysis_version)
        approved_before = {
            row["key"]: row for row in before_records if row["candidate"] is not None
        }
        if len(approved_before) != EXPECTED_APPROVED_OCCURRENCES:
            raise ExpansionDriftError(
                f"approved unresolved scope drift: expected {EXPECTED_APPROVED_OCCURRENCES}, "
                f"got {len(approved_before)}"
            )

        first = seed_assets(session, SAFE_ASSET_SEEDS)
        after_records = _resolution_records(session, analysis_version)
        after_by_key = {row["key"]: row for row in after_records}
        newly_resolved = [
            row
            for key, row in after_by_key.items()
            if row["status"] == "RESOLVED"
            and before_records_by_key(before_records).get(key, {}).get("status") != "RESOLVED"
        ]
        approved_keys = set(approved_before)
        new_keys = {row["key"] for row in newly_resolved}
        extra = [row for row in newly_resolved if row["key"] not in approved_keys]
        missing = sorted(approved_keys - new_keys)

        expected_asset_ids = {
            candidate_key(candidate): str(asset_id)
            for candidate, asset_id in zip(CANDIDATES, first.asset_ids, strict=True)
        }
        wrong_targets = [
            row
            for row in newly_resolved
            if row["key"] in approved_keys
            and row["asset_id"] != expected_asset_ids[approved_before[row["key"]]["candidate"]]
        ]
        before_by_key = before_records_by_key(before_records)
        changed_existing = [
            {
                "key": key,
                "before": before_by_key[key],
                "after": row,
            }
            for key, row in after_by_key.items()
            if before_by_key.get(key, {}).get("status") == "RESOLVED"
            and (
                row["status"] != "RESOLVED" or row["asset_id"] != before_by_key[key].get("asset_id")
            )
        ]
        guard = {
            "approved_before": len(approved_before),
            "newly_resolved": len(newly_resolved),
            "extra_resolution": extra,
            "missing_approved": missing,
            "wrong_targets": wrong_targets,
            "changed_existing_resolution": changed_existing,
            "resolved_records": newly_resolved,
        }
        if extra or missing or wrong_targets or changed_existing:
            session.rollback()
            raise ExpansionDriftError(
                "resolution scope guard failed: " + json.dumps(guard, ensure_ascii=False)
            )
        post_seed_counts = _catalog_counts(session)
        if dry_run:
            session.rollback()
            return {
                "preflight": preflight,
                "seed_first": _seed_summary(first),
                "resolution_guard": guard,
                "post_seed_catalog": post_seed_counts,
                "dry_run": True,
            }
        session.commit()

    with SessionFactory() as session:
        exact_after = _exact_assets(session)
        if any(len(rows) != 1 for rows in exact_after.values()):
            raise ExpansionDriftError(
                "post-commit exact Asset map is not one row per approved identity"
            )
        second = seed_assets(session, SAFE_ASSET_SEEDS)
        idempotency = _seed_summary(second)
        if (
            second.assets_created != 0
            or second.aliases_created != 0
            or second.assets_reused != len(SAFE_ASSET_SEEDS)
        ):
            session.rollback()
            raise ExpansionDriftError(f"idempotency rerun failed: {idempotency}")
        session.commit()

    with SessionFactory() as session:
        final_exact = _exact_assets(session)
    return {
        "preflight": preflight,
        "seed_first": _seed_summary(first),
        "resolution_guard": guard,
        "post_seed_catalog": post_seed_counts,
        "idempotency_rerun": idempotency,
        "asset_ids": {key: str(rows[0].id) for key, rows in final_exact.items() if rows},
        "dry_run": False,
    }


def before_records_by_key(records: list[Row]) -> dict[str, Row]:
    return {row["key"]: row for row in records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    try:
        result = _run_seed(dry_run=args.dry_run)
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "error_type": type(exc).__name__}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 2
    result["ok"] = True
    payload = json.dumps(result, ensure_ascii=False, indent=2, default=str)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
