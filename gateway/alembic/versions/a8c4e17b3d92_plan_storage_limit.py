"""plan storage limit

Revision ID: a8c4e17b3d92
Revises: f6b3d95e28a7
Create Date: 2026-09-19

"""
import json
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'a8c4e17b3d92'
down_revision: Union[str, Sequence[str], None] = 'f6b3d95e28a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STORAGE_MB = {"free": 1024, "pro": 10240, "enterprise": None}
_FEATURES = {"free": "1 GB of storage", "pro": "10 GB of storage"}


def _plans(bind):
    return bind.execute(sa.text("SELECT id, limits, features FROM plans")).fetchall()


def _load(value):
    return json.loads(value) if isinstance(value, str) else (value or {})


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    for plan_id, limits, features in _plans(bind):
        limits = _load(limits)
        if "storage_mb" not in limits:
            limits["storage_mb"] = _STORAGE_MB.get(plan_id)
        features = _load(features) or []
        extra = _FEATURES.get(plan_id)
        if extra and extra not in features:
            features.insert(min(2, len(features)), extra)
        bind.execute(
            sa.text("UPDATE plans SET limits = :limits, features = :features WHERE id = :id"),
            {"limits": json.dumps(limits), "features": json.dumps(features), "id": plan_id},
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    for plan_id, limits, features in _plans(bind):
        limits = _load(limits)
        limits.pop("storage_mb", None)
        features = [f for f in (_load(features) or []) if f not in _FEATURES.values()]
        bind.execute(
            sa.text("UPDATE plans SET limits = :limits, features = :features WHERE id = :id"),
            {"limits": json.dumps(limits), "features": json.dumps(features), "id": plan_id},
        )
