"""admin role ladder

Revision ID: b8d4f2a61e97
Revises: a7c3e1f09b52
Create Date: 2026-09-15

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b8d4f2a61e97'
down_revision: Union[str, Sequence[str], None] = 'a7c3e1f09b52'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE admin_users SET role = 'support' WHERE role = 'viewer'")
    op.alter_column(
        'admin_users',
        'role',
        existing_type=sa.String(),
        existing_nullable=False,
        server_default='support',
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'admin_users',
        'role',
        existing_type=sa.String(),
        existing_nullable=False,
        server_default='viewer',
    )
    op.execute("UPDATE admin_users SET role = 'support' WHERE role = 'admin'")
