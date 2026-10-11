"""Persist explicitly selected user research records; no source projection changes."""

import sqlalchemy as sa
from alembic import op

revision = "20261010_0025"
down_revision = "20260920_0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "research_candidates",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "asset_id", sa.Uuid(), sa.ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("status", sa.String(16), nullable=False),
        *(sa.Column(name, sa.Text(), nullable=False) for name in ("reason", "questions", "notes")),
        sa.Column("references", sa.JSON(), nullable=False),
        sa.Column("submission_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('TODO','RESEARCHING','ARCHIVED')", name="research_candidate_status"
        ),
    )
    op.create_index(
        "research_candidate_open_asset",
        "research_candidates",
        ["asset_id"],
        unique=True,
        sqlite_where=sa.text("status != 'ARCHIVED'"),
        postgresql_where=sa.text("status != 'ARCHIVED'"),
    )


def downgrade():
    op.drop_index("research_candidate_open_asset", table_name="research_candidates")
    op.drop_table("research_candidates")
