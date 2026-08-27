from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    AssetOpinionExtraction,
    OpinionDirection,
    OpinionExtractionResult,
    UnresolvedAssetHint,
)


def valid_asset_opinion() -> dict[str, object]:
    return {
        "asset_name": "Tencent",
        "symbol": "00700",
        "market": "HK",
        "direction": OpinionDirection.BULLISH,
        "strength": 80,
        "confidence": 0.9,
        "thesis": ["AI商业化", "广告恢复"],
        "catalysts": [],
        "risks": [],
        "time_horizon": "LONG_TERM",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("strength", -0.1),
        ("strength", 100.1),
        ("confidence", -0.1),
        ("confidence", 1.1),
    ],
)
def test_asset_opinion_enforces_numeric_ranges(field: str, value: float) -> None:
    with pytest.raises(ValidationError):
        AssetOpinionExtraction.model_validate({**valid_asset_opinion(), field: value})


@pytest.mark.parametrize("identity_field", ["investor_id", "event_id"])
def test_extractor_contract_rejects_system_identity_fields(identity_field: str) -> None:
    with pytest.raises(ValidationError):
        AssetOpinionExtraction.model_validate(
            {**valid_asset_opinion(), identity_field: str(uuid4())}
        )


def test_no_investment_opinion_is_a_valid_result() -> None:
    result = OpinionExtractionResult(
        investment_related=False,
        opinions=(),
        model_version="mock-opinion-v1",
    )

    assert result.opinions == ()


def test_ambiguous_investment_asset_is_preserved_as_unresolved_hint() -> None:
    result = OpinionExtractionResult(
        investment_related=True,
        opinions=(),
        unresolved_assets=(
            UnresolvedAssetHint(
                asset_name="这家AI应用公司",
                symbol=None,
                market=None,
                reason="AMBIGUOUS_ASSET",
            ),
        ),
        model_version="mock-opinion-v1",
    )

    assert result.unresolved_assets[0].symbol is None
    assert result.unresolved_assets[0].market is None
