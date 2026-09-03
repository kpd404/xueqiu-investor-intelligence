"""Create the Opinion × PortfolioAction consistency artifact table.

Revision ID: 20260904_0012
Revises: 20260904_0011
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0012"
down_revision: str | None = "20260904_0011"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "investor_action_consistencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("opinion_id", sa.Uuid(), nullable=False),
        sa.Column("opinion_direction", sa.String(length=32), nullable=True),
        sa.Column("portfolio_action_id", sa.Uuid(), nullable=False),
        sa.Column("action_type", sa.String(length=32), nullable=False),
        sa.Column("consistency_type", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("opinion_analysis_version", sa.String(length=255), nullable=False),
        sa.Column("consistency_policy_version", sa.String(length=64), nullable=False),
        sa.Column("input_identity", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_investor_action_consistencies_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_investor_action_consistencies_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opinion_id"],
            ["opinions.id"],
            name=op.f("fk_investor_action_consistencies_opinion_id_opinions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_action_id"],
            ["portfolio_actions.id"],
            name=op.f("fk_investor_action_consistencies_portfolio_action_id_portfolio_actions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investor_action_consistencies")),
        sa.UniqueConstraint(
            "input_identity",
            name="investor_action_consistency_input_identity",
        ),
    )
    for column in (
        "investor_id",
        "asset_id",
        "opinion_id",
        "portfolio_action_id",
        "effective_time",
    ):
        op.create_index(
            op.f(f"ix_investor_action_consistencies_{column}"),
            "investor_action_consistencies",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "effective_time",
        "portfolio_action_id",
        "opinion_id",
        "asset_id",
        "investor_id",
    ):
        op.drop_index(
            op.f(f"ix_investor_action_consistencies_{column}"),
            table_name="investor_action_consistencies",
        )
    op.drop_table("investor_action_consistencies")
