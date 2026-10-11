"""Persist explicit local Inbox progress only."""

import sqlalchemy as sa
from alembic import op

revision = "20261010_0026"
down_revision = "20261010_0025"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "inbox_user_states",
        sa.Column(
            "feed_id",
            sa.Uuid(),
            sa.ForeignKey("intelligence_feed_items.id", ondelete="RESTRICT"),
            primary_key=True,
        ),
        sa.Column("read", sa.Boolean(), nullable=False),
        sa.Column("processed", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("inbox_user_states")
