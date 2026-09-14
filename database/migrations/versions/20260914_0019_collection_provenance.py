"""Add source-independent collection provenance tables."""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260914_0019"
down_revision: str | None = "20260910_0018"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "collection_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("adapter_name", sa.String(length=128), nullable=False),
        sa.Column("collection_mode", sa.String(length=32), nullable=False),
        sa.Column("transport", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("run_status", sa.String(length=32), nullable=False),
        sa.Column("stop_reason", sa.String(length=128), nullable=True),
        sa.Column("coverage_status", sa.String(length=32), nullable=False),
        sa.Column("requested_window_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requested_window_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column("scope_type", sa.String(length=128), nullable=True),
        sa.Column("scope_key", sa.String(length=255), nullable=True),
        sa.Column("collector_version", sa.String(length=128), nullable=True),
        sa.Column("parameters_json", sa.JSON(), nullable=True),
        sa.Column("summary_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "ended_at IS NULL OR ended_at >= started_at",
            name=op.f("ck_collection_runs_collection_run_ended_after_started"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_runs")),
    )
    for column in (
        "source",
        "collection_mode",
        "transport",
        "run_status",
        "coverage_status",
        "started_at",
    ):
        op.create_index(
            op.f(f"ix_collection_runs_{column}"),
            "collection_runs",
            [column],
            unique=False,
        )
    op.create_index(
        "ix_collection_runs_source_mode",
        "collection_runs",
        ["source", "collection_mode"],
        unique=False,
    )

    op.create_table(
        "collection_observations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("collection_run_id", sa.Uuid(), nullable=False),
        sa.Column("raw_event_id", sa.Uuid(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ingest_disposition", sa.String(length=32), nullable=False),
        sa.Column("observation_sequence", sa.Integer(), nullable=True),
        sa.Column("source_page", sa.String(length=2048), nullable=True),
        sa.Column("source_context_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_run_id"],
            ["collection_runs.id"],
            name=op.f("fk_collection_observations_collection_run_id_collection_runs"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["raw_event_id"],
            ["raw_events.id"],
            name=op.f("fk_collection_observations_raw_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_observations")),
        sa.UniqueConstraint(
            "collection_run_id",
            "raw_event_id",
            name="collection_observation_run_event",
        ),
    )
    for column in ("collection_run_id", "raw_event_id", "observed_at"):
        op.create_index(
            op.f(f"ix_collection_observations_{column}"),
            "collection_observations",
            [column],
            unique=False,
        )


def downgrade() -> None:
    for column in ("observed_at", "raw_event_id", "collection_run_id"):
        op.drop_index(
            op.f(f"ix_collection_observations_{column}"),
            table_name="collection_observations",
        )
    op.drop_table("collection_observations")
    op.drop_index("ix_collection_runs_source_mode", table_name="collection_runs")
    for column in (
        "started_at",
        "coverage_status",
        "run_status",
        "transport",
        "collection_mode",
        "source",
    ):
        op.drop_index(op.f(f"ix_collection_runs_{column}"), table_name="collection_runs")
    op.drop_table("collection_runs")
