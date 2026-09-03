"""Add provenance and identity semantics for Position Change V0.

Revision ID: 20260904_0011
Revises: 20260903_0010
Create Date: 2026-09-04
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260904_0011"
down_revision: str | None = "20260903_0010"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("portfolio_actions") as batch_op:
        batch_op.add_column(sa.Column("asset_reference_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("previous_snapshot_batch_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("current_snapshot_batch_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("previous_position_snapshot_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("current_position_snapshot_id", sa.Uuid(), nullable=True))
        batch_op.alter_column("asset_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column("current_snapshot_id", existing_type=sa.Uuid(), nullable=True)
        batch_op.alter_column(
            "action_type",
            existing_type=sa.String(length=12),
            type_=sa.Enum(
                "POSITION_ADDED",
                "POSITION_REMOVED",
                "POSITION_INCREASED",
                "POSITION_DECREASED",
                "POSITION_UNCHANGED",
                name="portfolioactiontype",
                native_enum=False,
                length=19,
            ),
            existing_nullable=False,
        )

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE portfolio_actions AS pa
            SET current_snapshot_batch_id = current_position.snapshot_batch_id,
                current_position_snapshot_id = pa.current_snapshot_id
            FROM position_snapshots AS current_position
            WHERE current_position.id = pa.current_snapshot_id
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE portfolio_actions AS pa
            SET previous_snapshot_batch_id = previous_position.snapshot_batch_id,
                previous_position_snapshot_id = pa.previous_snapshot_id
            FROM position_snapshots AS previous_position
            WHERE previous_position.id = pa.previous_snapshot_id
            """
        )
    )
    connection.execute(
        sa.text(
            """
            UPDATE portfolio_actions
            SET action_type = CASE action_type
                WHEN 'NEW_POSITION' THEN 'POSITION_ADDED'
                WHEN 'INCREASE' THEN 'POSITION_INCREASED'
                WHEN 'DECREASE' THEN 'POSITION_DECREASED'
                WHEN 'EXIT' THEN 'POSITION_REMOVED'
                WHEN 'UNCHANGED' THEN 'POSITION_UNCHANGED'
                ELSE action_type
            END
            """
        )
    )

    with op.batch_alter_table("portfolio_actions") as batch_op:
        batch_op.create_foreign_key(
            op.f("fk_portfolio_actions_previous_snapshot_batch_id_portfolio_snapshot_batches"),
            "portfolio_snapshot_batches",
            ["previous_snapshot_batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            op.f("fk_portfolio_actions_current_snapshot_batch_id_portfolio_snapshot_batches"),
            "portfolio_snapshot_batches",
            ["current_snapshot_batch_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            op.f("fk_portfolio_actions_previous_position_snapshot_id_position_snapshots"),
            "position_snapshots",
            ["previous_position_snapshot_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            op.f("fk_portfolio_actions_current_position_snapshot_id_position_snapshots"),
            "position_snapshots",
            ["current_position_snapshot_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.alter_column(
            "previous_snapshot_batch_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )
        batch_op.alter_column(
            "current_snapshot_batch_id",
            existing_type=sa.Uuid(),
            nullable=False,
        )

    op.drop_constraint("portfolio_action_current_snapshot", "portfolio_actions", type_="unique")
    op.create_check_constraint(
        "portfolio_action_asset_identity",
        "portfolio_actions",
        "(asset_id IS NOT NULL AND asset_reference_id IS NULL) OR "
        "(asset_id IS NULL AND asset_reference_id IS NOT NULL)",
    )
    for column in (
        "asset_reference_id",
        "previous_snapshot_batch_id",
        "current_snapshot_batch_id",
        "previous_position_snapshot_id",
        "current_position_snapshot_id",
    ):
        op.create_index(
            op.f(f"ix_portfolio_actions_{column}"),
            "portfolio_actions",
            [column],
            unique=False,
        )
    op.create_index(
        "portfolio_action_resolved_identity",
        "portfolio_actions",
        [
            "portfolio_id",
            "previous_snapshot_batch_id",
            "current_snapshot_batch_id",
            "asset_id",
            "action_type",
        ],
        unique=True,
        postgresql_where=sa.text("asset_id IS NOT NULL"),
    )
    op.create_index(
        "portfolio_action_unresolved_identity",
        "portfolio_actions",
        [
            "portfolio_id",
            "previous_snapshot_batch_id",
            "current_snapshot_batch_id",
            "asset_reference_id",
            "action_type",
        ],
        unique=True,
        postgresql_where=sa.text("asset_reference_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("portfolio_action_unresolved_identity", table_name="portfolio_actions")
    op.drop_index("portfolio_action_resolved_identity", table_name="portfolio_actions")
    for column in (
        "current_position_snapshot_id",
        "previous_position_snapshot_id",
        "current_snapshot_batch_id",
        "previous_snapshot_batch_id",
        "asset_reference_id",
    ):
        op.drop_index(op.f(f"ix_portfolio_actions_{column}"), table_name="portfolio_actions")
    op.drop_constraint(
        op.f("ck_portfolio_actions_portfolio_action_asset_identity"),
        "portfolio_actions",
        type_="check",
    )

    with op.batch_alter_table("portfolio_actions") as batch_op:
        batch_op.drop_constraint(
            op.f("fk_portfolio_actions_current_position_snapshot_id_position_snapshots"),
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            op.f("fk_portfolio_actions_previous_position_snapshot_id_position_snapshots"),
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            op.f("fk_portfolio_actions_current_snapshot_batch_id_portfolio_snapshot_batches"),
            type_="foreignkey",
        )
        batch_op.drop_constraint(
            op.f("fk_portfolio_actions_previous_snapshot_batch_id_portfolio_snapshot_batches"),
            type_="foreignkey",
        )
        batch_op.drop_column("current_position_snapshot_id")
        batch_op.drop_column("previous_position_snapshot_id")
        batch_op.drop_column("current_snapshot_batch_id")
        batch_op.drop_column("previous_snapshot_batch_id")
        batch_op.drop_column("asset_reference_id")
        batch_op.alter_column("asset_id", existing_type=sa.Uuid(), nullable=False)
        batch_op.alter_column("current_snapshot_id", existing_type=sa.Uuid(), nullable=False)

    connection = op.get_bind()
    connection.execute(
        sa.text(
            """
            UPDATE portfolio_actions
            SET action_type = CASE action_type
                WHEN 'POSITION_ADDED' THEN 'NEW_POSITION'
                WHEN 'POSITION_INCREASED' THEN 'INCREASE'
                WHEN 'POSITION_DECREASED' THEN 'DECREASE'
                WHEN 'POSITION_REMOVED' THEN 'EXIT'
                WHEN 'POSITION_UNCHANGED' THEN 'UNCHANGED'
                ELSE action_type
            END
            """
        )
    )
    op.create_unique_constraint(
        "portfolio_action_current_snapshot",
        "portfolio_actions",
        ["current_snapshot_id"],
    )
