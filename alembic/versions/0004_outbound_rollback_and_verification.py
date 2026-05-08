"""outbound_rollback_and_verification

Revision ID: 0004_outbound_verify
Revises: 0003_factory_id_all_tables
Create Date: 2026-05-06 00:05:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0004_outbound_verify"
down_revision: Union[str, Sequence[str], None] = "0003_factory_id_all_tables"
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
    if not _column_exists(bind, "outbound_scans", "verification_record_id"):
        op.add_column(
            "outbound_scans",
            sa.Column("verification_record_id", sa.Integer(), nullable=True),
        )
    if not _index_exists(bind, "outbound_scans", "ix_outbound_scans_verification_record_id"):
        op.create_index(
            "ix_outbound_scans_verification_record_id",
            "outbound_scans",
            ["verification_record_id"],
            unique=False,
        )

    if not _column_exists(bind, "outbound_progress_snapshots", "completed_at"):
        op.add_column(
            "outbound_progress_snapshots",
            sa.Column("completed_at", sa.DateTime(), nullable=True),
        )
    if not _index_exists(
        bind, "outbound_progress_snapshots", "ix_outbound_progress_snapshots_completed_at"
    ):
        op.create_index(
            "ix_outbound_progress_snapshots_completed_at",
            "outbound_progress_snapshots",
            ["completed_at"],
            unique=False,
        )


def downgrade() -> None:
    bind = op.get_bind()
    with op.batch_alter_table("outbound_progress_snapshots") as batch_op:
        if _index_exists(
            bind, "outbound_progress_snapshots", "ix_outbound_progress_snapshots_completed_at"
        ):
            batch_op.drop_index("ix_outbound_progress_snapshots_completed_at")
        if _column_exists(bind, "outbound_progress_snapshots", "completed_at"):
            batch_op.drop_column("completed_at")

    with op.batch_alter_table("outbound_scans") as batch_op:
        if _index_exists(bind, "outbound_scans", "ix_outbound_scans_verification_record_id"):
            batch_op.drop_index("ix_outbound_scans_verification_record_id")
        if _column_exists(bind, "outbound_scans", "verification_record_id"):
            batch_op.drop_column("verification_record_id")
