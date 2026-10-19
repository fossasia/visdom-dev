# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
How much of a plan's countable allowance an account is using.

Shared by the billing page and by the checks that refuse a creation, so the
number someone is shown and the number they are held to are the same one.
"""

import datetime

from fastapi import HTTPException, status
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.billing import at_limit, limit_for
from app.models import APIKey, Membership, User, Workspace, WorkspaceInvite, WorkspaceUsageHour, utcnow


def owned_workspace_ids(db: Session, user: User, include_trashed: bool = False) -> list:
    query = db.query(Workspace.id).filter(Workspace.created_by == user.id)
    if not include_trashed:
        query = query.filter(Workspace.trashed_at.is_(None))
    return [row[0] for row in query.all()]


def workspaces_used(db: Session, user: User) -> int:
    return len(owned_workspace_ids(db, user))


def members_used(db: Session, user: User) -> int:
    owned = owned_workspace_ids(db, user)
    if not owned:
        return 0
    return (
        db.query(Membership)
        .filter(
            Membership.workspace_id.in_(owned),
            Membership.user_id != user.id,
            Membership.status == "active",
        )
        .count()
    )


def invites_waiting(db: Session, user: User) -> int:
    """Invites sent and not yet answered, across the workspaces the account owns.

    Both kinds: someone with an account who has not accepted, and an address
    with no account yet. Each one is a seat promised to somebody.
    """
    owned = owned_workspace_ids(db, user)
    if not owned:
        return 0
    unanswered = (
        db.query(Membership)
        .filter(
            Membership.workspace_id.in_(owned),
            Membership.user_id != user.id,
            Membership.status == "pending_acceptance",
        )
        .count()
    )
    unregistered = db.query(WorkspaceInvite).filter(WorkspaceInvite.workspace_id.in_(owned)).count()
    return unanswered + unregistered


def invites_waiting_in(db: Session, workspace_id) -> int:
    """Invites sent and not yet answered in one workspace."""
    unanswered = (
        db.query(Membership)
        .filter(
            Membership.workspace_id == workspace_id,
            Membership.status == "pending_acceptance",
        )
        .count()
    )
    unregistered = db.query(WorkspaceInvite).filter(WorkspaceInvite.workspace_id == workspace_id).count()
    return unanswered + unregistered


def seats_held(db: Session, user: User) -> int:
    return members_used(db, user) + invites_waiting(db, user)


def _still_works(expires_at, now) -> bool:
    if expires_at is None:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=datetime.timezone.utc)
    return now <= expires_at


def api_keys_used(db: Session, user: User) -> int:
    now = utcnow()
    rows = db.query(APIKey.expires_at).filter(APIKey.user_id == user.id, APIKey.is_active.is_(True)).all()
    return sum(1 for (expires_at,) in rows if _still_works(expires_at, now))


COUNTERS = {
    "workspaces": workspaces_used,
    "members": seats_held,
    "api_keys": api_keys_used,
}

_REFUSALS = {
    "workspaces": "You have reached the workspace limit for the {plan} plan.",
    "members": "You have reached the team member limit for the {plan} plan.",
    "api_keys": "You have reached the API key limit for the {plan} plan.",
}


def usage(db: Session, user: User) -> dict:
    return {name: count(db, user) for name, count in COUNTERS.items()}


def hold_account(db: Session, user: User) -> None:
    """Make checks against this account's limits wait for one another.

    A check counts rows and the caller adds one afterwards, so two requests at
    once could both find room. Holding the account's row until the caller
    commits lets only one of them count at a time.
    """
    db.query(User).filter(User.id == user.id).with_for_update().populate_existing().first()


def refuse_if_at_limit(db: Session, user: User, resource: str) -> None:
    """Stop a creation that the account's plan does not allow."""
    hold_account(db, user)
    tier = user.tier or "free"
    if not at_limit(db, tier, resource, COUNTERS[resource](db, user)):
        return
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=_REFUSALS[resource].format(plan=tier),
    )


