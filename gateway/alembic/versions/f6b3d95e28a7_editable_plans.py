"""editable plans

Revision ID: f6b3d95e28a7
Revises: e5a2c84d19f6
Create Date: 2026-09-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'f6b3d95e28a7'
down_revision: Union[str, Sequence[str], None] = 'e5a2c84d19f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_SEED = [
    {
        "id": "free", "name": "Free", "price": 0, "sort_order": 0, "is_public": True,
        "limits": {"workspaces": 1, "members": 3, "api_keys": 2}, "retention_days": 7,
        "features": ["1 workspace", "3 team members", "7-day log retention", "Community support"],
    },
    {
        "id": "pro", "name": "Pro", "price": 29, "sort_order": 1, "is_public": True,
        "limits": {"workspaces": 10, "members": None, "api_keys": 20}, "retention_days": 90,
        "features": [
            "10 workspaces", "Unlimited members", "90-day log retention",
            "Priority support", "Shared links",
        ],
    },
    {
        "id": "enterprise", "name": "Enterprise", "price": None, "sort_order": 2, "is_public": True,
        "limits": {"workspaces": None, "members": None, "api_keys": None}, "retention_days": None,
        "features": [
            "Unlimited workspaces", "SSO & audit logs", "Unlimited retention",
            "Dedicated support", "Custom SLAs",
        ],
    },
]


def upgrade() -> None:
    """Upgrade schema."""
    plans = op.create_table(
        'plans',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('price', sa.Integer(), nullable=True),
        sa.Column('sort_order', sa.Integer(), server_default='0', nullable=False),
        sa.Column('is_public', sa.Boolean(), server_default='true', nullable=False),
        sa.Column('archived_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('limits', sa.JSON(), nullable=False),
        sa.Column('features', sa.JSON(), nullable=False),
        sa.Column('retention_days', sa.Integer(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.bulk_insert(plans, _SEED)
    op.create_foreign_key('fk_users_tier_plans', 'users', 'plans', ['tier'], ['id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('fk_users_tier_plans', 'users', type_='foreignkey')
    op.drop_table('plans')
