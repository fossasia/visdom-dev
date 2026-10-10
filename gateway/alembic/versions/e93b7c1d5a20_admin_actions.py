"""admin actions audit trail

Revision ID: e93b7c1d5a20
Revises: d81f3a06e2c4
Create Date: 2026-08-28

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e93b7c1d5a20'
down_revision: Union[str, Sequence[str], None] = 'd81f3a06e2c4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'admin_actions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('admin_id', sa.String(), nullable=True),
        sa.Column('admin_email', sa.String(), nullable=True),
        sa.Column('action', sa.String(), nullable=False),
        sa.Column('model', sa.String(), nullable=False),
        sa.Column('row_id', sa.String(), nullable=True),
        sa.Column('changes', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_admin_actions_model'), 'admin_actions', ['model'])
    op.create_index(op.f('ix_admin_actions_row_id'), 'admin_actions', ['row_id'])
    op.create_index(op.f('ix_admin_actions_created_at'), 'admin_actions', ['created_at'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_admin_actions_created_at'), table_name='admin_actions')
    op.drop_index(op.f('ix_admin_actions_row_id'), table_name='admin_actions')
    op.drop_index(op.f('ix_admin_actions_model'), table_name='admin_actions')
    op.drop_table('admin_actions')
