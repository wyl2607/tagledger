"""add_location_kind

Revision ID: 0002_add_location_kind
Revises: 0001_baseline
Create Date: 2026-05-05 18:46:14.536180

"""

from typing import Sequence, Union

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_add_location_kind"
down_revision: Union[str, Sequence[str], None] = "0001_baseline"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "inventory_locations",
        sa.Column("location_kind", sa.String(), nullable=True, server_default="permanent"),
    )
    op.execute(
        sa.text(
            "UPDATE inventory_locations "
            "SET location_kind='permanent' "
            "WHERE location_kind IS NULL OR location_kind = ''"
        )
    )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("inventory_locations") as batch_op:
        batch_op.drop_column("location_kind")
