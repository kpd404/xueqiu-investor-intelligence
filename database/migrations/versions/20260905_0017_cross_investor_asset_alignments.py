"""Create deterministic Cross-Investor coverage/alignment artifacts.

Revision ID: 20260905_0017
Revises: 20260904_0016
Create Date: 2026-09-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260905_0017"
down_revision: str | None = "20260904_0016"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_investor_asset_alignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("source_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("opinion_coverage_state", sa.String(length=32), nullable=False),
        sa.Column("directional_alignment_state", sa.String(length=32), nullable=False),
        sa.Column("alignment_policy_version", sa.String(length=64), nullable=False),
        sa.Column("input_identity", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_cross_investor_asset_alignments_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["source_snapshot_id"],
            ["cross_investor_asset_snapshots.id"],
            name=op.f(
                "fk_cross_investor_asset_alignments_source_snapshot_id_"
                "cross_investor_asset_snapshots"
            ),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cross_investor_asset_alignments")),
        sa.UniqueConstraint(
            "input_identity",
            name="cross_investor_asset_alignment_input_identity",
        ),
        sa.UniqueConstraint(
            "source_snapshot_id",
            "alignment_policy_version",
            name="cross_investor_asset_alignment_source_policy",
        ),
    )
    for column in ("asset_id", "source_snapshot_id", "calculated_at", "created_at"):
        op.create_index(
            op.f(f"ix_cross_investor_asset_alignments_{column}"),
            "cross_investor_asset_alignments",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_cross_investor_asset_alignments_asset_policy",
        "cross_investor_asset_alignments",
        ["asset_id", "alignment_policy_version"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cross_investor_asset_alignments_asset_policy",
        table_name="cross_investor_asset_alignments",
    )
    for column in ("created_at", "calculated_at", "source_snapshot_id", "asset_id"):
        op.drop_index(
            op.f(f"ix_cross_investor_asset_alignments_{column}"),
            table_name="cross_investor_asset_alignments",
        )
    op.drop_table("cross_investor_asset_alignments")
