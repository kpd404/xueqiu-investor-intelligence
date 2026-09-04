"""Provider-neutral contracts for asset-centric cross-investor evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID

from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from contracts.consistency import ConsistencyType
from contracts.enums import OpinionDirection
from contracts.portfolio import PortfolioActionType
from contracts.thesis_change import ThesisChangeType

CROSS_INVESTOR_POLICY_VERSION = "cross-investor-asset-snapshot-v2"
CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION = "cross-investor-directional-alignment-v1"
# Descriptive alias retained for callers that name the derived dimension.
CROSS_INVESTOR_DIRECTIONAL_ALIGNMENT_POLICY_VERSION = CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION


def utc_now() -> datetime:
    return datetime.now(UTC)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_cross_investor_input_identity(
    *,
    asset_id: UUID,
    as_of: datetime,
    window_start: datetime,
    window_end: datetime,
    opinion_analysis_version: str,
    attention_policy_version: str,
    thesis_comparison_version: str,
    consistency_policy_version: str,
    cross_investor_policy_version: str,
    attention_occurrence_ids: tuple[UUID, ...] = (),
    opinion_ids: tuple[UUID, ...] = (),
    thesis_change_ids: tuple[UUID, ...] = (),
    portfolio_action_ids: tuple[UUID, ...] = (),
    consistency_ids: tuple[UUID, ...] = (),
    first_attention_dependencies: tuple[tuple[UUID, UUID, datetime], ...] = (),
) -> str:
    """Return a deterministic SHA-256 fingerprint of all aggregation inputs."""

    payload = {
        "asset_id": str(asset_id),
        "as_of": _utc(as_of).isoformat(),
        "attention_occurrence_ids": sorted(str(value) for value in attention_occurrence_ids),
        "attention_policy_version": attention_policy_version,
        "behavior_inputs": {
            "consistency_ids": sorted(str(value) for value in consistency_ids),
            "opinion_ids": sorted(str(value) for value in opinion_ids),
            "portfolio_action_ids": sorted(str(value) for value in portfolio_action_ids),
            "thesis_change_ids": sorted(str(value) for value in thesis_change_ids),
        },
        "cross_investor_policy_version": cross_investor_policy_version,
        "consistency_policy_version": consistency_policy_version,
        "first_attention_dependencies": [
            {
                "investor_id": str(investor_id),
                "occurrence_id": str(occurrence_id),
                "published_time": _utc(published_time).isoformat(),
            }
            for investor_id, occurrence_id, published_time in sorted(
                first_attention_dependencies,
                key=lambda value: (value[0].int, value[1].int, _utc(value[2]).isoformat()),
            )
        ],
        "opinion_analysis_version": opinion_analysis_version,
        "thesis_comparison_version": thesis_comparison_version,
        "window_end": _utc(window_end).isoformat(),
        "window_start": _utc(window_start).isoformat(),
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def build_cross_investor_alignment_input_identity(
    *,
    source_snapshot_input_identity: str,
    alignment_policy_version: str,
) -> str:
    """Return the fingerprint for one snapshot and alignment policy pair."""

    payload = {
        "alignment_policy_version": alignment_policy_version,
        "source_snapshot_input_identity": source_snapshot_input_identity,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


class CrossInvestorContribution(BaseModel):
    """Traceable contribution of one Investor to an Asset window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    attention_occurrence_ids: tuple[UUID, ...] = ()
    attention_occurrence_count: int = Field(default=0, ge=0)
    first_attention_occurrence_id: UUID | None = None
    first_attention_published_time: AwareDatetime | None = None
    window_opinion_ids: tuple[UUID, ...] = ()
    window_opinion_count: int = Field(default=0, ge=0)
    latest_window_opinion_id: UUID | None = Field(
        default=None,
        validation_alias=AliasChoices("latest_window_opinion_id", "latest_opinion_id"),
    )
    latest_window_opinion_direction: OpinionDirection | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "latest_window_opinion_direction",
            "latest_opinion_direction",
        ),
    )
    latest_window_opinion_time: AwareDatetime | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "latest_window_opinion_time",
            "latest_opinion_published_time",
        ),
    )
    thesis_change_ids: tuple[UUID, ...] = ()
    thesis_change_types: tuple[ThesisChangeType, ...] = ()
    portfolio_action_ids: tuple[UUID, ...] = ()
    portfolio_action_types: tuple[PortfolioActionType, ...] = ()
    consistency_ids: tuple[UUID, ...] = ()
    consistency_types: tuple[ConsistencyType, ...] = ()

    @model_validator(mode="after")
    def validate_provenance(self) -> CrossInvestorContribution:
        if self.attention_occurrence_count != len(self.attention_occurrence_ids):
            raise ValueError("attention_occurrence_count must match attention_occurrence_ids")
        if len(set(self.attention_occurrence_ids)) != len(self.attention_occurrence_ids):
            raise ValueError("attention_occurrence_ids must be unique")
        if self.window_opinion_count != len(self.window_opinion_ids):
            raise ValueError("window_opinion_count must match window_opinion_ids")
        if len(set(self.window_opinion_ids)) != len(self.window_opinion_ids):
            raise ValueError("window_opinion_ids must be unique")
        if (
            self.window_opinion_ids
            and self.latest_window_opinion_id is not None
            and self.latest_window_opinion_id not in self.window_opinion_ids
        ):
            raise ValueError("latest window Opinion must be in window_opinion_ids")
        return self

    # Compatibility aliases for v1 callers and persisted contribution readers.
    @property
    def latest_opinion_id(self) -> UUID | None:
        return self.latest_window_opinion_id

    @property
    def latest_opinion_direction(self) -> OpinionDirection | None:
        return self.latest_window_opinion_direction

    @property
    def latest_opinion_published_time(self) -> AwareDatetime | None:
        return self.latest_window_opinion_time


