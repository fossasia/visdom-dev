"""invite expiry

Revision ID: c4d8a1e6f925
Revises: a3e8d5c7b214
Create Date: 2026-11-02

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c4d8a1e6f925'
down_revision: Union[str, Sequence[str], None] = 'a3e8d5c7b214'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'memberships',
        sa.Column('invited_at', sa.DateTime(timezone=True), nullable=True),
    )
    # Invites already waiting get a full window from today rather than none.
    op.execute(
        "UPDATE memberships SET invited_at = CURRENT_TIMESTAMP "
        "WHERE status = 'pending_acceptance'"
    )
    op.execute(
        "UPDATE workspace_invites SET created_at = CURRENT_TIMESTAMP "
        "WHERE created_at IS NULL"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('memberships', 'invited_at')
