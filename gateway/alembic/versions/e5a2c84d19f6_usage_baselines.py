"""usage baselines

Revision ID: e5a2c84d19f6
Revises: d3f7a91c5b64
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e5a2c84d19f6'
down_revision: Union[str, Sequence[str], None] = 'd3f7a91c5b64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'usage_baselines',
        sa.Column('instance', sa.String(), nullable=False),
        sa.Column('workspace_id', sa.String(), nullable=False),
        sa.Column('writes', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('broadcasts', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('broadcast_bytes', sa.BigInteger(), server_default='0', nullable=False),
        sa.PrimaryKeyConstraint('instance', 'workspace_id'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('usage_baselines')
