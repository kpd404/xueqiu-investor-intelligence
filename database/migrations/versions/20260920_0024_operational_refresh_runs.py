"""Persist full operational refresh execution metadata."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260920_0024"
down_revision: str | None = "20260916_0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operational_refresh_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("trigger", sa.String(length=16), nullable=False),
        sa.Column("failure_stage", sa.String(length=64), nullable=True),
        sa.Column("failure_code", sa.String(length=128), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name=op.f("ck_operational_refresh_run_finished_after_started"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_operational_refresh_runs")),
    )
    op.create_index(
        op.f("ix_operational_refresh_runs_started_at"),
        "operational_refresh_runs",
        ["started_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_refresh_runs_status"),
        "operational_refresh_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_operational_refresh_runs_trigger"),
        "operational_refresh_runs",
        ["trigger"],
        unique=False,
    )
    op.create_index(
        "ix_operational_refresh_runs_status_started",
        "operational_refresh_runs",
        ["status", "started_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_refresh_runs_status_started",
        table_name="operational_refresh_runs",
    )
    for column in ("trigger", "status", "started_at"):
        op.drop_index(
            op.f(f"ix_operational_refresh_runs_{column}"),
            table_name="operational_refresh_runs",
        )
    op.drop_table("operational_refresh_runs")
