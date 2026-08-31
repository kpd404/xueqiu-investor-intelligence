from enum import StrEnum
from typing import Self
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    field_validator,
    model_validator,
)

ATTENTION_POLICY_VERSION = "attention-occurrence-v1"


class AttentionEvidenceType(StrEnum):
    OPINION = "OPINION"
    EXPLICIT_MENTION = "EXPLICIT_MENTION"
    REPOST = "REPOST"


class AssetMentionAlias(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    text: str = Field(min_length=1, max_length=255)
    alias_type: str = Field(min_length=1, max_length=32)


class AssetMentionCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    canonical_name: str = Field(min_length=1, max_length=255)
    aliases: tuple[AssetMentionAlias, ...] = ()


class AssetTextMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    matched_text: str = Field(min_length=1, max_length=255)
    matched_by: str = Field(min_length=1, max_length=32)


class AssetMentionMatch(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    matches: tuple[AssetTextMatch, ...]


class AttentionEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_type: AttentionEvidenceType
    matched_by: str = Field(min_length=1, max_length=64)
    reference: str | None = Field(default=None, max_length=255)
    details: dict[str, JsonValue] = Field(default_factory=dict)


_EVIDENCE_ORDER = {
    AttentionEvidenceType.OPINION: 0,
    AttentionEvidenceType.EXPLICIT_MENTION: 1,
    AttentionEvidenceType.REPOST: 2,
}


class AttentionOccurrenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    event_id: UUID
    published_time: AwareDatetime
    evidence_types: tuple[AttentionEvidenceType, ...]
    evidence: tuple[AttentionEvidence, ...]
    analysis_id: UUID | None = None
    opinion_id: UUID | None = None
    attention_policy_version: str = Field(min_length=1, max_length=64)
    calculated_at: AwareDatetime

    @field_validator("evidence_types")
    @classmethod
    def normalize_evidence_types(
        cls,
        values: tuple[AttentionEvidenceType, ...],
    ) -> tuple[AttentionEvidenceType, ...]:
        return tuple(sorted(set(values), key=_EVIDENCE_ORDER.__getitem__))

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        if not self.evidence_types or not self.evidence:
            raise ValueError("attention occurrence requires evidence")
        evidence_types = tuple(item.evidence_type for item in self.evidence)
        if len(set(evidence_types)) != len(evidence_types):
            raise ValueError("attention evidence types must be unique per occurrence")
        if set(evidence_types) != set(self.evidence_types):
            raise ValueError("evidence_types must match evidence entries")
        has_opinion = AttentionEvidenceType.OPINION in self.evidence_types
        if has_opinion != (self.analysis_id is not None and self.opinion_id is not None):
            raise ValueError("OPINION evidence requires analysis_id and opinion_id")
        return self


class AttentionOccurrenceView(AttentionOccurrenceCreate):
    id: UUID


class AttentionOccurrenceWriteResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    occurrence_ids: tuple[UUID, ...]
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)


class AttentionOccurrenceRebuildResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: UUID
    occurrence_ids: tuple[UUID, ...]
    affected_asset_ids: tuple[UUID, ...]
    created_count: int = Field(ge=0)
    updated_count: int = Field(ge=0)
    deleted_count: int = Field(ge=0)
    calculated_at: AwareDatetime
