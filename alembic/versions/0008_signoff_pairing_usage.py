"""signoff_pairing_usage

Revision ID: 0008_signoff_pairing_usage
Revises: 0007_signoff_pairing
Create Date: 2026-05-08 18:45:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0008_signoff_pairing_usage"
down_revision: Union[str, Sequence[str], None] = "0007_signoff_pairing"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _column_exists(bind, table_name: str, column_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(column["name"] == column_name for column in inspector.get_columns(table_name))


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "signoff_pairing_keys"):
        return
    if not _column_exists(bind, "signoff_pairing_keys", "preview_count"):
        op.add_column(
            "signoff_pairing_keys",
            sa.Column("preview_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if not _column_exists(bind, "signoff_pairing_keys", "last_previewed_at"):
        op.add_column(
            "signoff_pairing_keys",
            sa.Column("last_previewed_at", sa.DateTime(), nullable=True),
        )
    if not _index_exists(
        bind,
        "signoff_pairing_keys",
        "ix_signoff_pairing_keys_last_previewed_at",
    ):
        op.create_index(
            "ix_signoff_pairing_keys_last_previewed_at",
            "signoff_pairing_keys",
            ["last_previewed_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "signoff_pairing_keys"):
        return
    if _index_exists(bind, "signoff_pairing_keys", "ix_signoff_pairing_keys_last_previewed_at"):
        op.drop_index(
            "ix_signoff_pairing_keys_last_previewed_at", table_name="signoff_pairing_keys"
        )
    if _column_exists(bind, "signoff_pairing_keys", "last_previewed_at"):
        op.drop_column("signoff_pairing_keys", "last_previewed_at")
    if _column_exists(bind, "signoff_pairing_keys", "preview_count"):
        op.drop_column("signoff_pairing_keys", "preview_count")
