from uuid import UUID

from pydantic import AliasChoices, AwareDatetime, BaseModel, ConfigDict, Field

from contracts.enums import AttentionLevel, ConsensusDirection, OpinionDirection
from contracts.state import InvestorAssetStateSnapshot


class InvestorStateAggregationInput(BaseModel):
    """State plus trusted provenance and investor quality used by pure policies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    state_id: UUID
    state: InvestorAssetStateSnapshot
    quality_score: float | None
    source_event_ids: tuple[UUID, ...]


class InvestorStateContribution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    state_id: UUID
    investor_id: UUID
    asset_id: UUID
    quality_score: float = Field(ge=0, le=100)
    weight: float = Field(ge=0, le=1)
    active: bool
    attention_level: AttentionLevel
    direction: OpinionDirection
    conviction: float = Field(ge=0, le=100)
    mention_count: int = Field(ge=1)
    last_activity_time: AwareDatetime = Field(
        validation_alias=AliasChoices("last_activity_time", "last_opinion_time")
    )
    source_event_ids: tuple[UUID, ...]

    @property
    def last_opinion_time(self) -> AwareDatetime:
        """Compatibility alias for pre-1F consumers."""

        return self.last_activity_time


class AssetIntelligenceSnapshot(BaseModel):
    """Non-persisted derived intelligence for one asset at a stated time."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: UUID
    as_of: AwareDatetime
    observed_investor_count: int = Field(ge=0)
    active_investor_count: int = Field(ge=0)
    bullish_count: int = Field(ge=0)
    neutral_count: int = Field(ge=0)
    bearish_count: int = Field(ge=0)
    weighted_bullish: float = Field(ge=0)
    weighted_neutral: float = Field(ge=0)
    weighted_bearish: float = Field(ge=0)
    consensus_direction: ConsensusDirection
    consensus_strength: float = Field(ge=0, le=100)
    investor_states: tuple[InvestorStateContribution, ...]
    source_event_ids: tuple[UUID, ...]
