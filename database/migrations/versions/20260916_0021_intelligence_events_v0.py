"""Add deterministic Signal aggregation event tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0021"
down_revision: str | None = "20260916_0020"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "intelligence_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_intelligence_events_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intelligence_events")),
        sa.UniqueConstraint("event_type", "asset_id", name="intelligence_event_identity"),
    )
    op.create_index(
        op.f("ix_intelligence_events_asset_id"),
        "intelligence_events",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_events_first_observed_at"),
        "intelligence_events",
        ["first_observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_events_last_observed_at"),
        "intelligence_events",
        ["last_observed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_events_created_at"),
        "intelligence_events",
        ["created_at"],
        unique=False,
    )
    op.create_index(
        "ix_intelligence_events_asset_observed_at",
        "intelligence_events",
        ["asset_id", "last_observed_at"],
        unique=False,
    )

    op.create_table(
        "intelligence_event_evidence",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["intelligence_events.id"],
            name=op.f("fk_intelligence_event_evidence_event_id_intelligence_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["signal_id"],
            ["signals.id"],
            name=op.f("fk_intelligence_event_evidence_signal_id_signals"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intelligence_event_evidence")),
        sa.UniqueConstraint(
            "event_id",
            "signal_id",
            name="intelligence_event_evidence_identity",
        ),
    )
    op.create_index(
        op.f("ix_intelligence_event_evidence_event_id"),
        "intelligence_event_evidence",
        ["event_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_intelligence_event_evidence_signal_id"),
        "intelligence_event_evidence",
        ["signal_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_intelligence_event_evidence_signal_id"),
        table_name="intelligence_event_evidence",
    )
    op.drop_index(
        op.f("ix_intelligence_event_evidence_event_id"),
        table_name="intelligence_event_evidence",
    )
    op.drop_table("intelligence_event_evidence")
    op.drop_index(
        "ix_intelligence_events_asset_observed_at",
        table_name="intelligence_events",
    )
    for column in (
        "created_at",
        "last_observed_at",
        "first_observed_at",
        "asset_id",
    ):
        op.drop_index(
            op.f(f"ix_intelligence_events_{column}"),
            table_name="intelligence_events",
        )
    op.drop_table("intelligence_events")
