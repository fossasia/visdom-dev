"""key revocation notice

Revision ID: b9d5f28c4e13
Revises: a8c4e17b3d92
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'b9d5f28c4e13'
down_revision: Union[str, Sequence[str], None] = 'a8c4e17b3d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('api_keys', sa.Column('owner_notified_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('api_keys', sa.Column('revoke_after', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('api_keys', 'revoke_after')
    op.drop_column('api_keys', 'owner_notified_at')
