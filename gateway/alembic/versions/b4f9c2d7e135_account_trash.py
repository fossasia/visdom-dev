"""account trash

Revision ID: b4f9c2d7e135
Revises: f2d9b6a1c047
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b4f9c2d7e135'
down_revision: Union[str, Sequence[str], None] = 'f2d9b6a1c047'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('trashed_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('users', sa.Column('trashed_by', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('users', 'trashed_by')
    op.drop_column('users', 'trashed_at')
