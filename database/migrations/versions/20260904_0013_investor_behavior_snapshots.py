"""Create Investor Behavior Snapshot aggregation artifacts.

Revision ID: 20260904_0013
Revises: 20260904_0012
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0013"
down_revision: str | None = "20260904_0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investor_behavior_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attention_asset_count", sa.Integer(), nullable=False),
        sa.Column("attention_occurrence_count", sa.Integer(), nullable=False),
        sa.Column("new_attention_count", sa.Integer(), nullable=False),
        sa.Column("opinion_count", sa.Integer(), nullable=False),
        sa.Column("bullish_count", sa.Integer(), nullable=False),
        sa.Column("bearish_count", sa.Integer(), nullable=False),
        sa.Column("thesis_change_count", sa.Integer(), nullable=False),
        sa.Column("thesis_reinforced_count", sa.Integer(), nullable=False),
        sa.Column("thesis_changed_count", sa.Integer(), nullable=False),
        sa.Column("portfolio_action_count", sa.Integer(), nullable=False),
        sa.Column("position_increased_count", sa.Integer(), nullable=False),
        sa.Column("position_decreased_count", sa.Integer(), nullable=False),
        sa.Column("positive_alignment_count", sa.Integer(), nullable=False),
        sa.Column("negative_alignment_count", sa.Integer(), nullable=False),
        sa.Column("behavior_policy_version", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_identity", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_investor_behavior_snapshots_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investor_behavior_snapshots")),
        sa.UniqueConstraint(
            "investor_id",
            "window_start",
            "window_end",
            "behavior_policy_version",
            name="investor_behavior_snapshot_identity",
        ),
    )
    for column in (
        "investor_id",
        "as_of",
        "window_start",
        "window_end",
        "calculated_at",
    ):
        op.create_index(
            op.f(f"ix_investor_behavior_snapshots_{column}"),
            "investor_behavior_snapshots",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "calculated_at",
        "window_end",
        "window_start",
        "as_of",
        "investor_id",
    ):
        op.drop_index(
            op.f(f"ix_investor_behavior_snapshots_{column}"),
            table_name="investor_behavior_snapshots",
        )
    op.drop_table("investor_behavior_snapshots")
