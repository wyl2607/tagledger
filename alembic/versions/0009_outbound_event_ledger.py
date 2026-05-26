"""outbound_event_ledger

Revision ID: 0009_outbound_event_ledger
Revises: 0008_signoff_pairing_usage
Create Date: 2026-05-26 20:20:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0009_outbound_event_ledger"
down_revision: Union[str, Sequence[str], None] = "0008_signoff_pairing_usage"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(table_name: str, index_name: str, columns: list[str]) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    bind = op.get_bind()
    if not _table_exists(bind, "outbound_scan_event_ledger"):
        op.create_table(
            "outbound_scan_event_ledger",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.String(), nullable=False),
            sa.Column("order_no", sa.String(), nullable=False),
            sa.Column("part_code", sa.String(), nullable=False),
            sa.Column("location_code", sa.String(), nullable=True),
            sa.Column("source_code", sa.String(), nullable=False),
            sa.Column("matched_code", sa.String(), nullable=False),
            sa.Column("quantity", sa.Integer(), nullable=False),
            sa.Column("outcome", sa.String(), nullable=False),
            sa.Column("operator_id", sa.String(), nullable=False),
            sa.Column("record_id", sa.Integer(), nullable=True),
            sa.Column("scan_id", sa.Integer(), nullable=True),
            sa.Column("verification_record_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    for column in (
        "factory_id",
        "order_no",
        "part_code",
        "location_code",
        "outcome",
        "operator_id",
        "record_id",
        "scan_id",
        "verification_record_id",
    ):
        _create_index_if_missing(
            "outbound_scan_event_ledger",
            f"ix_outbound_scan_event_ledger_{column}",
            [column],
        )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "outbound_scan_event_ledger"):
        op.drop_table("outbound_scan_event_ledger")
