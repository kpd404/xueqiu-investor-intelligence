from enum import StrEnum
from uuid import UUID

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field, model_validator

from contracts.enums import AttentionLevel, OpinionDirection, PositionStatus


class OpinionTimelineEntry(BaseModel):
    """One traceable interpretation paired with its source event time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    opinion_id: UUID
    event_id: UUID
    investor_id: UUID
    asset_id: UUID
    direction: OpinionDirection
    strength: float = Field(ge=0, le=100)
    confidence: float = Field(ge=0, le=1)
    published_time: AwareDatetime
    generated_time: AwareDatetime


class InvestorAssetStateSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    investor_id: UUID
    asset_id: UUID
    attention_level: AttentionLevel
    direction: OpinionDirection
    conviction: float = Field(ge=0, le=100)
    mention_count: int = Field(ge=0)
    position_status: PositionStatus
    last_activity_time: AwareDatetime | None = Field(
        default=None,
        validation_alias=AliasChoices("last_activity_time", "last_opinion_time"),
    )
    last_material_change_time: AwareDatetime | None = Field(
        default=None,
        validation_alias=AliasChoices("last_material_change_time", "last_change_time"),
    )

    @property
    def last_opinion_time(self) -> AwareDatetime | None:
        """Compatibility alias for pre-1F callers; not a persisted field."""

        return self.last_activity_time

    @property
    def last_change_time(self) -> AwareDatetime | None:
        """Compatibility alias for pre-1F callers; not a persisted field."""

        return self.last_material_change_time


class StateTransitionType(StrEnum):
    NEW_ATTENTION = "NEW_ATTENTION"
    OPINION_UPGRADE = "OPINION_UPGRADE"
    OPINION_DOWNGRADE = "OPINION_DOWNGRADE"
    OPINION_REVERSAL = "OPINION_REVERSAL"
    NO_MATERIAL_CHANGE = "NO_MATERIAL_CHANGE"


class StateReduction(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    projection_changed: bool
    material_change: bool
    before: InvestorAssetStateSnapshot | None
    after: InvestorAssetStateSnapshot
    transition: StateTransitionType
    applied_opinion_ids: tuple[UUID, ...]
    source_event_ids: tuple[UUID, ...]

    @property
    def changed(self) -> bool:
        """Compatibility alias for the pre-1F projection change flag."""

        return self.projection_changed


class StateUpdateResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state_id: UUID
    projection_changed: bool
    material_change: bool = False
    before: InvestorAssetStateSnapshot | None
    after: InvestorAssetStateSnapshot
    transition: StateTransitionType
    applied_opinion_ids: tuple[UUID, ...]
    source_event_ids: tuple[UUID, ...]
    state_change_id: UUID | None = None

    @model_validator(mode="before")
    @classmethod
    def accept_legacy_changed_field(cls, value: object) -> object:
        if isinstance(value, dict) and "changed" in value:
            normalized = dict(value)
            normalized.setdefault("projection_changed", normalized["changed"])
            normalized.pop("changed", None)
            return normalized
        return value

    @property
    def changed(self) -> bool:
        """Compatibility alias for the pre-1F projection change flag."""

        return self.projection_changed


STATE_POLICY_VERSION = "state-v1"
