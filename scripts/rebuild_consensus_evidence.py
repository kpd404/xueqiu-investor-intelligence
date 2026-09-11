"""Build Consensus/Divergence evidence from the latest current-policy Snapshots."""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from config import get_production_analysis_policy
from contracts import (
    CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
    CROSS_INVESTOR_POLICY_VERSION,
)
from database.models import (
    Asset,
    AttentionOccurrence,
    CrossInvestorAssetSnapshot,
    EventAnalysis,
)
from database.session import SessionFactory
from database.unit_of_work import SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork
from intelligence import CrossInvestorConsensusEvidenceService


def _load_latest_overlap_snapshots(analysis_version: str):
    with SessionFactory() as session:
        statement = (
            select(CrossInvestorAssetSnapshot, Asset.name)
            .join(Asset, Asset.id == CrossInvestorAssetSnapshot.asset_id)
            .where(
                CrossInvestorAssetSnapshot.opinion_analysis_version == analysis_version,
                CrossInvestorAssetSnapshot.cross_investor_policy_version
                == CROSS_INVESTOR_POLICY_VERSION,
            )
            .order_by(
                CrossInvestorAssetSnapshot.asset_id,
                CrossInvestorAssetSnapshot.calculated_at.desc(),
                CrossInvestorAssetSnapshot.id.desc(),
            )
        )
        latest_by_asset = {}
        for snapshot, name in session.execute(statement):
            latest_by_asset.setdefault(snapshot.asset_id, (snapshot.id, str(name)))
        attention_statement = (
            select(AttentionOccurrence.asset_id, AttentionOccurrence.id)
            .outerjoin(EventAnalysis, AttentionOccurrence.analysis_id == EventAnalysis.id)
            .where(
                AttentionOccurrence.attention_policy_version == "attention-occurrence-v1",
                (
                    AttentionOccurrence.analysis_id.is_(None)
                    | (
                        (EventAnalysis.analysis_version == analysis_version)
                        & EventAnalysis.status.in_(["SUCCESS", "PARTIALLY_RESOLVED"])
                    )
                ),
            )
        )
        current_attention_ids = {}
        for asset_id, occurrence_id in session.execute(attention_statement):
            current_attention_ids.setdefault(asset_id, set()).add(str(occurrence_id))
        current_snapshots = {}
        for asset_id, (snapshot_id, name) in latest_by_asset.items():
            snapshot = session.get(CrossInvestorAssetSnapshot, snapshot_id)
            if snapshot is None or snapshot.attention_investor_count < 2:
                continue
            snapshot_attention_ids = {
                occurrence_id
                for contribution in snapshot.contributions or []
                for occurrence_id in (
                    contribution.get("attention_occurrence_ids", [])
                    if isinstance(contribution, dict)
                    else []
                )
            }
            snapshot_attention_ids = {
                str(occurrence_id) for occurrence_id in snapshot_attention_ids
            }
            if snapshot_attention_ids == current_attention_ids.get(asset_id, set()):
                current_snapshots[asset_id] = (snapshot_id, name)
    return tuple((snapshot_id, name) for snapshot_id, name in current_snapshots.values())


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    policy = get_production_analysis_policy()
    source_snapshots = _load_latest_overlap_snapshots(policy.active_analysis_version)
    service = CrossInvestorConsensusEvidenceService(
        lambda: SqlAlchemyCrossInvestorConsensusEvidenceUnitOfWork(SessionFactory),
        consensus_policy_version=CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
    )

    state_counts: Counter[str] = Counter()
    coverage_counts: Counter[str] = Counter()
    failures: list[str] = []
    eligible = 0
    processed = 0
    for snapshot_id, asset_name in source_snapshots:
        try:
            evidence = service.calculate(snapshot_id)
        except Exception as exc:
            failures.append(f"{snapshot_id}:{type(exc).__name__}")
            continue
        processed += 1
        state_counts[evidence.consensus_state.value] += 1
        coverage_counts[evidence.opinion_coverage_state.value] += 1
        eligible += evidence.opinion_investor_count >= 3
        print(
            f"asset={asset_name} attention={evidence.attention_investor_count} "
            f"opinions={evidence.opinion_investor_count} "
            f"coverage={evidence.opinion_coverage_state.value} "
            f"state={evidence.consensus_state.value}"
        )

    result = {
        "analysis_version": policy.active_analysis_version,
        "consensus_policy_version": CROSS_INVESTOR_CONSENSUS_POLICY_VERSION_V2,
        "source_snapshots": len(source_snapshots),
        "processed": processed,
        "eligible_opinion_investor_count_3_plus": eligible,
        "state_counts": dict(state_counts),
        "coverage_counts": dict(coverage_counts),
        "failed": failures,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
