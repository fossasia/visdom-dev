# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Removing the work a workspace's plan no longer keeps.

Every plan states how far back it keeps data and, until this, nothing acted on
it, so the free plan's seven days and the paid plan's ninety meant the same
thing: forever. The window belongs to the account that owns the workspace, the
same rule the storage limit follows, because the workspace is what the plan is
sold against and a member on a bigger plan should not quietly extend it.

Deleting is off by default. ``RETENTION_ENFORCE`` starts false so a deployment
runs this as a report for a while first, and what it says it would remove can be
read before anything is gone. That matters more here than anywhere else in the
product, because this is the one job whose whole purpose is destroying work.

The instances behind the proxy share one disk, so the sweep has to reach the
instance that actually holds a workspace. Each one is asked first, in report
mode, and the one that says it holds it is the one told to remove. When every
instance answers and none holds it, the workspace is dormant and any instance
can sweep its files. When one does not answer, it may be the holder, so the
workspace waits for the next sweep.
"""

import concurrent.futures
import contextlib
import datetime
import json
import logging
from types import SimpleNamespace

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.admin.activity import RETIRE_PATH, admin_call, instance_addresses
from app.config import settings
from app.database import SessionLocal, engine
from app.models import Plan, User, Workspace, utcnow

logger = logging.getLogger("visdom.retention")


def plan_for(db: Session, workspace: Workspace) -> Plan | None:
    """The plan of whoever owns the workspace, which is the one that applies."""
    if workspace.created_by is None:
        return None
    owner = db.query(User).filter(User.id == workspace.created_by).first()
    if owner is None:
        return None
    return db.query(Plan).filter(Plan.id == (owner.tier or "")).first()


def window_for(db: Session, workspace: Workspace) -> int | None:
    """How many days of work this workspace keeps, or None for all of it."""
    plan = plan_for(db, workspace)
    return plan.retention_days if plan is not None else None


def enforcing(today: datetime.date | None = None) -> bool:
    """Whether a sweep today deletes, rather than only reporting.

    ``RETENTION_STARTS`` lets deleting be switched on ahead of time, so the
    console can name the day it begins before anything is gone.
    """
    if not settings.RETENTION_ENFORCE:
        return False
    starts = settings.RETENTION_STARTS
    return starts is None or (today or utcnow().date()) >= starts


def sweepable(db: Session) -> list[Workspace]:
    """Workspaces a sweep should visit.

    A suspended or trashed workspace is left alone. Its owner cannot reach it to
    save anything, and the trash has a deletion rule of its own; taking work out
    of it while it waits would make that rule mean something else.
    """
    return (
        db.query(Workspace)
        .filter(Workspace.is_active.is_(True), Workspace.trashed_at.is_(None))
        .all()
    )


def ask_instance(address: str, workspace_id, days, dry_run: bool, timeout: float) -> dict | None:
    """One instance's answer about one workspace, or None if it did not give one."""
    body = json.dumps(
        {
            "workspace_id": str(workspace_id),
            "older_than_days": days,
            "dry_run": dry_run,
        }
    ).encode()
    return admin_call(address, RETIRE_PATH, body, timeout)


def _holder(answers: list[tuple[str, dict]]) -> str | None:
    """The address of the instance holding the workspace, if one does."""
    for address, answer in answers:
        if answer.get("loaded"):
            return address
    return None


def sweep_workspace(workspace: Workspace, days, enforce: bool, ask=ask_instance, timeout=None) -> dict:
    """Report, and optionally remove, one workspace's expired environments."""
    timeout = settings.RETENTION_TIMEOUT if timeout is None else timeout
    addresses = instance_addresses()
    answers = []
    for address in addresses:
        answer = ask(address, workspace.id, days, True, timeout)
        if answer is not None:
            answers.append((address, answer))

    expired = sorted({eid for _address, answer in answers for eid in answer.get("envs", [])})
    result = {
        "workspace": workspace.slug,
        "days": days,
        "expired": expired,
        "removed": 0,
        "enforced": bool(enforce),
    }
    if not expired or not enforce:
        return result

    target = _holder(answers)
    if target is None and len(answers) == len(addresses):
        target = addresses[0] if addresses else None
    if target is None:
        logger.warning("retention: %s skipped, an instance did not answer", workspace.slug)
        return result
    done = ask(target, workspace.id, days, False, timeout)
    result["removed"] = (done or {}).get("removed", 0)
    return result


