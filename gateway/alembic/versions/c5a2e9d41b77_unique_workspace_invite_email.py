"""one pending invite per email per workspace

Revision ID: c5a2e9d41b77
Revises: b3f1c07a91d4
Create Date: 2026-08-27

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c5a2e9d41b77'
down_revision: Union[str, Sequence[str], None] = 'b3f1c07a91d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        """
        DELETE FROM workspace_invites
        WHERE id IN (
            SELECT id FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY workspace_id, email
                           ORDER BY created_at NULLS LAST, id
                       ) AS rn
                FROM workspace_invites
            ) ranked
            WHERE rn > 1
        )
        """
    )
    op.create_unique_constraint(
        'uq_workspace_invites_workspace_email',
        'workspace_invites',
        ['workspace_id', 'email'],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        'uq_workspace_invites_workspace_email',
        'workspace_invites',
        type_='unique',
    )
