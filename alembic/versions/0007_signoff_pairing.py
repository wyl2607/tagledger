"""signoff_pairing

Revision ID: 0007_signoff_pairing
Revises: 0006_return_signoff_models
Create Date: 2026-05-08 18:10:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

revision: str = "0007_signoff_pairing"
down_revision: Union[str, Sequence[str], None] = "0006_return_signoff_models"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(bind, table_name: str) -> bool:
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(bind, table_name: str, index_name: str) -> bool:
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def _create_index_if_missing(
    table_name: str,
    index_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    bind = op.get_bind()
    if not _index_exists(bind, table_name, index_name):
        op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "signoff_pairing_keys"):
        op.create_table(
            "signoff_pairing_keys",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.Integer(), nullable=False),
            sa.Column("token_hash", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("created_by", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("expires_at", sa.DateTime(), nullable=False),
            sa.Column("revoked_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "signoff_pairing_keys", "ix_signoff_pairing_keys_factory_id", ["factory_id"]
    )
    _create_index_if_missing(
        "signoff_pairing_keys", "ix_signoff_pairing_keys_candidate_id", ["candidate_id"]
    )
    _create_index_if_missing(
        "signoff_pairing_keys", "ix_signoff_pairing_keys_token_hash", ["token_hash"], unique=True
    )
    _create_index_if_missing("signoff_pairing_keys", "ix_signoff_pairing_keys_status", ["status"])
    _create_index_if_missing(
        "signoff_pairing_keys", "ix_signoff_pairing_keys_created_by", ["created_by"]
    )
    _create_index_if_missing(
        "signoff_pairing_keys", "ix_signoff_pairing_keys_expires_at", ["expires_at"]
    )
    _create_index_if_missing(
        "signoff_pairing_keys", "ix_signoff_pairing_keys_revoked_at", ["revoked_at"]
    )

    if not _table_exists(bind, "signoff_assist_sessions"):
        op.create_table(
            "signoff_assist_sessions",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("factory_id", sa.String(), nullable=False),
            sa.Column("candidate_id", sa.Integer(), nullable=False),
            sa.Column("pairing_key_id", sa.Integer(), nullable=False),
            sa.Column("mode", sa.String(), nullable=False),
            sa.Column("prepared_payload_hash", sa.String(), nullable=False),
            sa.Column("previewed_at", sa.DateTime(), nullable=False),
            sa.Column("operator_decision", sa.String(), nullable=True),
            sa.Column("external_completion_mark", sa.String(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    _create_index_if_missing(
        "signoff_assist_sessions", "ix_signoff_assist_sessions_factory_id", ["factory_id"]
    )
    _create_index_if_missing(
        "signoff_assist_sessions", "ix_signoff_assist_sessions_candidate_id", ["candidate_id"]
    )
    _create_index_if_missing(
        "signoff_assist_sessions", "ix_signoff_assist_sessions_pairing_key_id", ["pairing_key_id"]
    )
    _create_index_if_missing("signoff_assist_sessions", "ix_signoff_assist_sessions_mode", ["mode"])
    _create_index_if_missing(
        "signoff_assist_sessions",
        "ix_signoff_assist_sessions_prepared_payload_hash",
        ["prepared_payload_hash"],
    )
    _create_index_if_missing(
        "signoff_assist_sessions", "ix_signoff_assist_sessions_previewed_at", ["previewed_at"]
    )
    _create_index_if_missing(
        "signoff_assist_sessions",
        "ix_signoff_assist_sessions_operator_decision",
        ["operator_decision"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if _table_exists(bind, "signoff_assist_sessions"):
        op.drop_table("signoff_assist_sessions")
    if _table_exists(bind, "signoff_pairing_keys"):
        op.drop_table("signoff_pairing_keys")
