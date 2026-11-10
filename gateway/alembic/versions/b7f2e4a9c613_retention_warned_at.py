"""retention warned at

Revision ID: b7f2e4a9c613
Revises: a3e8d5c7b214
Create Date: 2026-11-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b7f2e4a9c613'
down_revision: Union[str, Sequence[str], None] = 'a3e8d5c7b214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'workspaces',
        sa.Column('retention_warned_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Which environments a warning named, and when: removal is per environment.
    op.add_column('workspaces', sa.Column('retention_notice', sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('workspaces', 'retention_notice')
    op.drop_column('workspaces', 'retention_warned_at')
