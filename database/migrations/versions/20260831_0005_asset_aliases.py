"""Add canonical asset aliases for deterministic identity resolution.

Revision ID: 20260831_0005
Revises: 20260827_0004
Create Date: 2026-08-31
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260831_0005"
down_revision: str | None = "20260827_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "asset_aliases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("alias", sa.String(length=255), nullable=False),
        sa.Column("normalized_alias", sa.String(length=255), nullable=False),
        sa.Column("alias_type", sa.String(length=32), nullable=False),
        sa.Column("market", sa.String(length=32), nullable=True),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_asset_aliases_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_asset_aliases")),
        sa.UniqueConstraint(
            "asset_id",
            "normalized_alias",
            name="asset_alias_identity",
        ),
    )
    op.create_index(op.f("ix_asset_aliases_asset_id"), "asset_aliases", ["asset_id"], unique=False)
    op.create_index(
        op.f("ix_asset_aliases_normalized_alias"),
        "asset_aliases",
        ["normalized_alias"],
        unique=False,
    )
    op.create_index(op.f("ix_asset_aliases_market"), "asset_aliases", ["market"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_asset_aliases_market"), table_name="asset_aliases")
    op.drop_index(op.f("ix_asset_aliases_normalized_alias"), table_name="asset_aliases")
    op.drop_index(op.f("ix_asset_aliases_asset_id"), table_name="asset_aliases")
    op.drop_table("asset_aliases")
