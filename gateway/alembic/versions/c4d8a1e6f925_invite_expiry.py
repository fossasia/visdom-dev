"""invite expiry

Revision ID: c4d8a1e6f925
Revises: a3e8d5c7b214
Create Date: 2026-11-02

Adds ``memberships.invited_at`` and the two indexes the expiry sweep filters
on: ``workspace_invites.created_at`` and ``memberships (status, invited_at)``.
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
    op.create_index("ix_workspace_invites_created_at", "workspace_invites", ["created_at"])
    op.create_index("ix_memberships_status_invited_at", "memberships", ["status", "invited_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memberships_status_invited_at", table_name="memberships")
    op.drop_index("ix_workspace_invites_created_at", table_name="workspace_invites")
    op.drop_column('memberships', 'invited_at')
