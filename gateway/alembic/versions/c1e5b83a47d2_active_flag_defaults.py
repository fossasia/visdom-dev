"""active flag defaults

Revision ID: c1e5b83a47d2
Revises: b8d4f2a61e97
Create Date: 2026-09-17

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c1e5b83a47d2'
down_revision: Union[str, Sequence[str], None] = 'b8d4f2a61e97'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    for table in ('users', 'api_keys'):
        op.execute("UPDATE %s SET is_active = true WHERE is_active IS NULL" % table)
        op.alter_column(
            table,
            'is_active',
            existing_type=sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        )


def downgrade() -> None:
    """Downgrade schema."""
    for table in ('users', 'api_keys'):
        op.alter_column(
            table,
            'is_active',
            existing_type=sa.Boolean(),
            nullable=True,
            server_default=None,
        )
