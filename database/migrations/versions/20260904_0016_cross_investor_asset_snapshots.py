"""Create asset-centric Cross-Investor evidence snapshots.

Revision ID: 20260904_0016
Revises: 20260904_0015
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0016"
down_revision: str | None = "20260904_0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "cross_investor_asset_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("window_end", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attention_occurrence_count", sa.Integer(), nullable=False),
        sa.Column("attention_investor_count", sa.Integer(), nullable=False),
        sa.Column("new_attention_investor_count", sa.Integer(), nullable=False),
        sa.Column("opinion_count", sa.Integer(), nullable=False),
        sa.Column("opinion_investor_count", sa.Integer(), nullable=False),
        sa.Column("bullish_investor_count", sa.Integer(), nullable=False),
        sa.Column("bearish_investor_count", sa.Integer(), nullable=False),
        sa.Column("neutral_investor_count", sa.Integer(), nullable=False),
        sa.Column("thesis_change_count", sa.Integer(), nullable=False),
        sa.Column("thesis_change_investor_count", sa.Integer(), nullable=False),
        sa.Column("thesis_reinforced_investor_count", sa.Integer(), nullable=False),
        sa.Column("thesis_changed_investor_count", sa.Integer(), nullable=False),
        sa.Column("portfolio_action_count", sa.Integer(), nullable=False),
        sa.Column("portfolio_action_investor_count", sa.Integer(), nullable=False),
        sa.Column("position_increased_count", sa.Integer(), nullable=False),
        sa.Column("position_decreased_count", sa.Integer(), nullable=False),
        sa.Column("consistency_count", sa.Integer(), nullable=False),
        sa.Column("consistency_investor_count", sa.Integer(), nullable=False),
        sa.Column("positive_alignment_count", sa.Integer(), nullable=False),
        sa.Column("negative_alignment_count", sa.Integer(), nullable=False),
        sa.Column("contributions", sa.JSON(), nullable=False),
        sa.Column("opinion_analysis_version", sa.String(length=255), nullable=False),
        sa.Column("attention_policy_version", sa.String(length=64), nullable=False),
        sa.Column("thesis_comparison_version", sa.String(length=255), nullable=False),
        sa.Column("consistency_policy_version", sa.String(length=64), nullable=False),
        sa.Column("cross_investor_policy_version", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_identity", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_cross_investor_asset_snapshots_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_cross_investor_asset_snapshots")),
        sa.UniqueConstraint(
            "input_identity",
            name="cross_investor_asset_snapshot_input_identity",
        ),
    )
    for column in (
        "asset_id",
        "as_of",
        "window_start",
        "window_end",
        "calculated_at",
    ):
        op.create_index(
            op.f(f"ix_cross_investor_asset_snapshots_{column}"),
            "cross_investor_asset_snapshots",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_cross_investor_asset_snapshots_asset_window",
        "cross_investor_asset_snapshots",
        ["asset_id", "window_start", "window_end"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_cross_investor_asset_snapshots_asset_window",
        table_name="cross_investor_asset_snapshots",
    )
    for column in (
        "calculated_at",
        "window_end",
        "window_start",
        "as_of",
        "asset_id",
    ):
        op.drop_index(
            op.f(f"ix_cross_investor_asset_snapshots_{column}"),
            table_name="cross_investor_asset_snapshots",
        )
    op.drop_table("cross_investor_asset_snapshots")
