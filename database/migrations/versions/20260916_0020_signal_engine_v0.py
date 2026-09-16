"""Replace the legacy score-oriented Signal table with Signal evidence V0."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260916_0020"
down_revision: str | None = "20260914_0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _assert_empty(table_name: str, message: str) -> None:
    bind = op.get_bind()
    count = bind.execute(sa.text(f"SELECT COUNT(*) FROM {table_name}")).scalar_one()
    if count:
        raise RuntimeError(f"{message}; refusing destructive Signal migration ({count} rows)")


def upgrade() -> None:
    # The initial schema shipped an empty score-oriented `signals` table.  Do
    # not reinterpret or discard legacy rows if a non-empty database is found.
    _assert_empty("signals", "legacy signals table is not empty")
    op.drop_index(op.f("ix_signals_created_at"), table_name="signals")
    op.drop_index(op.f("ix_signals_asset_id"), table_name="signals")
    op.drop_table("signals")

    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=True),
        sa.Column("signal_type", sa.String(length=64), nullable=False),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("source_type", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_signals_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_signals_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
        sa.UniqueConstraint("signal_type", "source_id", name="signal_source_identity"),
    )
    op.create_index(op.f("ix_signals_asset_id"), "signals", ["asset_id"], unique=False)
    op.create_index(op.f("ix_signals_investor_id"), "signals", ["investor_id"], unique=False)
    op.create_index(op.f("ix_signals_created_at"), "signals", ["created_at"], unique=False)
    op.create_index(op.f("ix_signals_observed_at"), "signals", ["observed_at"], unique=False)
    op.create_index(
        "ix_signals_asset_observed_at",
        "signals",
        ["asset_id", "observed_at"],
        unique=False,
    )
    op.create_index(
        "ix_signals_source",
        "signals",
        ["source_type", "source_id"],
        unique=False,
    )


def downgrade() -> None:
    _assert_empty("signals", "Signal V0 table is not empty")
    for index_name in (
        "ix_signals_source",
        "ix_signals_asset_observed_at",
        "ix_signals_observed_at",
        "ix_signals_created_at",
        "ix_signals_investor_id",
        "ix_signals_asset_id",
    ):
        op.drop_index(index_name, table_name="signals")
    op.drop_table("signals")

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
    op.create_index(op.f("ix_signals_asset_id"), "signals", ["asset_id"], unique=False)
    op.create_index(op.f("ix_signals_created_at"), "signals", ["created_at"], unique=False)
