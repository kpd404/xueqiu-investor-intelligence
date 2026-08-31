"""Add derived attention occurrences.

Revision ID: 20260831_0006
Revises: 20260831_0005
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0006"
down_revision: str | None = "20260831_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "attention_occurrences",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("published_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("evidence_types", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("analysis_id", sa.Uuid(), nullable=True),
        sa.Column("opinion_id", sa.Uuid(), nullable=True),
        sa.Column("attention_policy_version", sa.String(length=64), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["analysis_id"],
            ["event_analyses.id"],
            name=op.f("fk_attention_occurrences_analysis_id_event_analyses"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_attention_occurrences_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["raw_events.id"],
            name=op.f("fk_attention_occurrences_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_attention_occurrences_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["opinion_id"],
            ["opinions.id"],
            name=op.f("fk_attention_occurrences_opinion_id_opinions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_attention_occurrences")),
        sa.UniqueConstraint(
            "event_id",
            "asset_id",
            "attention_policy_version",
            name="event_asset_attention_policy",
        ),
    )
    for column in (
        "investor_id",
        "asset_id",
        "event_id",
        "published_time",
        "analysis_id",
        "opinion_id",
    ):
        op.create_index(
            op.f(f"ix_attention_occurrences_{column}"),
            "attention_occurrences",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in (
        "opinion_id",
        "analysis_id",
        "published_time",
        "event_id",
        "asset_id",
        "investor_id",
    ):
        op.drop_index(
            op.f(f"ix_attention_occurrences_{column}"),
            table_name="attention_occurrences",
        )
    op.drop_table("attention_occurrences")
