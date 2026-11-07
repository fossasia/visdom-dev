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

When email is configured, an environment already past the window is removed
only after the owner was warned at least ``RETENTION_WARN_DAYS`` earlier. The
pass that sends that warning does not delete: the sweep looks at the timestamp
already stored, and the warning is recorded afterwards. That covers the first
time enforcement is on, a plan or owner change that cleared the timestamp, and
a send that failed. A later pass removes what the aged warning covered, then
warns about the next window. Environments that are only approaching the window
are named in the email and are not removed. Before ``RETENTION_STARTS``, and
while a start is still further off than the warning window, nothing is removed
and the existing warning schedule is unchanged. Email that is not configured
does not hold removal back, so a deployment without a relay does not keep data
forever.

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

from app import bypass
from app import email as outbound
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
    """How many days of work this workspace keeps, or None for all of it.

    All of it, too, while the owner's limits are bypassed. How long work is
    kept is one of the things a plan limits, and a promotion that lifted the
    rest while still deleting old work would not be what it said it was.
    """
    plan = plan_for(db, workspace)
    if plan is None or bypass.applies_to(db, workspace.creator):
        return None
    return plan.retention_days


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

    With email configured, a workspace is only enforced once
    ``removal_allowed`` says its stored warning is old enough. The timestamp is
    the one loaded here, so a warning sent later in the same pass cannot
    authorize this removal.
    """
    enforce = enforcing() if enforce is None else enforce
    now = utcnow()
    due = []
    for workspace in sweepable(db):
        days = window_for(db, workspace)
        if days:
            due.append(
                (
                    SimpleNamespace(
                        id=workspace.id,
                        slug=workspace.slug,
                        retention_warned_at=workspace.retention_warned_at,
                    ),
                    days,
                )
            )
    db.commit()

    summary = {"visited": 0, "with_expired": 0, "removed": 0, "workspaces": []}
    for workspace, days in due:
        summary["visited"] += 1
        this_enforce = enforce and removal_allowed(workspace.retention_warned_at, now)
        result = sweep_workspace(workspace, days, this_enforce, ask=ask)
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


def removal_allowed(warned_at, now: datetime.datetime | None = None) -> bool:
    """Whether overdue environments may be removed, given the warning on record.

    With email configured, removal waits until a warning was successfully sent
    at least ``RETENTION_WARN_DAYS`` earlier. A missing timestamp means nothing
    qualifying has been sent: the first time enforcement is on, a send that
    failed, or an owner or plan change that cleared it. A younger warning is
    still inside that grace. Email that is not configured does not hold
    removal back, so enforcement keeps working without a relay.
    """
    if not outbound.configured():
        return True
    if warned_at is None:
        return False
    now = now or utcnow()
    if warned_at.tzinfo is None:
        warned_at = warned_at.replace(tzinfo=datetime.timezone.utc)
    grace = datetime.timedelta(days=max(settings.RETENTION_WARN_DAYS, 1))
    return now - warned_at >= grace


def sweep_once(ask=ask_instance) -> dict | None:
    """Remove what an earlier warning covered, then warn about the next window.

    Removal runs first and reads the warning timestamp already stored, so the
    message this pass sends cannot authorize deleting in this pass. Overdue
    environments therefore stay until a warning has had
    ``RETENTION_WARN_DAYS`` of notice. The warning afterwards is the one the
    owner reads before a later pass removes that work. With email
    unconfigured, removal is unchanged and no warning is sent.
    """
    with only_sweep() as mine:
        if not mine:
            return None
        db = SessionLocal()
        try:
            summary = sweep(db, ask=ask)
            try:
                warn_owners(db, ask=ask)
            except Exception:
                logger.exception("retention: warning owners failed")
                db.rollback()
            return summary
        finally:
            db.close()


_SOONEST = 0.01


def expiring(
    workspace: Workspace, older_than_days: float, ask=ask_instance, timeout=None, complete=False
) -> list | None:
    """Environments older than the given age, from whichever instances answer.

    None when no instance answered, so the console can say it does not know
    rather than that nothing is going. With ``complete``, also None when any
    instance did not answer, for a caller that must not act on a partial list.
    """
    addresses = instance_addresses()
    if not addresses:
        return None
    timeout = settings.VISDOM_ACTIVITY_TIMEOUT if timeout is None else timeout
    days = max(older_than_days, _SOONEST)
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(addresses)) as pool:
        answers = list(pool.map(lambda a: ask(a, workspace.id, days, True, timeout), addresses))
    answered = [answer for answer in answers if answer is not None]
    if not answered or (complete and len(answered) < len(answers)):
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
    days = window_for(db, workspace)
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


def warn_owners(db: Session, ask=ask_instance, now: datetime.datetime | None = None) -> int:
    """Email each owner whose workspace has work about to be removed.

    The console banner only reaches someone who opens the console. One email
    per warning window is enough: a workspace warned less than
    ``RETENTION_WARN_DAYS`` ago is skipped, so a daily sweep does not repeat it.
    While deleting is still scheduled, nobody is emailed until the start day is
    within ``RETENTION_WARN_DAYS``, so a far-off start does not mean an email
    every few days until then.

    Only a message the relay took counts as a warning, so with email not set
    up, or a failed send, the next sweep tries again. A workspace is skipped
    when any instance did not answer, since the list of what goes would be
    incomplete. As in ``sweep``, the database is read first and the
    transaction ended before any instance is asked. Returns how many went out.
    """
    if not outbound.configured() or not settings.RETENTION_ENFORCE:
        return 0
    now = now or utcnow()
    today = now.date()
    starts = settings.RETENTION_STARTS
    if starts is not None and today < starts:
        ahead = (starts - today).days
        if ahead > settings.RETENTION_WARN_DAYS:
            return 0
        starts_on = starts
    else:
        ahead = settings.RETENTION_WARN_DAYS
        starts_on = None
    gap = datetime.timedelta(days=max(settings.RETENTION_WARN_DAYS, 1))

    due = []
    for workspace in sweepable(db):
        warned = workspace.retention_warned_at
        if warned is not None:
            if warned.tzinfo is None:
                warned = warned.replace(tzinfo=datetime.timezone.utc)
            if now - warned < gap:
                continue
        owner = workspace.creator
        if owner is None or not owner.email:
            continue
        days = window_for(db, workspace)
        if not days:
            continue
        due.append((SimpleNamespace(id=workspace.id, name=workspace.name), owner.email, days))
    db.commit()

    sent = 0
    for workspace, email, days in due:
        envs = expiring(workspace, days - ahead, ask=ask, complete=True)
        if not envs:
            continue
        delivered = outbound.send_retention_warning_email(
            email, workspace.name, days, envs, starts_on, settings.FRONTEND_URL
        )
        if not delivered:
            continue
        db.query(Workspace).filter(Workspace.id == workspace.id).update(
            {Workspace.retention_warned_at: now}, synchronize_session=False
        )
        db.commit()
        sent += 1
    return sent


def forget_warnings(db: Session, user) -> None:
    """Let the workspaces this user owns be warned again, after their plan changed.

    A new plan can keep fewer days, so more work goes sooner than the last
    warning said. The caller commits.
    """
    db.query(Workspace).filter(Workspace.created_by == user.id).update(
        {Workspace.retention_warned_at: None}, synchronize_session=False
    )
