"""membership created_at

Revision ID: g1h2i3j4k5l6
Revises: f2d9b6a1c047
Create Date: 2026-11-09

Add a created_at timestamp to the memberships table so the daily invite-email
rate-limit can count how many pending-acceptance rows were created in the last
24 hours alongside WorkspaceInvite rows.  Existing rows get NULL (the column
is nullable), which means they are invisible to the 24-hour window query and
never counted against the new limit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'g1h2i3j4k5l6'
down_revision: Union[str, Sequence[str], None] = 'a3e8d5c7b214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'memberships',
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('memberships', 'created_at')

