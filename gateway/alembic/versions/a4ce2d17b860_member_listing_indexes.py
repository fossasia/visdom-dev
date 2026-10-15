"""Index workspace member listing cursors.

Revision ID: a4ce2d17b860
Revises: c6a1e3f8d247
Create Date: 2026-10-10

"""
from typing import Sequence, Union

from alembic import op


revision: str = "a4ce2d17b860"
down_revision: Union[str, Sequence[str], None] = "c6a1e3f8d247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_memberships_workspace_user", "memberships", ["workspace_id", "user_id"]
    )
    op.create_index(
        "ix_workspace_invites_workspace_id", "workspace_invites", ["workspace_id", "id"]
    )


def downgrade() -> None:
    op.drop_index("ix_workspace_invites_workspace_id", table_name="workspace_invites")
    op.drop_index("ix_memberships_workspace_user", table_name="memberships")
