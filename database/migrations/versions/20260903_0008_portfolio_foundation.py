"""Create the independent Portfolio Fact foundation tables.

Revision ID: 20260903_0008
Revises: 20260903_0007
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0008"
down_revision: str | None = "20260903_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "ACTIVE",
                "INACTIVE",
                "UNKNOWN",
                name="portfoliostatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_portfolio_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio")),
        sa.UniqueConstraint("source", "external_id", name="portfolio_source_external"),
    )
    op.create_index(op.f("ix_portfolio_investor_id"), "portfolio", ["investor_id"])

    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("asset_reference_id", sa.Uuid(), nullable=True),
        sa.Column("weight", sa.Float(), nullable=True),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_reference", sa.String(length=2048), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "(asset_id IS NOT NULL AND asset_reference_id IS NULL) OR "
            "(asset_id IS NULL AND asset_reference_id IS NOT NULL)",
            name="position_snapshot_asset_identity",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_position_snapshots_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name=op.f("fk_position_snapshots_portfolio_id_portfolio"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_position_snapshots")),
    )
    for column in ("portfolio_id", "asset_id", "asset_reference_id", "snapshot_time"):
        op.create_index(
            op.f(f"ix_position_snapshots_{column}"),
            "position_snapshots",
            [column],
            unique=False,
        )

    op.create_table(
        "portfolio_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("previous_snapshot_id", sa.Uuid(), nullable=True),
        sa.Column("current_snapshot_id", sa.Uuid(), nullable=False),
        sa.Column(
            "action_type",
            sa.Enum(
                "NEW_POSITION",
                "INCREASE",
                "DECREASE",
                "EXIT",
                "UNCHANGED",
                name="portfolioactiontype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_portfolio_actions_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_snapshot_id"],
            ["position_snapshots.id"],
            name=op.f("fk_portfolio_actions_current_snapshot_id_position_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name=op.f("fk_portfolio_actions_portfolio_id_portfolio"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_snapshot_id"],
            ["position_snapshots.id"],
            name=op.f("fk_portfolio_actions_previous_snapshot_id_position_snapshots"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_actions")),
        sa.UniqueConstraint("current_snapshot_id", name="portfolio_action_current_snapshot"),
    )
    for column in (
        "portfolio_id",
        "asset_id",
        "previous_snapshot_id",
        "current_snapshot_id",
        "effective_time",
    ):
        op.create_index(
            op.f(f"ix_portfolio_actions_{column}"),
            "portfolio_actions",
            [column],
            unique=False,
        )

    op.create_table(
        "investor_action_claims",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=True),
        sa.Column("asset_reference_id", sa.Uuid(), nullable=True),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column(
            "claim_type",
            sa.Enum(
                "BUY",
                "ADD_POSITION",
                "REDUCE_POSITION",
                "SELL",
                "HOLD",
                "UNKNOWN",
                name="investoractionclaimtype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("evidence_text", sa.Text(), nullable=False),
        sa.Column("published_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("analysis_version", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "NOT (asset_id IS NOT NULL AND asset_reference_id IS NOT NULL)",
            name="investor_action_claim_asset_identity",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_investor_action_claims_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["raw_events.id"],
            name=op.f("fk_investor_action_claims_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_investor_action_claims_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investor_action_claims")),
    )
    for column in ("investor_id", "asset_id", "asset_reference_id", "event_id", "published_time"):
        op.create_index(
            op.f(f"ix_investor_action_claims_{column}"),
            "investor_action_claims",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("published_time", "event_id", "asset_reference_id", "asset_id", "investor_id"):
        op.drop_index(
            op.f(f"ix_investor_action_claims_{column}"), table_name="investor_action_claims"
        )
    op.drop_table("investor_action_claims")

    for column in (
        "effective_time",
        "current_snapshot_id",
        "previous_snapshot_id",
        "asset_id",
        "portfolio_id",
    ):
        op.drop_index(op.f(f"ix_portfolio_actions_{column}"), table_name="portfolio_actions")
    op.drop_table("portfolio_actions")

    for column in ("snapshot_time", "asset_reference_id", "asset_id", "portfolio_id"):
        op.drop_index(op.f(f"ix_position_snapshots_{column}"), table_name="position_snapshots")
    op.drop_table("position_snapshots")

    op.drop_index(op.f("ix_portfolio_investor_id"), table_name="portfolio")
    op.drop_table("portfolio")
