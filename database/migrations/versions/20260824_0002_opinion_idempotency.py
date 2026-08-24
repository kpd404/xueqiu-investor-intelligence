"""Guarantee opinion processing idempotency.

Revision ID: 20260824_0002
Revises: 20260821_0001
Create Date: 2026-08-24
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260824_0002"
down_revision: str | None = "20260821_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("opinions") as batch_op:
        batch_op.create_unique_constraint(
            "event_asset_model",
            ["event_id", "asset_id", "model_version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("opinions") as batch_op:
        batch_op.drop_constraint("event_asset_model", type_="unique")
