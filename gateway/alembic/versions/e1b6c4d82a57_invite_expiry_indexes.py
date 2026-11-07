"""indexes for the invite expiry sweep

Revision ID: e1b6c4d82a57
Revises: c4d8a1e6f925
Create Date: 2026-11-07

The sweep deletes ``workspace_invites`` older than a cutoff and
``pending_acceptance`` memberships older than that same cutoff. Neither
filter had an index.

This revision continues ``c4d8a1e6f925``, so this branch stays one Alembic
line. The retention-warning branch adds ``b7f2e4a9c613``, which also revises
``a3e8d5c7b214``. Each branch is linear on its own. Merging both produces two
heads, and the second merge needs a merge revision that revises
``e1b6c4d82a57`` and ``b7f2e4a9c613``. Neither branch should name the other's
revision as its parent.
"""
from typing import Sequence, Union

from alembic import op


revision: str = "e1b6c4d82a57"
down_revision: Union[str, Sequence[str], None] = "c4d8a1e6f925"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index("ix_workspace_invites_created_at", "workspace_invites", ["created_at"])
    op.create_index("ix_memberships_status_invited_at", "memberships", ["status", "invited_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_memberships_status_invited_at", table_name="memberships")
    op.drop_index("ix_workspace_invites_created_at", table_name="workspace_invites")
