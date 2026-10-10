"""workspace storage limit

Revision ID: e7c1a4f38b29
Revises: d4b7e2a90c15
Create Date: 2026-09-30

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'e7c1a4f38b29'
down_revision: Union[str, Sequence[str], None] = 'd4b7e2a90c15'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_WORKSPACE_STORAGE_MB = {"free": 1024, "pro": 5120, "enterprise": None}


def _plans(bind):
    return bind.execute(sa.text("SELECT id, limits FROM plans")).fetchall()


def _load(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def _save(bind, plan_id, limits):
    bind.execute(
        sa.text("UPDATE plans SET limits = :limits WHERE id = :id"),
        {"limits": json.dumps(limits), "id": plan_id},
    )


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    for plan_id, limits in _plans(bind):
        limits = _load(limits)
        if "workspace_storage_mb" not in limits:
            limits["workspace_storage_mb"] = _WORKSPACE_STORAGE_MB.get(plan_id)
            _save(bind, plan_id, limits)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    for plan_id, limits in _plans(bind):
        limits = _load(limits)
        limits.pop("workspace_storage_mb", None)
        _save(bind, plan_id, limits)
