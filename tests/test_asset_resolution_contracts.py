from uuid import uuid4

import pytest
from pydantic import ValidationError

from contracts import (
    AssetOpinionExtraction,
    AssetReference,
    AssetResolutionResult,
    AssetResolutionStatus,
    OpinionDirection,
    OpinionExtractionResult,
    UnresolvedAsset,
    normalize_asset_reference,
    normalize_market_hint,
    normalize_symbol_hint,
)


def reference(**overrides: object) -> AssetReference:
    values: dict[str, object] = {
        "name_hint": "腾讯控股",
        "symbol_hint": "00700",
        "market_hint": "HK",
    }
    values.update(overrides)
    return AssetReference(**values)


def test_asset_reference_is_source_neutral_and_requires_a_hint() -> None:
    value = reference(symbol_hint=None, market_hint=None)

    assert value.name_hint == "腾讯控股"
    assert value.model_dump_json()

    with pytest.raises(ValidationError):
        AssetReference()


def test_asset_resolution_result_states_have_explicit_identity_shapes() -> None:
    asset_id = uuid4()
    candidate_a = uuid4()
    candidate_b = uuid4()

    resolved = AssetResolutionResult(
        status=AssetResolutionStatus.RESOLVED,
        reference=reference(),
        asset_id=asset_id,
        matched_by="SYMBOL",
    )
    unresolved = AssetResolutionResult(
        status=AssetResolutionStatus.UNRESOLVED,
        reference=reference(),
    )
    ambiguous = AssetResolutionResult(
        status=AssetResolutionStatus.AMBIGUOUS,
        reference=reference(name_hint="同名公司"),
        candidate_asset_ids=(candidate_a, candidate_b),
    )
    invalid = AssetResolutionResult(
        status=AssetResolutionStatus.INVALID,
        reference=reference(),
    )

    assert resolved.asset_id == asset_id
    assert unresolved.asset_id is None
    assert ambiguous.candidate_asset_ids == (candidate_a, candidate_b)
    assert invalid.status is AssetResolutionStatus.INVALID

    with pytest.raises(ValidationError):
        AssetResolutionResult(status=AssetResolutionStatus.RESOLVED, reference=reference())
    with pytest.raises(ValidationError):
        AssetResolutionResult(
            status=AssetResolutionStatus.AMBIGUOUS,
            reference=reference(),
            candidate_asset_ids=(candidate_a,),
        )


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SH", "SH"),
        ("SSE", "SH"),
        ("SHANGHAI", "SH"),
        ("SZ", "SZ"),
        ("SZSE", "SZ"),
        ("SHENZHEN", "SZ"),
        ("HK", "HK"),
        ("HKEX", "HK"),
        ("HONGKONG", "HK"),
        ("NASDAQ", None),
        (None, None),
    ],
)
def test_market_normalization_is_explicit(value: str | None, expected: str | None) -> None:
    assert normalize_market_hint(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("SH600585", "600585"),
        ("SSE600585", "600585"),
        ("SHANGHAI600585", "600585"),
        ("600585.SH", "600585"),
        ("SZ300274", "300274"),
        ("SHENZHEN300274", "300274"),
        ("300274.SZSE", "300274"),
        ("0700.HK", "0700"),
        ("0700.HONGKONG", "0700"),
        ("HK0700", "0700"),
        ("600585", "600585"),
        (None, None),
    ],
)
def test_symbol_normalization_strips_known_market_wrappers(
    value: str | None, expected: str | None
) -> None:
    assert normalize_symbol_hint(value) == expected


def test_normalization_does_not_guess_market_from_bare_symbol_length() -> None:
    normalized = normalize_asset_reference(AssetReference(symbol_hint="600585"))

    assert normalized.symbol == "600585"
    assert normalized.market is None


def test_symbol_embedded_market_is_used_only_when_unambiguous() -> None:
    assert normalize_asset_reference(AssetReference(symbol_hint="SH600585")).market == "SH"
    assert (
        normalize_asset_reference(AssetReference(symbol_hint="0700.HK", market_hint="SH")).market
        is None
    )


def test_unresolved_asset_preserves_full_extracted_opinion_semantics() -> None:
    extraction = AssetOpinionExtraction(
        asset_name="海螺水泥",
        symbol="SH600585",
        market="SH",
        direction=OpinionDirection.BULLISH,
        strength=70,
        confidence=0.9,
        thesis=("分红能力",),
        catalysts=("利润分配",),
        risks=("代码待确认",),
        time_horizon="LONG_TERM",
    )

    unresolved = UnresolvedAsset.from_extraction(extraction)

    assert unresolved.asset_name == "海螺水泥"
    assert unresolved.symbol == "SH600585"
    assert unresolved.market == "SH"
    assert unresolved.direction is OpinionDirection.BULLISH
    assert unresolved.strength == 70
    assert unresolved.confidence == 0.9
    assert unresolved.thesis == ("分红能力",)
    assert unresolved.catalysts == ("利润分配",)
    assert unresolved.risks == ("代码待确认",)
    assert unresolved.time_horizon == "LONG_TERM"
    assert extraction.to_asset_reference().symbol_hint == "SH600585"


def test_extracted_opinion_can_carry_name_only_identity_hints() -> None:
    extraction = AssetOpinionExtraction(
        asset_name="一家未命名 AI 公司",
        symbol=None,
        market=None,
        direction=OpinionDirection.BULLISH,
        strength=60,
        confidence=0.55,
    )

    reference = extraction.to_asset_reference()

    assert reference.name_hint == "一家未命名 AI 公司"
    assert reference.symbol_hint is None
    assert reference.market_hint is None


def test_distinct_name_only_opinions_are_not_treated_as_duplicates() -> None:
    result = OpinionExtractionResult(
        investment_related=True,
        model_version="test-model",
        opinions=(
            AssetOpinionExtraction(
                asset_name="第一家未命名公司",
                direction=OpinionDirection.BULLISH,
                strength=60,
                confidence=0.6,
            ),
            AssetOpinionExtraction(
                asset_name="第二家未命名公司",
                direction=OpinionDirection.BEARISH,
                strength=40,
                confidence=0.6,
            ),
        ),
    )

    assert len(result.opinions) == 2
