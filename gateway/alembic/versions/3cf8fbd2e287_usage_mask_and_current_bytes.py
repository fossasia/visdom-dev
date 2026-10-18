"""usage mask and current bytes

Revision ID: 3cf8fbd2e287
Revises: c6a1e3f8d247
Create Date: 2026-10-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '3cf8fbd2e287'
down_revision: Union[str, Sequence[str], None] = 'c6a1e3f8d247'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'workspace_usage_hours',
        sa.Column('minutes_mask', sa.BigInteger(), nullable=False, server_default='0'),
    )
    op.add_column(
        'workspace_usage_hours',
        sa.Column('current_bytes', sa.BigInteger(), nullable=False, server_default='0'),
    )
    op.execute('UPDATE workspace_usage_hours SET current_bytes = peak_bytes')


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('workspace_usage_hours', 'current_bytes')
    op.drop_column('workspace_usage_hours', 'minutes_mask')
