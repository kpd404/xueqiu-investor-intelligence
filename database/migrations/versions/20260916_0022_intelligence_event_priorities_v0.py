"""Add deterministic observation-priority rows for Intelligence Events."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0022"
down_revision: str | None = "20260916_0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_event_priorities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("priority_level", sa.String(length=16), nullable=False),
        sa.Column("reason", sa.String(length=64), nullable=False),
        sa.Column("evidence_count", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["intelligence_events.id"],
            name=op.f("fk_intelligence_event_priorities_event_id_intelligence_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intelligence_event_priorities")),
        sa.UniqueConstraint(
            "event_id",
            name="intelligence_event_priority_event_identity",
        ),
    )
    op.create_index(
        op.f("ix_intelligence_event_priorities_event_id"),
        "intelligence_event_priorities",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_event_priorities_created_at"),
        "intelligence_event_priorities",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_intelligence_event_priorities_level_reason",
        "intelligence_event_priorities",
        ["priority_level", "reason"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_intelligence_event_priorities_level_reason",
        table_name="intelligence_event_priorities",
    )
    op.drop_index(
        op.f("ix_intelligence_event_priorities_created_at"),
        table_name="intelligence_event_priorities",
    )
    op.drop_index(
        op.f("ix_intelligence_event_priorities_event_id"),
        table_name="intelligence_event_priorities",
    )
    op.drop_table("intelligence_event_priorities")
