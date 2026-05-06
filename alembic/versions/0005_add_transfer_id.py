"""add_transfer_id

Revision ID: 0005_add_transfer_id
Revises: 0004_outbound_rollback_and_verification
Create Date: 2026-05-06 01:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0005_add_transfer_id"
down_revision: Union[str, Sequence[str], None] = "0004_outbound_rollback_and_verification"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _column_exists(bind, "inventory_movements", "transfer_id"):
        op.add_column(
            "inventory_movements",
            sa.Column("transfer_id", sa.String(length=64), nullable=True),
        )
    if not _index_exists(bind, "inventory_movements", "ix_inventory_movements_transfer_id"):
        op.create_index(
            "ix_inventory_movements_transfer_id",
            "inventory_movements",
            ["transfer_id"],
            unique=False,
        )

    if not _column_exists(bind, "outbound_scans", "transfer_id"):
        op.add_column(
            "outbound_scans",
            sa.Column("transfer_id", sa.String(length=64), nullable=True),
        )
    if not _index_exists(bind, "outbound_scans", "ix_outbound_scans_transfer_id"):
        op.create_index(
            "ix_outbound_scans_transfer_id",
            "outbound_scans",
            ["transfer_id"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("outbound_scans") as batch_op:
        if _index_exists(bind, "outbound_scans", "ix_outbound_scans_transfer_id"):
            batch_op.drop_index("ix_outbound_scans_transfer_id")
        if _column_exists(bind, "outbound_scans", "transfer_id"):
            batch_op.drop_column("transfer_id")

    with op.batch_alter_table("inventory_movements") as batch_op:
        if _index_exists(bind, "inventory_movements", "ix_inventory_movements_transfer_id"):
            batch_op.drop_index("ix_inventory_movements_transfer_id")
        if _column_exists(bind, "inventory_movements", "transfer_id"):
            batch_op.drop_column("transfer_id")
