"""Add analysis lifecycle, state change ledger, and temporal state fields.

Revision ID: 20260826_0003
Revises: 20260824_0002
Create Date: 2026-08-26
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision: str = "20260826_0003"
down_revision: str | None = "20260824_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "event_analyses",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("analysis_version", sa.String(length=255), nullable=False),
        sa.Column("model_version", sa.String(length=255), nullable=False),
        sa.Column("prompt_version", sa.String(length=255), nullable=False),
        sa.Column("schema_version", sa.String(length=255), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SUCCESS",
                "NO_OPINION",
                "PARTIALLY_RESOLVED",
                "FAILED",
                name="eventanalysisstatus",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("investment_related", sa.Boolean(), nullable=False),
        sa.Column("generated_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("structured_output", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=255), nullable=True),
        sa.ForeignKeyConstraint(
            ["event_id"],
            ["raw_events.id"],
            name=op.f("fk_event_analyses_event_id_raw_events"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_event_analyses")),
        sa.UniqueConstraint("event_id", "analysis_version", name="event_analysis_identity"),
    )
    op.create_index(
        op.f("ix_event_analyses_event_id"), "event_analyses", ["event_id"], unique=False
    )

    with op.batch_alter_table("opinions") as batch_op:
        batch_op.add_column(sa.Column("analysis_id", sa.Uuid(), nullable=True))
        batch_op.drop_constraint("event_asset_model", type_="unique")
        batch_op.create_unique_constraint(
            "event_asset_analysis", ["event_id", "asset_id", "analysis_id"]
        )
        batch_op.create_index(op.f("ix_opinions_analysis_id"), ["analysis_id"], unique=False)
        batch_op.create_foreign_key(
            op.f("fk_opinions_analysis_id_event_analyses"),
            "event_analyses",
            ["analysis_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    op.create_table(
        "investor_asset_state_changes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("investor_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column(
            "transition_type",
            sa.Enum(
                "NEW_ATTENTION",
                "OPINION_UPGRADE",
                "OPINION_DOWNGRADE",
                "OPINION_REVERSAL",
                "NO_MATERIAL_CHANGE",
                name="statetransitiontype",
                native_enum=False,
            ),
            nullable=False,
        ),
        sa.Column("effective_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before", sa.JSON(), nullable=True),
        sa.Column("after", sa.JSON(), nullable=False),
        sa.Column("triggering_opinion_id", sa.Uuid(), nullable=False),
        sa.Column("source_event_ids", sa.JSON(), nullable=False),
        sa.Column("state_policy_version", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["asset_id"],
            ["assets.id"],
            name=op.f("fk_investor_asset_state_changes_asset_id_assets"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["investor_id"],
            ["investors.id"],
            name=op.f("fk_investor_asset_state_changes_investor_id_investors"),
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["triggering_opinion_id"],
            ["opinions.id"],
            name=op.f("fk_investor_asset_state_changes_triggering_opinion_id_opinions"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investor_asset_state_changes")),
        sa.UniqueConstraint(
            "triggering_opinion_id",
            "state_policy_version",
            name="state_change_opinion_policy",
        ),
    )
    op.create_index(
        op.f("ix_investor_asset_state_changes_investor_id"),
        "investor_asset_state_changes",
        ["investor_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investor_asset_state_changes_asset_id"),
        "investor_asset_state_changes",
        ["asset_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investor_asset_state_changes_effective_time"),
        "investor_asset_state_changes",
        ["effective_time"],
        unique=False,
    )
    op.create_index(
        op.f("ix_investor_asset_state_changes_triggering_opinion_id"),
        "investor_asset_state_changes",
        ["triggering_opinion_id"],
        unique=False,
    )

    with op.batch_alter_table("investor_asset_states") as batch_op:
        batch_op.add_column(sa.Column("last_activity_time", sa.DateTime(timezone=True)))
        batch_op.add_column(sa.Column("last_material_change_time", sa.DateTime(timezone=True)))

    op.execute(
        "UPDATE investor_asset_states "
        "SET last_activity_time = last_opinion_time, "
        "last_material_change_time = last_change_time"
    )

    with op.batch_alter_table("investor_asset_states") as batch_op:
        batch_op.drop_column("last_opinion_time")
        batch_op.drop_column("last_change_time")


def downgrade() -> None:
    # A prior unpublished 0003 could have short index names or a partially
    # completed non-transactional SQLite downgrade. Handle both safely.
    state_columns = {
        column["name"] for column in inspect(op.get_bind()).get_columns("investor_asset_states")
    }
    if "last_opinion_time" not in state_columns:
        with op.batch_alter_table("investor_asset_states") as batch_op:
            batch_op.add_column(sa.Column("last_opinion_time", sa.DateTime(timezone=True)))
    if "last_change_time" not in state_columns:
        with op.batch_alter_table("investor_asset_states") as batch_op:
            batch_op.add_column(sa.Column("last_change_time", sa.DateTime(timezone=True)))

    state_columns = {
        column["name"] for column in inspect(op.get_bind()).get_columns("investor_asset_states")
    }
    if "last_activity_time" in state_columns:
        op.execute(
            "UPDATE investor_asset_states "
            "SET last_opinion_time = COALESCE(last_activity_time, last_opinion_time), "
            "last_change_time = COALESCE(last_material_change_time, last_change_time)"
        )
        with op.batch_alter_table("investor_asset_states") as batch_op:
            batch_op.drop_column("last_activity_time")
    if "last_material_change_time" in state_columns:
        with op.batch_alter_table("investor_asset_states") as batch_op:
            batch_op.drop_column("last_material_change_time")

    _drop_indexes_if_present(
        "investor_asset_state_changes",
        (
            "ix_investor_asset_state_changes_triggering_opinion_id",
            "ix_investor_asset_state_changes_effective_time",
            "ix_investor_asset_state_changes_asset_id",
            "ix_investor_asset_state_changes_investor_id",
            "ix_state_changes_triggering_opinion_id",
            "ix_state_changes_effective_time",
            "ix_state_changes_asset_id",
            "ix_state_changes_investor_id",
        ),
    )
    op.drop_table("investor_asset_state_changes")

    inspector = inspect(op.get_bind())
    opinion_constraints = {item["name"] for item in inspector.get_unique_constraints("opinions")}
    opinion_fks = {item["name"] for item in inspector.get_foreign_keys("opinions")}
    opinion_indexes = {item["name"] for item in inspector.get_indexes("opinions")}
    opinion_columns = {item["name"] for item in inspector.get_columns("opinions")}
    with op.batch_alter_table("opinions") as batch_op:
        fk_name = op.f("fk_opinions_analysis_id_event_analyses")
        if fk_name in opinion_fks:
            batch_op.drop_constraint(fk_name, type_="foreignkey")
        index_name = op.f("ix_opinions_analysis_id")
        if index_name in opinion_indexes:
            batch_op.drop_index(index_name)
        if "event_asset_analysis" in opinion_constraints:
            batch_op.drop_constraint("event_asset_analysis", type_="unique")
        if "event_asset_model" not in opinion_constraints:
            batch_op.create_unique_constraint(
                "event_asset_model", ["event_id", "asset_id", "model_version"]
            )
        if "analysis_id" in opinion_columns:
            batch_op.drop_column("analysis_id")

    _drop_indexes_if_present("event_analyses", (op.f("ix_event_analyses_event_id"),))
    op.drop_table("event_analyses")


def _drop_indexes_if_present(table_name: str, names: Sequence[str]) -> None:
    existing = {item["name"] for item in inspect(op.get_bind()).get_indexes(table_name)}
    for name in names:
        if name in existing:
            op.drop_index(name, table_name=table_name)
