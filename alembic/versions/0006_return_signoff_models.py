"""return_signoff_models

Revision ID: 0006_return_signoff_models
Revises: 0005_add_transfer_id
Create Date: 2026-05-08 17:35:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0006_return_signoff_models"
down_revision: Union[str, Sequence[str], None] = "0005_add_transfer_id"
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

    if not _table_exists(bind, "return_signoff_candidates"):
        op.create_table(
            "return_signoff_candidates",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("business_key", sa.String(), nullable=False),
            sa.Column("return_reference", sa.String(), nullable=True),
            sa.Column("product_model", sa.String(), nullable=True),
            sa.Column("serial_number", sa.String(), nullable=True),
            sa.Column("captured_at", sa.DateTime(), nullable=True),
            sa.Column("confirmed_by", sa.String(), nullable=True),
            sa.Column("ocr_confidence_summary", sa.String(), nullable=True),
            sa.Column("notes", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    for column in (
        "factory_id",
        "status",
        "business_key",
        "return_reference",
        "product_model",
        "serial_number",
        "captured_at",
        "confirmed_by",
    ):
        _create_index_if_missing(
            "return_signoff_candidates",
            f"ix_return_signoff_candidates_{column}",
            [column],
        )

    if not _table_exists(bind, "evidence_photos"):
        op.create_table(
            "evidence_photos",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.Integer(), nullable=False),
            sa.Column("source_record_id", sa.Integer(), nullable=True),
            sa.Column("photo_type", sa.String(), nullable=False),
            sa.Column("storage_ref", sa.String(), nullable=False),
            sa.Column("capture_device", sa.String(), nullable=False),
            sa.Column("ocr_text_summary", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    for column in (
        "factory_id",
        "candidate_id",
        "source_record_id",
        "photo_type",
        "capture_device",
    ):
        _create_index_if_missing("evidence_photos", f"ix_evidence_photos_{column}", [column])


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "evidence_photos"):
        op.drop_table("evidence_photos")
    if _table_exists(bind, "return_signoff_candidates"):
        op.drop_table("return_signoff_candidates")