class CrossInvestorAssetSnapshotCreate(BaseModel):
    """Immutable asset-centric aggregation over a fact-time window."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    as_of: AwareDatetime
    window_start: AwareDatetime
    window_end: AwareDatetime

    attention_occurrence_count: int = Field(ge=0)
    attention_investor_count: int = Field(ge=0)
    new_attention_investor_count: int = Field(ge=0)

    opinion_count: int = Field(ge=0)
    opinion_investor_count: int = Field(ge=0)
    bullish_investor_count: int = Field(ge=0)
    bearish_investor_count: int = Field(ge=0)
    neutral_investor_count: int = Field(ge=0)

    thesis_change_count: int = Field(ge=0)
    thesis_change_investor_count: int = Field(ge=0)
    thesis_reinforced_investor_count: int = Field(ge=0)
    thesis_changed_investor_count: int = Field(ge=0)

    portfolio_action_count: int = Field(ge=0)
    portfolio_action_investor_count: int = Field(ge=0)
    position_increased_count: int = Field(ge=0)
    position_decreased_count: int = Field(ge=0)

    consistency_count: int = Field(ge=0)
    consistency_investor_count: int = Field(ge=0)
    positive_alignment_count: int = Field(ge=0)
    negative_alignment_count: int = Field(ge=0)

    contributions: tuple[CrossInvestorContribution, ...] = ()

    opinion_analysis_version: str = Field(min_length=1, max_length=255)
    attention_policy_version: str = Field(min_length=1, max_length=64)
    thesis_comparison_version: str = Field(min_length=1, max_length=255)
    consistency_policy_version: str = Field(min_length=1, max_length=64)
    cross_investor_policy_version: str = Field(
        default=CROSS_INVESTOR_POLICY_VERSION,
        min_length=1,
        max_length=64,
    )
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    input_identity: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )

    @model_validator(mode="after")
    def validate_window(self) -> CrossInvestorAssetSnapshotCreate:
        if self.window_start > self.window_end:
            raise ValueError("window_start must be earlier than or equal to window_end")
        if self.as_of < self.window_end:
            raise ValueError("as_of must be on or after window_end")
        investor_ids = [item.investor_id for item in self.contributions]
        if len(investor_ids) != len(set(investor_ids)):
            raise ValueError("contributions must contain one entry per investor")
        return self


class CrossInvestorAssetSnapshotView(CrossInvestorAssetSnapshotCreate):
    id: UUID


class CrossInvestorAssetSnapshotResult(BaseModel):
    """Result of calculating one cross-investor asset snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    snapshot_id: UUID
    asset_id: UUID
    window_start: AwareDatetime
    window_end: AwareDatetime
    cross_investor_policy_version: str = Field(min_length=1, max_length=64)
    created: bool


class OpinionCoverageState(StrEnum):
    """Coverage of Attention Investors by effective window Opinions."""

    NONE = "NONE"
    PARTIAL = "PARTIAL"
    COMPLETE = "COMPLETE"


class DirectionalAlignmentState(StrEnum):
    """Per-Investor latest Opinion direction alignment, not Consensus."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    ALIGNED_BULLISH = "ALIGNED_BULLISH"
    ALIGNED_BEARISH = "ALIGNED_BEARISH"
    ALIGNED_NEUTRAL = "ALIGNED_NEUTRAL"
    MIXED_DIRECTION = "MIXED_DIRECTION"


class CrossInvestorAssetAlignmentCreate(BaseModel):
    """Immutable deterministic coverage and direction view of one snapshot."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    source_snapshot_id: UUID
    opinion_coverage_state: OpinionCoverageState
    directional_alignment_state: DirectionalAlignmentState
    alignment_policy_version: str = Field(min_length=1, max_length=64)
    input_identity: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )
    calculated_at: AwareDatetime = Field(default_factory=utc_now)
    created_at: AwareDatetime = Field(default_factory=utc_now)


class CrossInvestorAssetAlignmentView(CrossInvestorAssetAlignmentCreate):
    id: UUID


class CrossInvestorAssetAlignmentResult(BaseModel):
    """Result of calculating one immutable alignment artifact."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    alignment_id: UUID
    asset_id: UUID
    source_snapshot_id: UUID
    alignment_policy_version: str = Field(min_length=1, max_length=64)
    created: bool


__all__ = [
    "CROSS_INVESTOR_ALIGNMENT_POLICY_VERSION",
    "CROSS_INVESTOR_DIRECTIONAL_ALIGNMENT_POLICY_VERSION",
    "CROSS_INVESTOR_POLICY_VERSION",
    "CrossInvestorAssetAlignmentCreate",
    "CrossInvestorAssetAlignmentResult",
    "CrossInvestorAssetAlignmentView",
    "CrossInvestorContribution",
    "CrossInvestorAssetSnapshotCreate",
    "CrossInvestorAssetSnapshotResult",
    "CrossInvestorAssetSnapshotView",
    "DirectionalAlignmentState",
    "OpinionCoverageState",
    "build_cross_investor_alignment_input_identity",
    "build_cross_investor_input_identity",
]
