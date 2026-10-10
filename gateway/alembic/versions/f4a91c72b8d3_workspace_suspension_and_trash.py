"""workspace suspension and trash

Revision ID: f4a91c72b8d3
Revises: e93b7c1d5a20
Create Date: 2026-09-03

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f4a91c72b8d3'
down_revision: Union[str, Sequence[str], None] = 'e93b7c1d5a20'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'workspaces',
        sa.Column(
            'is_active',
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )
    op.add_column(
        'workspaces',
        sa.Column('trashed_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('workspaces', 'trashed_at')
    op.drop_column('workspaces', 'is_active')
