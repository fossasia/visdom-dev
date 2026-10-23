"""stripe subscriptions

Revision ID: d2b7e9c41f05
Revises: 3cf8fbd2e287
Create Date: 2026-10-19

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'd2b7e9c41f05'
down_revision: Union[str, Sequence[str], None] = '3cf8fbd2e287'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('plans', sa.Column('stripe_price_id', sa.String(), nullable=True))
    op.create_unique_constraint('uq_plans_stripe_price_id', 'plans', ['stripe_price_id'])
    op.create_table(
        'subscriptions',
        sa.Column('id', sa.String(), nullable=False),
        sa.Column('user_id', sa.UUID(), nullable=False),
        sa.Column('plan_id', sa.String(), nullable=True),
        sa.Column('price_id', sa.String(), nullable=True),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('current_period_end', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ends_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plan_id'], ['plans.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_subscriptions_user_id'), 'subscriptions', ['user_id'], unique=False)
    op.create_index(op.f('ix_users_stripe_customer_id'), 'users', ['stripe_customer_id'], unique=False)
    op.execute("UPDATE plans SET price = 20 WHERE id = 'pro' AND price = 29")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("UPDATE plans SET price = 29 WHERE id = 'pro' AND price = 20")
    op.drop_index(op.f('ix_users_stripe_customer_id'), table_name='users')
    op.drop_index(op.f('ix_subscriptions_user_id'), table_name='subscriptions')
    op.drop_table('subscriptions')
    op.drop_constraint('uq_plans_stripe_price_id', 'plans', type_='unique')
    op.drop_column('plans', 'stripe_price_id')
