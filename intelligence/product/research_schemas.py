"""Public user-record contract, distinct from deterministic DiscoveryCandidate."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict

from intelligence.product.evidence_schemas import EvidenceReadingView


class ResearchSourceView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["CURRENT", "HISTORICAL", "UNVERIFIED", "UNAVAILABLE"]
    message: str
    evidence: EvidenceReadingView | None


class ResearchView(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: UUID
    asset_id: UUID
    asset_name: str
    status: Literal["TODO", "RESEARCHING", "ARCHIVED"]
    reason: str
    questions: str
    notes: str
    references: list[dict]
    created_at: AwareDatetime
    updated_at: AwareDatetime
    sources: list[ResearchSourceView] | None = None


class ResearchList(BaseModel):
    items: list[ResearchView]
