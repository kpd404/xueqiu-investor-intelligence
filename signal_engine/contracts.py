from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, RootModel


class SignalEvidence(BaseModel):
    """One traceable fact supporting a research-priority signal."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    raw_event_id: UUID
    evidence_type: str = Field(min_length=1, pattern=r"^[A-Z][A-Z0-9_]*$")
    description: str = Field(min_length=1)


class SignalEvidenceCollection(RootModel[list[SignalEvidence]]):
    """Canonical JSON payload persisted in `Signal.reasons`."""
