"""workspace created_at

Revision ID: d81f3a06e2c4
Revises: c5a2e9d41b77
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd81f3a06e2c4'
down_revision: Union[str, Sequence[str], None] = 'c5a2e9d41b77'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'workspaces',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('workspaces', 'created_at')
