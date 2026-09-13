"""Read-only PostgreSQL calibration for Investor Intelligence V0."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.api.dependencies import get_investor_intelligence_service


def _asset_label(asset) -> str:
    return f"{asset.asset_name} · {asset.market}:{asset.symbol}"


def _run() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    service = get_investor_intelligence_service()
    views = service.list_investor_views()
    print("# Investor Intelligence V0 Real-data Calibration")
    attention_investor_count = sum(view.attention_asset_count > 0 for view in views)
    opinion_investor_count = sum(view.opinion_asset_count > 0 for view in views)
    print(f"Investors with Attention evidence: {attention_investor_count}")
    print(f"Investors with Opinion evidence: {opinion_investor_count}")
    print(f"Investor × Asset Attention pairs: {sum(view.attention_asset_count for view in views)}")
    print(f"Investor × Asset Opinion pairs: {sum(view.opinion_asset_count for view in views)}")
    for view in views:
        attention_assets = [
            _asset_label(asset)
            for asset in view.asset_views
            if asset.attention_occurrence_count > 0
        ]
        opinion_assets = [
            _asset_label(asset) for asset in view.asset_views if asset.opinion_count > 0
        ]
        repeated_assets = [
            _asset_label(asset) for asset in view.asset_views if asset.has_repeated_opinion
        ]
        changed_assets = [
            _asset_label(asset) for asset in view.asset_views if asset.changed_count > 0
        ]
        reversal_assets = [
            _asset_label(asset) for asset in view.asset_views if asset.reversal_count > 0
        ]
        shared_attention_assets = [
            _asset_label(asset)
            for asset in view.asset_views
            if asset.attention_occurrence_count > 0 and asset.shared_attention_investor_count > 0
        ]
        shared_opinion_assets = [
            _asset_label(asset)
            for asset in view.asset_views
            if asset.opinion_count > 0 and asset.shared_opinion_investor_count > 0
        ]
        print(
            json.dumps(
                {
                    "investor": view.investor_name,
                    "investor_id": str(view.investor_id),
                    "attention_assets": attention_assets,
                    "opinion_assets": opinion_assets,
                    "repeated_opinion_assets": repeated_assets,
                    "thesis_changed_assets": changed_assets,
                    "direction_reversal_assets": reversal_assets,
                    "shared_attention_assets": shared_attention_assets,
                    "shared_opinion_assets": shared_opinion_assets,
                    "missing_thesis_comparison_count": (
                        view.data_quality.missing_thesis_comparison_count
                    ),
                    "overlaps": [
                        {
                            "other_investor": overlap.other_investor_name,
                            "shared_attention_assets": overlap.shared_attention_asset_count,
                            "shared_opinion_assets": overlap.shared_opinion_asset_count,
                        }
                        for overlap in view.overlap_summaries
                    ],
                    "completeness": view.completeness.value,
                    "limitations": view.data_quality.limitations,
                },
                ensure_ascii=False,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(_run())
