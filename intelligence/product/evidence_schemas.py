"""Read-only content contracts; these views are never persisted."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from contracts import OpinionDirection, ThesisChangeType
from intelligence.product.schemas import ProductAssetIdentity


class _View(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class EvidenceRaw(_View):
    raw_event_id: UUID
    investor_id: UUID
    investor_name: str
    published_time: AwareDatetime
    source: str
    source_url: str | None
    source_url_status: Literal["AVAILABLE", "MISSING_OR_UNSAFE"]
    content: str
    readable_content: str
    current_author_text: str
    contains_repost: bool


class EvidenceOpinion(_View):
    opinion_id: UUID
    role: Literal["THESIS_PREVIOUS", "THESIS_CURRENT", "DIRECTION_VOTE", "ATTENTION_OPINION"]
    direction: OpinionDirection
    thesis: tuple[str, ...]
    catalysts: tuple[str, ...]
    risks: tuple[str, ...]
    time_horizon: str | None
    confidence: float = Field(ge=0, le=1)
    analysis_id: UUID | None
    analysis_version: str | None
    model_version: str
    raw: EvidenceRaw


class EvidenceAttention(_View):
    attention_occurrence_id: UUID
    attention_only: bool
    raw: EvidenceRaw


class EvidenceComparison(_View):
    change_type: ThesisChangeType
    summary: str
    evidence: tuple[str, ...]
    confidence: float = Field(ge=0, le=1)
    comparison_version: str
    opinion_analysis_version: str


class EvidenceGroup(_View):
    source_type: str
    source_id: UUID
    event_id: UUID | None
    signal_id: UUID | None
    observed_at: AwareDatetime
    source_window_start: AwareDatetime | None
    source_window_end: AwareDatetime | None
    source_as_of: AwareDatetime | None
    direction_voter_ids: tuple[UUID, ...]
    attention_only_investor_ids: tuple[UUID, ...]
    basis: Literal["CURRENT_ASSOCIATION", "EFFECTIVE_HISTORY", "HISTORICAL_REFERENCE"]
    comparison: EvidenceComparison | None
    opinions: tuple[EvidenceOpinion, ...]
    attention: tuple[EvidenceAttention, ...]


class AvailableHistory(_View):
    thesis_change_id: UUID
    change_type: ThesisChangeType
    effective_time: AwareDatetime
    investor_id: UUID


class EvidenceReadingView(_View):
    asset: ProductAssetIdentity
    groups: tuple[EvidenceGroup, ...]
    available_history: tuple[AvailableHistory, ...] = ()
    historical_completeness: Literal["UNKNOWN"] = "UNKNOWN"
