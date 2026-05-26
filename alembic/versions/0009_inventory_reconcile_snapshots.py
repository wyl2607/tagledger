"""inventory_reconcile_snapshots

Revision ID: 0009_inventory_reconcile
Revises: 0008_signoff_pairing_usage
Create Date: 2026-05-24 17:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0009_inventory_reconcile"
down_revision: Union[str, Sequence[str], None] = "0008_signoff_pairing_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "inventory_reconcile_snapshots"):
        op.create_table(
            "inventory_reconcile_snapshots",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("filename", sa.String(), nullable=False),
            sa.Column("file_hash", sa.String(), nullable=False),
            sa.Column("uploaded_by", sa.String(), nullable=False),
            sa.Column("uploaded_by_user_id", sa.Integer(), nullable=True),
            sa.Column("parsed_row_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("summary_json", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists(
        bind,
        "inventory_reconcile_snapshots",
        "ix_inventory_reconcile_snapshots_filename",
    ):
        op.create_index(
            "ix_inventory_reconcile_snapshots_filename",
            "inventory_reconcile_snapshots",
            ["filename"],
            unique=False,
        )
    if not _index_exists(
        bind,
        "inventory_reconcile_snapshots",
        "ix_inventory_reconcile_snapshots_file_hash",
    ):
        op.create_index(
            "ix_inventory_reconcile_snapshots_file_hash",
            "inventory_reconcile_snapshots",
            ["file_hash"],
            unique=True,
        )
    if not _index_exists(
        bind,
        "inventory_reconcile_snapshots",
        "ix_inventory_reconcile_snapshots_uploaded_by",
    ):
        op.create_index(
            "ix_inventory_reconcile_snapshots_uploaded_by",
            "inventory_reconcile_snapshots",
            ["uploaded_by"],
            unique=False,
        )
    if not _index_exists(
        bind,
        "inventory_reconcile_snapshots",
        "ix_inventory_reconcile_snapshots_uploaded_by_user_id",
    ):
        op.create_index(
            "ix_inventory_reconcile_snapshots_uploaded_by_user_id",
            "inventory_reconcile_snapshots",
            ["uploaded_by_user_id"],
            unique=False,
        )
    if not _index_exists(
        bind,
        "inventory_reconcile_snapshots",
        "ix_inventory_reconcile_snapshots_created_at",
    ):
        op.create_index(
            "ix_inventory_reconcile_snapshots_created_at",
            "inventory_reconcile_snapshots",
            ["created_at"],
            unique=False,
        )

    if not _table_exists(bind, "inventory_reconcile_snapshot_items"):
        op.create_table(
            "inventory_reconcile_snapshot_items",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("snapshot_id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.String(), nullable=False),
            sa.Column("part_key", sa.String(), nullable=False),
            sa.Column("location_code", sa.String(), nullable=False),
            sa.Column("system_quantity", sa.Integer(), nullable=True),
            sa.Column("excel_quantity", sa.Integer(), nullable=True),
            sa.Column("category", sa.String(), nullable=False),
            sa.Column("processing_status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.ForeignKeyConstraint(["snapshot_id"], ["inventory_reconcile_snapshots.id"]),
            sa.PrimaryKeyConstraint("id"),
        )
    for index_name, columns in {
        "ix_inventory_reconcile_snapshot_items_snapshot_id": ["snapshot_id"],
        "ix_inventory_reconcile_snapshot_items_factory_id": ["factory_id"],
        "ix_inventory_reconcile_snapshot_items_part_key": ["part_key"],
        "ix_inventory_reconcile_snapshot_items_location_code": ["location_code"],
        "ix_inventory_reconcile_snapshot_items_category": ["category"],
        "ix_inventory_reconcile_snapshot_items_processing_status": ["processing_status"],
        "ix_inventory_reconcile_snapshot_items_created_at": ["created_at"],
        "ix_inventory_reconcile_snapshot_items_lookup": [
            "factory_id",
            "part_key",
            "location_code",
        ],
    }.items():
        if not _index_exists(bind, "inventory_reconcile_snapshot_items", index_name):
            op.create_index(
                index_name,
                "inventory_reconcile_snapshot_items",
                columns,
                unique=False,
            )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "inventory_reconcile_snapshot_items"):
        op.drop_table("inventory_reconcile_snapshot_items")
    if _table_exists(bind, "inventory_reconcile_snapshots"):
        op.drop_table("inventory_reconcile_snapshots")
