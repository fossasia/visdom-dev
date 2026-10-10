"""workspace usage hours

Revision ID: d3f7a91c5b64
Revises: c1e5b83a47d2
Create Date: 2026-09-18

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd3f7a91c5b64'
down_revision: Union[str, Sequence[str], None] = 'c1e5b83a47d2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'workspace_usage_hours',
        sa.Column('workspace_id', sa.UUID(), nullable=False),
        sa.Column('hour_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active_minutes', sa.Integer(), server_default='0', nullable=False),
        sa.Column('writes', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('broadcasts', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('broadcast_bytes', sa.BigInteger(), server_default='0', nullable=False),
        sa.Column('peak_bytes', sa.BigInteger(), server_default='0', nullable=False),
        sa.ForeignKeyConstraint(['workspace_id'], ['workspaces.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('workspace_id', 'hour_start'),
    )
    op.create_index(
        'ix_workspace_usage_hours_hour_start',
        'workspace_usage_hours',
        ['hour_start'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index('ix_workspace_usage_hours_hour_start', table_name='workspace_usage_hours')
    op.drop_table('workspace_usage_hours')
