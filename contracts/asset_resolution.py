import re
from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AssetReference(BaseModel):
    """Provider-neutral identity hints for one mentioned asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name_hint: str | None = Field(default=None, max_length=255)
    symbol_hint: str | None = Field(default=None, max_length=64)
    market_hint: str | None = Field(default=None, max_length=32)

    @field_validator("name_hint", "symbol_hint", "market_hint")
    @classmethod
    def normalize_hints(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @model_validator(mode="after")
    def require_one_hint(self) -> Self:
        if not any((self.name_hint, self.symbol_hint, self.market_hint)):
            raise ValueError("asset reference must contain at least one identity hint")
        return self


class AssetResolutionStatus(StrEnum):
    RESOLVED = "RESOLVED"
    UNRESOLVED = "UNRESOLVED"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


class NormalizedAssetReference(BaseModel):
    """Deterministically normalized identity values used by a future resolver."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str | None = Field(default=None, max_length=255)
    symbol: str | None = Field(default=None, max_length=64)
    market: str | None = Field(default=None, max_length=32)


class AssetResolutionResult(BaseModel):
    """Result contract for deterministic asset resolution."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: AssetResolutionStatus
    reference: AssetReference
    asset_id: UUID | None = None
    candidate_asset_ids: tuple[UUID, ...] = ()
    matched_by: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=255)
    normalized_name: str | None = Field(default=None, max_length=255)
    normalized_symbol: str | None = Field(default=None, max_length=64)
    normalized_market: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_resolution_shape(self) -> Self:
        if len(set(self.candidate_asset_ids)) != len(self.candidate_asset_ids):
            raise ValueError("candidate_asset_ids must be unique")
        if self.status is AssetResolutionStatus.RESOLVED:
            if self.asset_id is None:
                raise ValueError("resolved result must include asset_id")
            if self.candidate_asset_ids and self.asset_id not in self.candidate_asset_ids:
                raise ValueError("resolved asset_id must be among candidate_asset_ids")
        elif self.status is AssetResolutionStatus.AMBIGUOUS:
            if self.asset_id is not None:
                raise ValueError("ambiguous result must not include asset_id")
            if len(self.candidate_asset_ids) < 2:
                raise ValueError("ambiguous result must include multiple candidates")
        elif self.asset_id is not None or self.candidate_asset_ids:
            raise ValueError(f"{self.status.value.lower()} result cannot include asset IDs")
        return self


_MARKET_ALIASES = {
    "SH": "SH",
    "SSE": "SH",
    "SHANGHAI": "SH",
    "SZ": "SZ",
    "SZSE": "SZ",
    "SHENZHEN": "SZ",
    "HK": "HK",
    "HKEX": "HK",
    "HONGKONG": "HK",
}
_PREFIX_PATTERN = re.compile(r"^(SHANGHAI|SHENZHEN|HONGKONG|HKEX|SZSE|SSE|SH|SZ|HK)(.+)$")
_SUFFIX_PATTERN = re.compile(r"^(.+)\.(SHANGHAI|SHENZHEN|HONGKONG|HKEX|SZSE|SSE|SH|SZ|HK)$")


def normalize_market_hint(value: str | None) -> str | None:
    if value is None:
        return None
    return _MARKET_ALIASES.get(value.strip().upper())


def normalize_symbol_hint(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().upper()
    if not normalized:
        return None
    if match := _PREFIX_PATTERN.fullmatch(normalized):
        return match.group(2)
    if match := _SUFFIX_PATTERN.fullmatch(normalized):
        return match.group(1)
    return normalized


def normalize_name_hint(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.split())
    return normalized or None


def normalize_asset_reference(reference: AssetReference) -> NormalizedAssetReference:
    """Normalize known aliases without inferring a market from symbol length."""

    normalized_market = normalize_market_hint(reference.market_hint)
    normalized_symbol = normalize_symbol_hint(reference.symbol_hint)

    embedded_market: str | None = None
    if reference.symbol_hint:
        symbol_text = reference.symbol_hint.strip().upper()
        if match := _PREFIX_PATTERN.fullmatch(symbol_text):
            embedded_market = normalize_market_hint(match.group(1))
        elif match := _SUFFIX_PATTERN.fullmatch(symbol_text):
            embedded_market = normalize_market_hint(match.group(2))
    if normalized_market is None:
        normalized_market = embedded_market
    elif embedded_market is not None and normalized_market != embedded_market:
        normalized_market = None

    return NormalizedAssetReference(
        name=normalize_name_hint(reference.name_hint),
        symbol=normalized_symbol,
        market=normalized_market,
    )