def sweep(db: Session, enforce: bool | None = None, ask=ask_instance) -> dict:
    """Visit every workspace, reporting and optionally removing what has aged out.

    An account on a plan that keeps everything is skipped without asking any
    instance, which is most of the cost of this when the paid plans are the ones
    with work in them.

    The database is read first and its transaction ended before any instance
    is asked, so a sweep that waits on slow instances holds nothing open.
    """
    enforce = enforcing() if enforce is None else enforce
    due = []
    for workspace in sweepable(db):
        days = window_for(db, workspace)
        if days:
            due.append((SimpleNamespace(id=workspace.id, slug=workspace.slug), days))
    db.commit()

    summary = {"visited": 0, "with_expired": 0, "removed": 0, "workspaces": []}
    for workspace, days in due:
        summary["visited"] += 1
        result = sweep_workspace(workspace, days, enforce, ask=ask)
        if not result["expired"]:
            continue
        summary["with_expired"] += 1
        summary["removed"] += result["removed"]
        summary["workspaces"].append(result)
        logger.info(
            "retention: %s keeps %s days, %d env(s) past it, %d removed",
            result["workspace"],
            days,
            len(result["expired"]),
            result["removed"],
        )
    return summary


_SWEEP_LOCK = 7234092


@contextlib.contextmanager
def only_sweep(bind=None, key=_SWEEP_LOCK):
    bind = bind or engine
    if bind.dialect.name != "postgresql":
        yield True
        return
    with bind.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        mine = bool(conn.execute(text("SELECT pg_try_advisory_lock(:key)"), {"key": key}).scalar())
        try:
            yield mine
        finally:
            if mine:
                conn.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": key})


def sweep_once() -> dict | None:
    with only_sweep() as mine:
        if not mine:
            return None
        db = SessionLocal()
        try:
            return sweep(db)
        finally:
            db.close()


_SOONEST = 0.01


def expiring(workspace: Workspace, older_than_days: float, ask=ask_instance, timeout=None) -> list | None:
    """Environments older than the given age, from whichever instances answer.

    None when no instance answered, so the console can say it does not know
    rather than that nothing is going.
    """
    addresses = instance_addresses()
    if not addresses:
        return None
    timeout = settings.VISDOM_ACTIVITY_TIMEOUT if timeout is None else timeout
    days = max(older_than_days, _SOONEST)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(addresses)) as pool:
        answers = list(pool.map(lambda a: ask(a, workspace.id, days, True, timeout), addresses))
    answered = [answer for answer in answers if answer is not None]
    if not answered:
        return None
    return sorted({eid for answer in answered for eid in answer.get("envs", [])})


def notice(db: Session, workspace: Workspace, ask=ask_instance, today: datetime.date | None = None) -> dict:
    """What a member should be told about how long this workspace keeps work.

    ``state`` is one of ``forever`` (the plan keeps everything), ``not_enforced``
    (the plan has a window but nothing is deleted yet), ``scheduled`` (deleting
    starts on ``starts_on``) or ``active``. ``expiring`` lists what goes next:
    on the start day when scheduled, within ``warn_days`` when active.
    """
    today = today or utcnow().date()
    plan = plan_for(db, workspace)
    days = plan.retention_days if plan is not None else None
    result = {
        "plan": plan.name if plan is not None else None,
        "days": days,
        "state": "forever",
        "starts_on": None,
        "warn_days": settings.RETENTION_WARN_DAYS,
        "expiring": None,
    }
    if not days:
        return result
    if not settings.RETENTION_ENFORCE:
        result["state"] = "not_enforced"
        return result

    starts = settings.RETENTION_STARTS
    if starts is not None and today < starts:
        result["state"] = "scheduled"
        result["starts_on"] = starts
        ahead = (starts - today).days
    else:
        result["state"] = "active"
        ahead = settings.RETENTION_WARN_DAYS
    if workspace.is_active:
        result["expiring"] = expiring(workspace, days - ahead, ask=ask)
    return result
