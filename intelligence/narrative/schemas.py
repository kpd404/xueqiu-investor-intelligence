"""Read-side contracts for fact-only Intelligence Narratives."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class NarrativeAssetIdentity(BaseModel):
    """Listing-level identity carried into the narrative projection."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    name: str = Field(min_length=1, max_length=255)
    market: str = Field(min_length=1, max_length=32)
    symbol: str = Field(min_length=1, max_length=64)


class IntelligenceNarrativeView(BaseModel):
    """Deterministic, observed-evidence-only narrative for one Asset."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset: NarrativeAssetIdentity
    headline: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1)
    attention_summary: str = Field(min_length=1)
    thesis_summary: str = Field(min_length=1)
    cross_investor_summary: str = Field(min_length=1)
    consensus_summary: str = Field(min_length=1)
    evidence_summary: str = Field(min_length=1)
    timeline_summary: str = Field(min_length=1)
    limitations: list[str] = Field(default_factory=list)


__all__ = ["IntelligenceNarrativeView", "NarrativeAssetIdentity"]
