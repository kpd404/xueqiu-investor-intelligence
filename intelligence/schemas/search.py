"""HTTP-friendly search response contract for the Query Layer."""

from pydantic import BaseModel, ConfigDict, Field

from intelligence.schemas.intelligence import IntelligenceSearchEntity


class IntelligenceSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    query: str = Field(min_length=1)
    items: tuple[IntelligenceSearchEntity, ...] = ()


__all__ = ["IntelligenceSearchResponse"]
