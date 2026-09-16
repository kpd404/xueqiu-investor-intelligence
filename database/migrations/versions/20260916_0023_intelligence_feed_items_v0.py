"""Add the read-side Intelligence Feed projection table."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0023"
down_revision: str | None = "20260916_0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_feed_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("priority_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("context", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["priority_id"],
            ["intelligence_event_priorities.id"],
            name=op.f("fk_intelligence_feed_items_priority_id_intelligence_event_priorities"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_intelligence_feed_items_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intelligence_feed_items")),
        sa.UniqueConstraint(
            "priority_id",
            name="intelligence_feed_item_priority_identity",
        ),
    )
    op.create_index(
        op.f("ix_intelligence_feed_items_priority_id"),
        "intelligence_feed_items",
        ["priority_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_feed_items_asset_id"),
        "intelligence_feed_items",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_feed_items_observed_at"),
        "intelligence_feed_items",
        ["observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_feed_items_created_at"),
        "intelligence_feed_items",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_intelligence_feed_items_asset_observed_at",
        "intelligence_feed_items",
        ["asset_id", "observed_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_feed_items_asset_observed_at",
        table_name="intelligence_feed_items",
    )
    for column in ("created_at", "observed_at", "asset_id", "priority_id"):
        op.drop_index(
            op.f(f"ix_intelligence_feed_items_{column}"),
            table_name="intelligence_feed_items",
        )
    op.drop_table("intelligence_feed_items")