def refuse_if_no_seat(db: Session, owner: User) -> None:
    """Stop an invite or an approval that the owner's plan has no seat for.

    Invites still waiting count as taken. Counting only the people who had
    accepted let an owner send any number of invites while under the limit and
    end up with all of them as members.
    """
    hold_account(db, owner)
    tier = owner.tier or "free"
    ceiling = limit_for(db, tier, "members")
    if ceiling is None:
        return
    waiting = invites_waiting(db, owner)
    if members_used(db, owner) + waiting < ceiling:
        return
    detail = f"The {tier} plan allows {ceiling} team members and every seat is taken"
    if waiting:
        detail += (
            f", counting {waiting} invite{'' if waiting == 1 else 's'} still waiting. "
            "Cancel one to free a seat."
        )
    else:
        detail += "."
    raise HTTPException(status_code=status.HTTP_402_PAYMENT_REQUIRED, detail=detail)


def refuse_if_full(db: Session, owner: User) -> None:
    """Stop someone joining a workspace whose owner's plan is already full.

    An invite holds a seat, so accepting one normally finds room. This is for
    the invite that was sent before seats were held, or the plan that shrank
    while it waited.
    """
    hold_account(db, owner)
    tier = owner.tier or "free"
    ceiling = limit_for(db, tier, "members")
    if ceiling is None or members_used(db, owner) < ceiling:
        return
    raise HTTPException(
        status_code=status.HTTP_402_PAYMENT_REQUIRED,
        detail=(
            "This workspace has no room for another member on its owner's plan. "
            "Ask one of its admins."
        ),
    )


def latest_storage(db: Session, workspace_ids) -> dict:
    """Bytes on disk per workspace, as of the most recent hour recorded.

    Storage is a level rather than a total, so this is the latest reading and
    never a sum over the month.
    """
    if not workspace_ids:
        return {}
    newest = (
        db.query(
            WorkspaceUsageHour.workspace_id,
            func.max(WorkspaceUsageHour.hour_start).label("hour_start"),
        )
        .filter(WorkspaceUsageHour.workspace_id.in_(workspace_ids))
        .group_by(WorkspaceUsageHour.workspace_id)
        .subquery()
    )
    rows = (
        db.query(WorkspaceUsageHour.workspace_id, WorkspaceUsageHour.current_bytes)
        .join(
            newest,
            and_(
                WorkspaceUsageHour.workspace_id == newest.c.workspace_id,
                WorkspaceUsageHour.hour_start == newest.c.hour_start,
            ),
        )
        .all()
    )
    return {workspace_id: int(size or 0) for workspace_id, size in rows}


MEGABYTE = 1024 * 1024


def storage_used(db: Session, user: User) -> int:
    """Bytes on disk across every workspace the account owns, as last sampled.

    Workspaces in the trash count too. Their files stay on disk until they are
    purged, so leaving them out let an account trash a full workspace and fill
    another.
    """
    return sum(latest_storage(db, owned_workspace_ids(db, user, include_trashed=True)).values())


def workspace_storage_limit(db: Session, workspace: Workspace) -> int | None:
    """Bytes one workspace may hold under its owner's plan, or None for no cap."""
    owner = workspace.creator
    if owner is None:
        return None
    limit_mb = limit_for(db, owner.tier, "workspace_storage_mb")
    return None if limit_mb is None else limit_mb * MEGABYTE


def storage_refusal(db: Session, workspace: Workspace) -> str | None:
    """Why new plots are refused here, or ``None`` while there is room.

    Two ceilings: what any one workspace may hold, and what all of the owner's
    workspaces may hold together. The first is what stops one busy workspace
    taking the whole allowance, or the whole disk on a plan with no total.

    The owner's plan is the one that pays, so a member writing into someone
    else's workspace is held to the owner's limit, not their own. The gateway
    only says so: visdom refuses the requests that add data, and keeps serving
    reads and deletions, which is how an account gets back under the limit.
    """
    owner = workspace.creator
    if owner is None:
        return None
    ceiling = workspace_storage_limit(db, workspace)
    if ceiling is not None and latest_storage(db, [workspace.id]).get(workspace.id, 0) >= ceiling:
        return (
            f"This workspace has used all {ceiling // MEGABYTE:,} MB of storage one "
            f"workspace may hold on the {owner.tier} plan, so new plots are refused. "
            "Viewing still works; deleting old environments frees space."
        )
    limit_mb = limit_for(db, owner.tier, "storage_mb")
    if limit_mb is None:
        return None
    if storage_used(db, owner) < limit_mb * MEGABYTE:
        return None
    return (
        f"This workspace's owner has used all {limit_mb:,} MB of storage on the "
        f"{owner.tier} plan, so new plots are refused. Viewing still works; "
        "deleting old environments frees space."
    )
