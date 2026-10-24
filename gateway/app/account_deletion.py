# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Closing an account: a request, a waiting period, then removal.

A request stops the account working straight away but removes nothing. Signing
in during the next ``GRACE_DAYS`` cancels it. After that the account goes for
good, and so do the workspaces nobody else was using, and signing in is refused:
removal may already be partway through, and an account handed back then could
be missing some of its files.

A workspace other people still use never goes with the account. Its owner, or
its only admin, has to put someone else in charge first, so a team is never
left holding a workspace nobody can run.
"""

import datetime
import logging

from sqlalchemy.orm import Session

from app import payments
from app.admin.activity import FilesKept, drop_workspace
from app.database import SessionLocal
from app.models import AdminAction, Membership, User, Workspace, WorkspaceInvite, utcnow
from app.retention import only_sweep

GRACE_DAYS = 30

_DELETION_LOCK = 7234093

_OWNER = "you own it. Make another member the owner from the Members tab."
_LAST_ADMIN = "you are its only admin. Make another member an admin from the Members tab."


def _aware(moment):
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def _others(db: Session, workspace_id, user_id) -> list[Membership]:
    return (
        db.query(Membership)
        .filter(
            Membership.workspace_id == workspace_id,
            Membership.user_id != user_id,
            Membership.status == "active",
        )
        .all()
    )


def standing(db: Session, user: User) -> dict:
    """What deleting this account would take with it, and what is in the way.

    ``leaving_with`` are the live workspaces where this account is the only
    active member. ``blockers`` are the ones with other members that this
    account is still responsible for.
    """
    rows = (
        db.query(Workspace, Membership)
        .join(Membership, Membership.workspace_id == Workspace.id)
        .filter(
            Membership.user_id == user.id,
            Membership.status == "active",
            Workspace.trashed_at.is_(None),
        )
        .order_by(Workspace.name)
        .all()
    )
    blockers, leaving_with = [], []
    for workspace, mine in rows:
        others = _others(db, workspace.id, user.id)
        if not others:
            leaving_with.append(workspace)
        elif workspace.created_by == user.id:
            blockers.append((workspace, _OWNER))
        elif mine.role == "admin" and not any(m.role == "admin" for m in others):
            blockers.append((workspace, _LAST_ADMIN))
    return {"blockers": blockers, "leaving_with": leaving_with}


def delete_after(user: User) -> datetime.datetime | None:
    requested = _aware(user.deletion_requested_at)
    if requested is None:
        return None
    return requested + datetime.timedelta(days=GRACE_DAYS)


def request(db: Session, user: User) -> datetime.datetime:
    """Start the waiting period and close every session the account has.

    Nothing is removed here, except that a paid plan is told not to renew, so
    the waiting period never brings another charge. The caller has already
    checked ``standing``.
    """
    payments.stop_renewing(db, user)
    user.deletion_requested_at = utcnow()
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return delete_after(user)


def final(user: User, now: datetime.datetime | None = None) -> bool:
    deadline = delete_after(user)
    return deadline is not None and deadline <= (now or utcnow())


def cancel(user: User) -> bool:
    """Called on sign-in. Returns whether there was a request to cancel."""
    if user.deletion_requested_at is None:
        return False
    user.deletion_requested_at = None
    return True


def due_ids(db: Session, now: datetime.datetime | None = None) -> list:
    cutoff = (now or utcnow()) - datetime.timedelta(days=GRACE_DAYS)
    return [
        row[0]
        for row in db.query(User.id)
        .filter(User.deletion_requested_at.isnot(None), User.deletion_requested_at <= cutoff)
        .all()
    ]


def _heir(db: Session, workspace_id, user_id):
    admins = sorted(
        (m for m in _others(db, workspace_id, user_id) if m.role == "admin"),
        key=lambda m: str(m.user_id),
    )
    return admins[0].user_id if admins else None


def erase(db: Session, user_id, now: datetime.datetime | None = None) -> dict | None:
    """Remove one account whose waiting period is over.

    The row is locked and the deadline checked again, so two workers cannot
    both remove it. An account that has picked up a blocker since the request
    is left alone and logged, rather than taking a shared workspace with it.

    The plot files of the workspaces going with it are removed first. If any
    instance does not confirm, the account stays and the next tick tries again.
    A refusal ends the transaction, so the row is not held while the remaining
    accounts are worked through.
    """
    cutoff = (now or utcnow()) - datetime.timedelta(days=GRACE_DAYS)
    user = (
        db.query(User)
        .filter(
            User.id == user_id,
            User.deletion_requested_at.isnot(None),
            User.deletion_requested_at <= cutoff,
        )
        .with_for_update(skip_locked=True)
        .first()
    )
    if user is None:
        return None
    try:
        return remove(db, user, f"asked for by the account holder {GRACE_DAYS} days earlier")
    except StillNeeded as exc:
        logging.warning("account %s is due for deletion but still runs %s", user.id, exc)
    except FilesKept as exc:
        logging.warning("account %s is due for deletion but kept: %s", user.id, exc)
    except (payments.PaymentsDown, payments.PaymentsOff) as exc:
        logging.warning("account %s is due for deletion but its plan is still paid: %s", user.id, exc)
    db.commit()
    return None


class StillNeeded(RuntimeError):
    """The account still runs a workspace other people use."""


def remove(db: Session, user: User, reason: str, staff_id=None, staff_email=None) -> dict:
    """Remove an account and the workspaces only it uses, for good.

    Refused with ``StillNeeded`` while the account is responsible for a
    workspace other people use, with ``FilesKept`` when an instance did not
    confirm that the plot files are gone, and with ``payments.PaymentsDown``
    when a paid plan could not be cancelled. Either way the account and its rows
    stay. Files already removed for an earlier workspace stay removed, which is
    why signing in no longer cancels once the waiting period is over.
    """
    state = standing(db, user)
    if state["blockers"]:
        raise StillNeeded(", ".join(ws.slug for ws, _ in state["blockers"]))

    payments.end_now(db, user)

    freed = 0
    for workspace in state["leaving_with"]:
        freed += drop_workspace(workspace.id)["bytes"]

    removed = []
    for workspace in state["leaving_with"]:
        db.query(WorkspaceInvite).filter(WorkspaceInvite.workspace_id == workspace.id).delete(
            synchronize_session=False
        )
        removed.append(workspace.slug)
        db.delete(workspace)
    db.flush()

    for workspace in db.query(Workspace).filter(Workspace.created_by == user.id).all():
        workspace.created_by = (
            _heir(db, workspace.id, user.id) if workspace.trashed_at is None else None
        )
    db.query(WorkspaceInvite).filter(WorkspaceInvite.invited_by == user.id).update(
        {WorkspaceInvite.invited_by: None}, synchronize_session=False
    )

    row_id = str(user.id)
    db.add(
        AdminAction(
            admin_id=staff_id,
            admin_email=staff_email,
            action="delete",
            model="User",
            row_id=row_id,
            changes={
                "reason": reason,
                "email": user.email,
                "workspaces_removed": removed,
                "bytes_freed": freed,
            },
        )
    )
    db.delete(user)
    db.commit()
    return {"user_id": row_id, "workspaces_removed": removed}


def erase_due(db: Session, now: datetime.datetime | None = None) -> int:
    erased = 0
    for user_id in due_ids(db, now):
        try:
            if erase(db, user_id, now) is not None:
                erased += 1
        except Exception:
            logging.exception("could not delete account %s", user_id)
            db.rollback()
    return erased


def erase_once() -> int | None:
    with only_sweep(key=_DELETION_LOCK) as mine:
        if not mine:
            return None
        db = SessionLocal()
        try:
            return erase_due(db)
        finally:
            db.close()
