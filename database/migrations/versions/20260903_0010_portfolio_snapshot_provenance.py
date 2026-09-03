"""Add explicit PortfolioSnapshotBatch provenance to position facts.

Revision ID: 20260903_0010
Revises: 20260903_0009
Create Date: 2026-09-03
"""

from collections.abc import Sequence
from datetime import UTC, datetime
from uuid import uuid4

import sqlalchemy as sa
from alembic import op

revision: str = "20260903_0010"
down_revision: str | None = "20260903_0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "portfolio_snapshot_batches",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_id", sa.Uuid(), nullable=False),
        sa.Column("snapshot_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source", sa.String(length=64), nullable=False),
        sa.Column("external_id", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["portfolio_id"],
            ["portfolio.id"],
            name=op.f("fk_portfolio_snapshot_batches_portfolio_id_portfolio"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_portfolio_snapshot_batches")),
        sa.UniqueConstraint(
            "portfolio_id",
            "snapshot_time",
            "source",
            "external_id",
            name="portfolio_snapshot_batch_identity",
        ),
    )
    op.create_index(
        op.f("ix_portfolio_snapshot_batches_portfolio_id"),
        "portfolio_snapshot_batches",
        ["portfolio_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_portfolio_snapshot_batches_snapshot_time"),
        "portfolio_snapshot_batches",
        ["snapshot_time"],
        unique=False,
    )

    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.add_column(sa.Column("snapshot_batch_id", sa.Uuid(), nullable=True))

    connection = op.get_bind()
    existing_batches = connection.execute(
        sa.text(
            """
            SELECT DISTINCT ps.portfolio_id, ps.snapshot_time, p.source, p.external_id
            FROM position_snapshots AS ps
            JOIN portfolio AS p ON p.id = ps.portfolio_id
            """
        )
    ).mappings()
    for row in existing_batches:
        batch_id = uuid4()
        connection.execute(
            sa.text(
                """
                INSERT INTO portfolio_snapshot_batches
                    (id, portfolio_id, snapshot_time, source, external_id, created_at)
                VALUES (:id, :portfolio_id, :snapshot_time, :source, :external_id, :created_at)
                """
            ),
            {
                "id": batch_id,
                "portfolio_id": row["portfolio_id"],
                "snapshot_time": row["snapshot_time"],
                "source": row["source"],
                "external_id": row["external_id"],
                "created_at": datetime.now(UTC),
            },
        )
        connection.execute(
            sa.text(
                """
                UPDATE position_snapshots
                SET snapshot_batch_id = :batch_id
                WHERE portfolio_id = :portfolio_id AND snapshot_time = :snapshot_time
                """
            ),
            {
                "batch_id": batch_id,
                "portfolio_id": row["portfolio_id"],
                "snapshot_time": row["snapshot_time"],
            },
        )

    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_position_snapshots_snapshot_batch_id_portfolio_snapshot_batches"),
            "portfolio_snapshot_batches",
            ["snapshot_batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.alter_column("snapshot_batch_id", existing_type=sa.Uuid(), nullable=False)

    op.create_index(
        op.f("ix_position_snapshots_snapshot_batch_id"),
        "position_snapshots",
        ["snapshot_batch_id"],
        unique=False,
    )

    op.drop_index("position_snapshot_resolved_identity", table_name="position_snapshots")
    op.drop_index("position_snapshot_unresolved_identity", table_name="position_snapshots")
    op.create_index(
        "position_snapshot_resolved_identity",
        "position_snapshots",
        ["snapshot_batch_id", "asset_id"],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL"),
    )
    op.create_index(
        "position_snapshot_unresolved_identity",
        "position_snapshots",
        ["snapshot_batch_id", "asset_reference_id"],
        unique=True,
        postgresql_where=sa.text("asset_reference_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("position_snapshot_unresolved_identity", table_name="position_snapshots")
    op.drop_index("position_snapshot_resolved_identity", table_name="position_snapshots")
    op.drop_index(op.f("ix_position_snapshots_snapshot_batch_id"), table_name="position_snapshots")

    with op.batch_alter_table("position_snapshots") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_position_snapshots_snapshot_batch_id_portfolio_snapshot_batches"),
            type_="foreignkey",
        )
        batch_op.drop_column("snapshot_batch_id")

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

    op.drop_index(
        op.f("ix_portfolio_snapshot_batches_snapshot_time"),
        table_name="portfolio_snapshot_batches",
    )
    op.drop_index(
        op.f("ix_portfolio_snapshot_batches_portfolio_id"),
        table_name="portfolio_snapshot_batches",
    )
    op.drop_table("portfolio_snapshot_batches")
