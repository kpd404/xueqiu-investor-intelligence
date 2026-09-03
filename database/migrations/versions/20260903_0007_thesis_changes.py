"""Add versioned thesis change artifacts.

Revision ID: 20260903_0007
Revises: 20260831_0006
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0007"
down_revision: str | None = "20260831_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "thesis_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("previous_opinion_id", sa.Uuid(), nullable=True),
        sa.Column("current_opinion_id", sa.Uuid(), nullable=False),
        sa.Column("previous_event_id", sa.Uuid(), nullable=True),
        sa.Column("current_event_id", sa.Uuid(), nullable=False),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "change_type",
            sa.Enum(
                "NEW_THESIS",
                "THESIS_UNCHANGED",
                "THESIS_REINFORCED",
                "THESIS_EXTENDED",
                "THESIS_CHANGED",
                "INSUFFICIENT_EVIDENCE",
                name="thesischangetype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("opinion_analysis_version", sa.String(length=255), nullable=False),
        sa.Column("comparison_version", sa.String(length=255), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("input_identity", sa.String(length=512), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_thesis_changes_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_event_id"],
            ["raw_events.id"],
            name=op.f("fk_thesis_changes_current_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["current_opinion_id"],
            ["opinions.id"],
            name=op.f("fk_thesis_changes_current_opinion_id_opinions"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_thesis_changes_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_event_id"],
            ["raw_events.id"],
            name=op.f("fk_thesis_changes_previous_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["previous_opinion_id"],
            ["opinions.id"],
            name=op.f("fk_thesis_changes_previous_opinion_id_opinions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_thesis_changes")),
        sa.UniqueConstraint(
            "input_identity",
            name="thesis_change_input_identity",
        ),
    )
    for column in (
        "investor_id",
        "asset_id",
        "previous_opinion_id",
        "current_opinion_id",
        "previous_event_id",
        "current_event_id",
        "effective_time",
    ):
        op.create_index(
            op.f(f"ix_thesis_changes_{column}"),
            "thesis_changes",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "effective_time",
        "current_event_id",
        "previous_event_id",
        "current_opinion_id",
        "previous_opinion_id",
        "asset_id",
        "investor_id",
    ):
        op.drop_index(op.f(f"ix_thesis_changes_{column}"), table_name="thesis_changes")
    op.drop_table("thesis_changes")
