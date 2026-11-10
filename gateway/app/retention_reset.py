# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Dropping retention notice when what it promised no longer holds.

A retention email tells an owner what their plan keeps and what goes. That
stops being true when the owner's plan changes, when a limit bypass ends, or
when the workspace gets a new owner, so the notice on record has to go and the
next sweep waits for a fresh one.

This is one ORM flush hook rather than a reset at each place that can change a
plan or an owner. Whatever path writes ``User.tier``, ``User.bypass_limits``,
``Workspace.created_by`` or the bypass switch for everyone, the reset happens
in the same flush, so it commits or rolls back with that write. A bulk
``query.update()`` skips ORM events, so those columns must keep being written
through the ORM.

Nothing here imports ``app.retention``, so modules that change plans
(payments, bypass, billing) do not need it at all.
"""

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app import bypass
from app.models import PlatformSwitch, User, Workspace

_UNKNOWN = object()


def _change(obj, attr):
    """``(before, after)`` for a pending write to ``attr``, or None if there is none.

    ``before`` is ``_UNKNOWN`` when the old value was not loaded, for example
    after a commit expired the object. A caller treats that as a real change.
    """
    history = inspect(obj).attrs[attr].history
    if not history.added:
        return None
    before = history.deleted[0] if history.deleted else _UNKNOWN
    after = history.added[0]
    if before is not _UNKNOWN and before == after:
        return None
    return before, after


def _turned_off(obj, attr) -> bool:
    change = _change(obj, attr)
    if change is None:
        return False
    before, after = change
    return not after and (before is _UNKNOWN or bool(before))


def clear(workspace: Workspace) -> None:
    """Forget every retention warning this workspace was given."""
    if workspace.retention_warned_at is not None:
        workspace.retention_warned_at = None
    if workspace.retention_notice is not None:
        workspace.retention_notice = None


@event.listens_for(Session, "before_flush")
def _drop_stale_notice(session, _flush_context, _instances) -> None:
    owners = set()
    everyone = False
    for obj in list(session.dirty):
        if isinstance(obj, User):
            if _change(obj, "tier") is not None or _turned_off(obj, "bypass_limits"):
                owners.add(obj.id)
        elif isinstance(obj, Workspace):
            if _change(obj, "created_by") is not None:
                clear(obj)
        elif isinstance(obj, PlatformSwitch):
            if obj.name == bypass.EVERYONE and _turned_off(obj, "is_on"):
                everyone = True
    if not owners and not everyone:
        return
    with session.no_autoflush:
        query = session.query(Workspace)
        if everyone:
            query = query.filter(
                Workspace.retention_warned_at.isnot(None) | Workspace.retention_notice.isnot(None)
            )
        else:
            query = query.filter(Workspace.created_by.in_(owners))
        for workspace in query.all():
            clear(workspace)
