"""Create the six MVP core entities.

Revision ID: 20260821_0001
Revises:
Create Date: 2026-08-21
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260821_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=False),
        sa.Column("industry", sa.String(length=255), nullable=True),
        sa.Column("themes", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_assets")),
        sa.UniqueConstraint("market", "symbol", name="market_symbol"),
    )
    op.create_table(
        "investors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=64), nullable=False),
        sa.Column("platform_user_id", sa.String(length=255), nullable=False),
        sa.Column("homepage_url", sa.String(length=2048), nullable=True),
        sa.Column("investment_style", sa.String(length=255), nullable=True),
        sa.Column("expertise_domains", sa.JSON(), nullable=False),
        sa.Column("quality_score", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investors")),
        sa.UniqueConstraint("platform", "platform_user_id", name="platform_identity"),
    )
    op.create_table(
        "raw_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column(
            "event_type",
            sa.Enum("POST", "ARTICLE", "PORTFOLIO_SNAPSHOT", name="eventtype", native_enum=False),
            nullable=False,
        ),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("url", sa.String(length=2048), nullable=False),
        sa.Column("published_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("raw_data", sa.JSON(), nullable=False),
        sa.Column("hash", sa.String(length=64), nullable=False),
        sa.Column("collected_time", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_raw_events_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_raw_events")),
    )
    op.create_index(op.f("ix_raw_events_hash"), "raw_events", ["hash"], unique=True)
    op.create_index(op.f("ix_raw_events_investor_id"), "raw_events", ["investor_id"])
    op.create_index(op.f("ix_raw_events_published_time"), "raw_events", ["published_time"])
    op.create_table(
        "investor_asset_states",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column(
            "attention_level",
            sa.Enum(
                "UNKNOWN",
                "DISCOVERED",
                "TRACKING",
                "FOCUS",
                "CORE_FOCUS",
                "ABANDONED",
                name="attentionlevel",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "direction",
            sa.Enum(
                "STRONG_BEARISH",
                "BEARISH",
                "NEUTRAL",
                "BULLISH",
                "STRONG_BULLISH",
                name="opiniondirection",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("conviction", sa.Float(), nullable=False),
        sa.Column("mention_count", sa.Integer(), nullable=False),
        sa.Column(
            "position_status",
            sa.Enum(
                "NO_POSITION",
                "WATCHING",
                "SMALL_POSITION",
                "CORE_POSITION",
                "REDUCING",
                "EXITED",
                name="positionstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("last_opinion_time", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_change_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_investor_asset_states_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_investor_asset_states_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investor_asset_states")),
        sa.UniqueConstraint("investor_id", "asset_id", name="investor_asset"),
    )
    op.create_index(
        op.f("ix_investor_asset_states_asset_id"), "investor_asset_states", ["asset_id"]
    )
    op.create_index(
        op.f("ix_investor_asset_states_investor_id"), "investor_asset_states", ["investor_id"]
    )
    op.create_table(
        "opinions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column(
            "direction",
            sa.Enum(
                "STRONG_BEARISH",
                "BEARISH",
                "NEUTRAL",
                "BULLISH",
                "STRONG_BULLISH",
                name="opiniondirection",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("strength", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("thesis", sa.JSON(), nullable=False),
        sa.Column("catalysts", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("time_horizon", sa.String(length=64), nullable=True),
        sa.Column("generated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_opinions_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["raw_events.id"],
            name=op.f("fk_opinions_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_opinions_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_opinions")),
    )
    op.create_index(op.f("ix_opinions_asset_id"), "opinions", ["asset_id"])
    op.create_index(op.f("ix_opinions_event_id"), "opinions", ["event_id"])
    op.create_index(op.f("ix_opinions_investor_id"), "opinions", ["investor_id"])
    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("signal_score", sa.Float(), nullable=False),
        sa.Column(
            "signal_level",
            sa.Enum(
                "STRONG_SIGNAL",
                "HIGH_PRIORITY_RESEARCH",
                "WATCH",
                "LOW_PRIORITY",
                name="signallevel",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("reasons", sa.JSON(), nullable=False),
        sa.Column("risks", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_signals_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
    )
    op.create_index(op.f("ix_signals_asset_id"), "signals", ["asset_id"])
    op.create_index(op.f("ix_signals_created_at"), "signals", ["created_at"])


def downgrade() -> None:
    op.drop_index(op.f("ix_signals_created_at"), table_name="signals")
    op.drop_index(op.f("ix_signals_asset_id"), table_name="signals")
    op.drop_table("signals")
    op.drop_index(op.f("ix_opinions_investor_id"), table_name="opinions")
    op.drop_index(op.f("ix_opinions_event_id"), table_name="opinions")
    op.drop_index(op.f("ix_opinions_asset_id"), table_name="opinions")
    op.drop_table("opinions")
    op.drop_index(op.f("ix_investor_asset_states_investor_id"), table_name="investor_asset_states")
    op.drop_index(op.f("ix_investor_asset_states_asset_id"), table_name="investor_asset_states")
    op.drop_table("investor_asset_states")
    op.drop_index(op.f("ix_raw_events_published_time"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_investor_id"), table_name="raw_events")
    op.drop_index(op.f("ix_raw_events_hash"), table_name="raw_events")
    op.drop_table("raw_events")
    op.drop_table("investors")
    op.drop_table("assets")
