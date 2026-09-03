"""Add per-position identity indexes for idempotent snapshot imports.

Revision ID: 20260903_0009
Revises: 20260903_0008
Create Date: 2026-09-03
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0009"
down_revision: str | None = "20260903_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_index(
        "position_snapshot_resolved_identity",
        "position_snapshots",
        ["portfolio_id", "snapshot_time", "asset_id"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL"),
    )
    op.create_index(
        "position_snapshot_unresolved_identity",
        "position_snapshots",
        ["portfolio_id", "snapshot_time", "asset_reference_id"],
        unique=True,
        postgresql_where=sa.text("asset_reference_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("position_snapshot_unresolved_identity", table_name="position_snapshots")
    op.drop_index("position_snapshot_resolved_identity", table_name="position_snapshots")
