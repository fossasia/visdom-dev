"""heartbeats

Revision ID: f2d9b6a1c047
Revises: e7c1a4f38b29
Create Date: 2026-10-01

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f2d9b6a1c047'
down_revision: Union[str, Sequence[str], None] = 'e7c1a4f38b29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'heartbeats',
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('beat_at', sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('name'),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table('heartbeats')
