from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from contracts.cross_investor import ConsensusEvidenceState, OpinionCoverageState
from database.base import Base
from database.models._types import utc_now


class CrossInvestorConsensusEvidence(Base):
    """Immutable deterministic Consensus/Divergence evidence for one Snapshot."""

    __tablename__ = "cross_investor_consensus_evidences"
    __table_args__ = (
        UniqueConstraint(
            "input_identity",
            name="cross_investor_consensus_evidence_input_identity",
        ),
        UniqueConstraint(
            "source_snapshot_id",
            "source_alignment_id",
            "consensus_policy_version",
            name="cross_investor_consensus_evidence_source_policy",
        ),
        Index(
            "ix_cross_investor_consensus_evidences_asset_policy",
            "asset_id",
            "consensus_policy_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    asset_id: Mapped[UUID] = mapped_column(
        ForeignKey("assets.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    source_snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("cross_investor_asset_snapshots.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    source_alignment_id: Mapped[UUID] = mapped_column(
        ForeignKey("cross_investor_asset_alignments.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )

    attention_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    opinion_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bullish_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    bearish_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    neutral_investor_count: Mapped[int] = mapped_column(Integer, nullable=False)
    opinion_coverage_state: Mapped[OpinionCoverageState] = mapped_column(
        String(32),
        nullable=False,
    )
    consensus_state: Mapped[ConsensusEvidenceState] = mapped_column(
        String(32),
        nullable=False,
    )
    contributing_investor_ids: Mapped[list[str]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    latest_opinions: Mapped[list[dict[str, object]]] = mapped_column(
        JSON,
        default=list,
        nullable=False,
    )
    consensus_policy_version: Mapped[str] = mapped_column(String(64), nullable=False)
    input_identity: Mapped[str] = mapped_column(String(64), nullable=False)
    calculated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        index=True,
        default=utc_now,
        nullable=False,
    )
