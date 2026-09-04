"""Harden effective derived artifact and snapshot provenance semantics.

Revision ID: 20260904_0014
Revises: 20260904_0013
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0014"
down_revision: str | None = "20260904_0013"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("portfolio_snapshot_batches") as batch_op:
        batch_op.add_column(
            sa.Column(
                "completeness",
                sa.String(length=16),
                nullable=False,
                server_default="FULL",
            )
        )
        batch_op.alter_column("completeness", server_default=None)

    with op.batch_alter_table("portfolio_actions") as batch_op:
        batch_op.alter_column(
            "action_type",
            existing_type=sa.String(length=19),
            type_=sa.String(length=32),
            existing_nullable=False,
        )

    op.drop_constraint(
        "investor_behavior_snapshot_identity",
        "investor_behavior_snapshots",
        type_="unique",
    )
    with op.batch_alter_table("investor_behavior_snapshots") as batch_op:
        batch_op.add_column(
            sa.Column(
                "active_analysis_version",
                sa.String(length=255),
                nullable=False,
                server_default="legacy:unspecified",
            )
        )
        batch_op.add_column(sa.Column("thesis_comparison_version", sa.String(length=255)))
        batch_op.add_column(sa.Column("consistency_policy_version", sa.String(length=64)))
        batch_op.alter_column("active_analysis_version", server_default=None)
    op.create_unique_constraint(
        "investor_behavior_snapshot_input_identity",
        "investor_behavior_snapshots",
        ["input_identity"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "investor_behavior_snapshot_input_identity",
        "investor_behavior_snapshots",
        type_="unique",
    )
    with op.batch_alter_table("investor_behavior_snapshots") as batch_op:
        batch_op.drop_column("consistency_policy_version")
        batch_op.drop_column("thesis_comparison_version")
        batch_op.drop_column("active_analysis_version")
    op.create_unique_constraint(
        "investor_behavior_snapshot_identity",
        "investor_behavior_snapshots",
        ["investor_id", "window_start", "window_end", "behavior_policy_version"],
    )

    with op.batch_alter_table("portfolio_actions") as batch_op:
        batch_op.alter_column(
            "action_type",
            existing_type=sa.String(length=32),
            type_=sa.String(length=19),
            existing_nullable=False,
        )

    with op.batch_alter_table("portfolio_snapshot_batches") as batch_op:
        batch_op.drop_column("completeness")
