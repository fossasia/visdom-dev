# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""The subscription plan catalog and per-tier limits, read from the database.

Plans used to be a constant in this module, so changing what a tier included
meant a code change and a deploy. They now live in the `plans` table; this module
stays the one place that reads them, so nothing that asks about a limit needs
to know where plans are stored.

Two different questions are asked of a plan and they have different answers.
What an account may pick for itself is only what is public and not archived,
since changing plan needs no payment yet and a hidden internal tier must not be
one click away. What staff may assign is anything not archived. And an account
already on an archived plan keeps that plan's limits: archiving stops new
assignments, it does not take anything away.

A `None` limit means unlimited.
"""

import re

from sqlalchemy.orm import Session

from app.models import Plan

DEFAULT_TIER = "free"

LIMIT_KEYS = ("workspaces", "members", "api_keys", "storage_mb", "workspace_storage_mb")

PLAN_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")

DEFAULT_PLANS = [
    {
        "id": "free",
        "name": "Free",
        "price": 0,
        "sort_order": 0,
        "limits": {
            "workspaces": 1,
            "members": 3,
            "api_keys": 2,
            "storage_mb": 1024,
            "workspace_storage_mb": 1024,
        },
        "retention_days": 7,
        "features": [
            "1 workspace",
            "3 team members",
            "1 GB of storage",
            "7-day log retention",
            "Community support",
        ],
    },
    {
        "id": "pro",
        "name": "Pro",
        "price": 29,
        "sort_order": 1,
        "limits": {
            "workspaces": 10,
            "members": None,
            "api_keys": 20,
            "storage_mb": 10240,
            "workspace_storage_mb": 5120,
        },
        "retention_days": 90,
        "features": [
            "10 workspaces",
            "Unlimited members",
            "10 GB of storage",
            "90-day log retention",
            "Priority support",
            "Shared links",
        ],
    },
    {
        "id": "enterprise",
        "name": "Enterprise",
        "price": None,
        "sort_order": 2,
        "limits": {
            "workspaces": None,
            "members": None,
            "api_keys": None,
            "storage_mb": None,
            "workspace_storage_mb": None,
        },
        "retention_days": None,
        "features": [
            "Unlimited workspaces",
            "SSO & audit logs",
            "Unlimited retention",
            "Dedicated support",
            "Custom SLAs",
        ],
    },
]

_NO_PLAN = {
    "id": DEFAULT_TIER,
    "name": "Free",
    "price": 0,
    "limits": dict.fromkeys(LIMIT_KEYS, 0),
    "retention_days": 0,
    "features": [],
}


def seed_default_plans(db: Session) -> int:
    """Insert whichever default plans are missing. Returns how many were added."""
    present = {plan_id for (plan_id,) in db.query(Plan.id)}
    added = 0
    for spec in DEFAULT_PLANS:
        if spec["id"] not in present:
            db.add(Plan(is_public=True, **spec))
            added += 1
    if added:
        db.commit()
    return added


def validate_limits(limits) -> dict:
    """Check a plan's limits, returning them in canonical form.

    Every known marker has to be present. A missing one would otherwise read as
    unlimited, so a typo in the console would quietly hand out everything.
    """
    if not isinstance(limits, dict):
        raise ValueError("Limits must be an object, for example {\"workspaces\": 1}.")
    unknown = sorted(set(limits) - set(LIMIT_KEYS))
    if unknown:
        raise ValueError("Unknown limit: %s. Known limits: %s." % (", ".join(unknown), ", ".join(LIMIT_KEYS)))
    missing = [key for key in LIMIT_KEYS if key not in limits]
    if missing:
        raise ValueError("Every limit must be set; missing: %s. Use null for unlimited." % ", ".join(missing))
    clean = {}
    for key in LIMIT_KEYS:
        value = limits[key]
        if value is None:
            clean[key] = None
            continue
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("%s must be a whole number of zero or more, or null for unlimited." % key)
        clean[key] = value
    return clean


def validate_features(features) -> list:
    """Check a plan's feature bullets, treating an empty value as none."""
    if features in (None, {}, ""):
        return []
    if not isinstance(features, list) or not all(isinstance(f, str) for f in features):
        raise ValueError("Features must be a list of text, for example [\"1 workspace\"].")
    return [f.strip() for f in features if f.strip()]


def _readable_limits(limits) -> dict:
    limits = limits if isinstance(limits, dict) else {}
    clean = {}
    for key in LIMIT_KEYS:
        value = limits.get(key, 0)
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or value < 0):
            value = 0
        clean[key] = value
    return clean


def _as_dict(plan: Plan) -> dict:
    return {
        "id": plan.id,
        "name": plan.name,
        "price": plan.price,
        "limits": _readable_limits(plan.limits),
        "retention_days": plan.retention_days,
        "features": list(plan.features or []),
    }


def _ordered(query):
    return query.order_by(Plan.sort_order, Plan.id)


def ordered_plans(db: Session) -> list:
    """The plans an account can see and pick: public and not archived."""
    rows = _ordered(
        db.query(Plan).filter(Plan.is_public.is_(True), Plan.archived_at.is_(None))
    ).all()
    return [_as_dict(plan) for plan in rows]


def assignable_plans(db: Session) -> list:
    """Every plan staff may put an account on: anything not archived."""
    return _ordered(db.query(Plan).filter(Plan.archived_at.is_(None))).all()


def get_plan(db: Session, tier) -> dict:
    """The plan an account on this tier is held to, archived or not."""
    plan = db.get(Plan, tier or DEFAULT_TIER)
    if plan is None:
        plan = db.get(Plan, DEFAULT_TIER)
    return _as_dict(plan) if plan is not None else dict(_NO_PLAN)


def selectable(db: Session, tier) -> bool:
    """Whether an account may move itself onto this tier."""
    plan = db.get(Plan, tier) if tier else None
    return plan is not None and plan.is_public and plan.archived_at is None


def assignable(db: Session, tier) -> bool:
    """Whether staff may put an account onto this tier."""
    plan = db.get(Plan, tier) if tier else None
    return plan is not None and plan.archived_at is None


def limit_for(db: Session, tier, resource):
    return get_plan(db, tier)["limits"].get(resource)


def at_limit(db: Session, tier, resource, used):
    """Whether one more of this resource would exceed the plan."""
    ceiling = limit_for(db, tier, resource)
    return ceiling is not None and used >= ceiling
