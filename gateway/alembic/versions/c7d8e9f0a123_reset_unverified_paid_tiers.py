"""Reset paid tiers that were set without a verified subscription.

Revision ID: c7d8e9f0a123
Revises: c6a1e3f8d247
Create Date: 2026-10-14

"""
from typing import Sequence, Union

from alembic import op


revision: str = "c7d8e9f0a123"
down_revision: Union[str, Sequence[str], None] = "c6a1e3f8d247"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Paid tiers have no verified subscription source in this application yet."""
    op.execute("UPDATE users SET tier = 'free' WHERE tier IS NULL OR tier <> 'free'")


def downgrade() -> None:
    """Do not restore unverifiable paid tiers."""
    pass
