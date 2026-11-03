# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Removing invites nobody answered.

An invite holds a seat on the owner's plan until it is answered, so one that is
never answered holds it forever. Both kinds expire after ``INVITE_EXPIRY_DAYS``:
a ``workspace_invites`` row for an email with no account yet, and a
``pending_acceptance`` membership for someone who has one. Zero turns this off.
"""

import datetime

from sqlalchemy.orm import Session

from app.config import settings
from app.database import SessionLocal
from app.models import Membership, WorkspaceInvite, utcnow


def cutoff(now: datetime.datetime | None = None) -> datetime.datetime | None:
    """Invites sent before this have expired, or None when they never do."""
    if settings.INVITE_EXPIRY_DAYS <= 0:
        return None
    return (now or utcnow()) - datetime.timedelta(days=settings.INVITE_EXPIRY_DAYS)


def is_expired(sent_at: datetime.datetime | None, now: datetime.datetime | None = None) -> bool:
    """Whether an invite sent at ``sent_at`` is past the cutoff, swept or not."""
    before = cutoff(now)
    if before is None or sent_at is None:
        return False
    if sent_at.tzinfo is None:
        sent_at = sent_at.replace(tzinfo=datetime.timezone.utc)
    return sent_at < before


def expire(db: Session, now: datetime.datetime | None = None) -> int:
    """Delete every invite older than the cutoff. Returns how many went."""
    before = cutoff(now)
    if before is None:
        return 0
    removed = (
        db.query(WorkspaceInvite)
        .filter(WorkspaceInvite.created_at < before)
        .delete(synchronize_session=False)
    )
    removed += (
        db.query(Membership)
        .filter(Membership.status == "pending_acceptance", Membership.invited_at < before)
        .delete(synchronize_session=False)
    )
    db.commit()
    return removed


def expire_once() -> int:
    db = SessionLocal()
    try:
        return expire(db)
    finally:
        db.close()
