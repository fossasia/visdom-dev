"""staff grants

Revision ID: c6a1e3f8d247
Revises: b4f9c2d7e135
Create Date: 2026-10-06

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'c6a1e3f8d247'
down_revision: Union[str, Sequence[str], None] = 'b4f9c2d7e135'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'staff_grants',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('permission', sa.String(), nullable=False),
        sa.Column('role', sa.String(), nullable=True),
        sa.Column('admin_user_id', sa.UUID(), nullable=True),
        sa.Column('granted_by', sa.String(), nullable=True),
        sa.Column('granted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['admin_user_id'], ['admin_users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_staff_grants_permission'), 'staff_grants', ['permission'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_staff_grants_permission'), table_name='staff_grants')
    op.drop_table('staff_grants')
