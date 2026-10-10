# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Finds the leftovers a running deployment accumulates.

None of these are errors on their own, and none are deleted here. They are the
rows that stop matching reality over time: a workspace nobody belongs to, a key
issued and never used, an invite to someone who has since signed up. Left alone
they are what turns into a manual cleanup against the live database, which has
already happened once here with 268 orphaned workspace directories.
"""

import datetime

from sqlalchemy.orm import joinedload

from app.models import (
    APIKey,
    Membership,
    SharedLink,
    User,
    Workspace,
    WorkspaceInvite,
    utcnow,
)

STALE_KEY_DAYS = 90


def _aware(moment):
    """Treat a naive timestamp as UTC, which is what the columns hold."""
    if moment is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=datetime.timezone.utc)
    return moment


def empty_workspaces(db):
    """Workspaces with no active member.

    Nobody can reach these through the app, so they are invisible until someone
    goes looking, and they still hold whatever is on disk.
    """
    active = (
        db.query(Membership.workspace_id)
        .filter(Membership.status == "active")
        .distinct()
        .subquery()
    )
    return (
        db.query(Workspace)
        .options(joinedload(Workspace.creator))
        .filter(~Workspace.id.in_(db.query(active.c.workspace_id)))
        .order_by(Workspace.slug)
        .all()
    )


def unused_keys(db):
    """Keys that have never been used, or not for a long time.

    A key is a live credential, so one nobody is using is only risk. Keys made
    in the last day are skipped, since a new key not yet used is normal.
    """
    cutoff = utcnow() - datetime.timedelta(days=STALE_KEY_DAYS)
    fresh = utcnow() - datetime.timedelta(days=1)
    rows = (
        db.query(APIKey)
        .options(joinedload(APIKey.owner))
        .filter(APIKey.is_active.is_(True))
        .all()
    )
    stale = []
    for key in rows:
        created, used = _aware(key.created_at), _aware(key.last_used_at)
        if used is None:
            if created is not None and created < fresh:
                stale.append((key, "never used"))
        elif used < cutoff:
            stale.append((key, f"last used {used.date()}"))
    return stale


def expired_links(db):
    """Shared links whose expiry has passed. They no longer work, so they are
    only a list of addresses somebody was once given access to."""
    now = utcnow()
    rows = (
        db.query(SharedLink)
        .options(joinedload(SharedLink.workspace))
        .filter(SharedLink.expires_at.isnot(None))
        .all()
    )
    return [link for link in rows if _aware(link.expires_at) < now]


def answered_invites(db):
    """Email invites whose recipient has since registered.

    Registering converts pending invites into memberships, so one left behind
    means the two paths disagreed, and the person is now holding an invite they
    can never accept.
    """
    return (
        db.query(WorkspaceInvite)
        .options(joinedload(WorkspaceInvite.workspace))
        .join(User, User.email == WorkspaceInvite.email)
        .order_by(WorkspaceInvite.created_at)
        .all()
    )


def findings(db):
    """Everything worth a look, as sections the page can render in order."""
    return [
        {
            "title": "Workspaces with no active member",
            "note": "Unreachable through the app, and still holding whatever is on disk.",
            "rows": [
                f"{ws.slug} (created by {ws.creator.email if ws.creator else 'unknown'})"
                for ws in empty_workspaces(db)
            ],
        },
        {
            "title": "Keys nobody is using",
            "note": f"Active keys never used, or unused for {STALE_KEY_DAYS} days.",
            "rows": [
                f"{key.name} ({key.owner.email if key.owner else 'unknown'}) - {why}"
                for key, why in unused_keys(db)
            ],
        },
        {
            "title": "Shared links past their expiry",
            "note": "These no longer grant anything.",
            "rows": [
                f"{link.workspace.slug if link.workspace else 'unknown'} - "
                f"{link.invite_email or 'anyone'}, expired {_aware(link.expires_at).date()}"
                for link in expired_links(db)
            ],
        },
        {
            "title": "Invites to people who already signed up",
            "note": "Registering should have turned these into memberships.",
            "rows": [
                f"{invite.email} for "
                f"{invite.workspace.slug if invite.workspace else 'unknown'}"
                for invite in answered_invites(db)
            ],
        },
    ]
