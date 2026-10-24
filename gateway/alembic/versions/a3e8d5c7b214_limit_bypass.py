"""limit bypass

Revision ID: a3e8d5c7b214
Revises: d2b7e9c41f05
Create Date: 2026-10-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a3e8d5c7b214'
down_revision: Union[str, Sequence[str], None] = 'd2b7e9c41f05'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'users',
        sa.Column('bypass_limits', sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_table(
        'platform_switches',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('is_on', sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column('changed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('changed_by', sa.String(), nullable=True),
        sa.PrimaryKeyConstraint('name'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('platform_switches')
    op.drop_column('users', 'bypass_limits')
