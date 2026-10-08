"""user deletion_requested_at

Revision ID: d4b7e2a90c15
Revises: c3e8a5f71d24
Create Date: 2026-09-29

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd4b7e2a90c15'
down_revision: Union[str, Sequence[str], None] = 'c3e8a5f71d24'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('deletion_requested_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'deletion_requested_at')
