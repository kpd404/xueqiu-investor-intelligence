"""Create immutable Cross-Investor Consensus/Divergence evidence."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260910_0018"
down_revision: str | None = "20260905_0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_investor_consensus_evidences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_alignment_id", sa.Uuid(), nullable=False),
        sa.Column("attention_investor_count", sa.Integer(), nullable=False),
        sa.Column("opinion_investor_count", sa.Integer(), nullable=False),
        sa.Column("bullish_investor_count", sa.Integer(), nullable=False),
        sa.Column("bearish_investor_count", sa.Integer(), nullable=False),
        sa.Column("neutral_investor_count", sa.Integer(), nullable=False),
        sa.Column("opinion_coverage_state", sa.String(length=32), nullable=False),
        sa.Column("consensus_state", sa.String(length=32), nullable=False),
        sa.Column("contributing_investor_ids", sa.JSON(), nullable=False),
        sa.Column("latest_opinions", sa.JSON(), nullable=False),
        sa.Column("consensus_policy_version", sa.String(length=64), nullable=False),
        sa.Column("input_identity", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_cross_investor_consensus_evidences_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["cross_investor_asset_snapshots.id"],
            name=op.f(
                "fk_cross_investor_consensus_evidences_source_snapshot_id_"
                "cross_investor_asset_snapshots"
            ),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_alignment_id"],
            ["cross_investor_asset_alignments.id"],
            name=op.f(
                "fk_cross_investor_consensus_evidences_source_alignment_id_"
                "cross_investor_asset_alignments"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cross_investor_consensus_evidences")),
        sa.UniqueConstraint(
            "input_identity",
            name="cross_investor_consensus_evidence_input_identity",
        ),
        sa.UniqueConstraint(
            "source_snapshot_id",
            "source_alignment_id",
            "consensus_policy_version",
            name="cross_investor_consensus_evidence_source_policy",
        ),
    )
    for column in (
        "asset_id",
        "source_snapshot_id",
        "source_alignment_id",
        "calculated_at",
        "created_at",
    ):
        op.create_index(
            op.f(f"ix_cross_investor_consensus_evidences_{column}"),
            "cross_investor_consensus_evidences",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_cross_investor_consensus_evidences_asset_policy",
        "cross_investor_consensus_evidences",
        ["asset_id", "consensus_policy_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cross_investor_consensus_evidences_asset_policy",
        table_name="cross_investor_consensus_evidences",
    )
    for column in (
        "created_at",
        "calculated_at",
        "source_alignment_id",
        "source_snapshot_id",
        "asset_id",
    ):
        op.drop_index(
            op.f(f"ix_cross_investor_consensus_evidences_{column}"),
            table_name="cross_investor_consensus_evidences",
        )
    op.drop_table("cross_investor_consensus_evidences")
