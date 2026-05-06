"""add_factory_id_to_all_tables

Revision ID: 0003_factory_id_all_tables
Revises: 0002_add_location_kind
Create Date: 2026-05-05 21:15:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0003_factory_id_all_tables"
down_revision: Union[str, Sequence[str], None] = "0002_add_location_kind"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


FACTORY_TABLES = (
    "records",
    "outbound_scans",
    "outbound_progress_snapshots",
    "inventory_locations",
    "inventory_movements",
    "users",
    "audit_logs",
)


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    columns = inspector.get_columns(table_name)
    return any(column["name"] == column_name for column in columns)


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    indexes = inspector.get_indexes(table_name)
    return any(index["name"] == index_name for index in indexes)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    for table_name in FACTORY_TABLES:
        if not _column_exists(bind, table_name, "factory_id"):
            op.add_column(
                table_name,
                sa.Column(
                    "factory_id",
                    sa.String(length=32),
                    nullable=False,
                    server_default="factory_a",
                ),
            )
        op.execute(
            sa.text(
                f"UPDATE {table_name} "
                "SET factory_id = 'factory_a' "
                "WHERE factory_id IS NULL OR factory_id = ''"
            )
        )
        index_name = f"ix_{table_name}_factory_id"
        if not _index_exists(bind, table_name, index_name):
            op.create_index(
                index_name,
                table_name,
                ["factory_id"],
                unique=False,
            )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    for table_name in reversed(FACTORY_TABLES):
        index_name = f"ix_{table_name}_factory_id"
        with op.batch_alter_table(table_name) as batch_op:
            if _index_exists(bind, table_name, index_name):
                batch_op.drop_index(index_name)
            if _column_exists(bind, table_name, "factory_id"):
                batch_op.drop_column("factory_id")
