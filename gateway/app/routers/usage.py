# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""What an account's own workspaces have used this month.

Deliberately small: active time and storage, which are the two things an
account is likely to be charged on, and nothing about how the instances work
underneath. Only workspaces the account owns are counted, since that is what
its plan pays for.
"""

import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.billing import limit_for
from app.dependencies import get_current_user, get_db
from app.models import User, Workspace, WorkspaceUsageHour, utcnow
from app.usage import MEGABYTE, latest_storage, owned_workspace_ids

router = APIRouter(prefix="/usage", tags=["usage"])


def month_start(moment: datetime.datetime | None = None) -> datetime.datetime:
    moment = moment or utcnow()
    return moment.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def active_minutes_since(db: Session, workspace_ids, since) -> dict:
    """Minutes with work in them, per workspace, from `since` onwards."""
    if not workspace_ids:
        return {}
    rows = (
        db.query(WorkspaceUsageHour.workspace_id, func.sum(WorkspaceUsageHour.active_minutes))
        .filter(
            WorkspaceUsageHour.workspace_id.in_(workspace_ids),
            WorkspaceUsageHour.hour_start >= since,
        )
        .group_by(WorkspaceUsageHour.workspace_id)
        .all()
    )
    return {workspace_id: int(total or 0) for workspace_id, total in rows}


@router.get("")
def my_usage(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """This month's active time and current storage for the workspaces you own."""
    since = month_start()
    ids = owned_workspace_ids(db, current_user)
    workspaces = (
        db.query(Workspace).filter(Workspace.id.in_(ids)).order_by(Workspace.name).all()
        if ids
        else []
    )
    minutes = active_minutes_since(db, ids, since)
    storage = latest_storage(db, ids)

    rows = [
        {
            "id": str(ws.id),
            "name": ws.name,
            "slug": ws.slug,
            "active_minutes": minutes.get(ws.id, 0),
            "storage_bytes": storage.get(ws.id, 0),
        }
        for ws in workspaces
    ]
    per_workspace_mb = limit_for(db, current_user.tier, "workspace_storage_mb")
    return {
        "period_start": since.isoformat(),
        "workspace_storage_limit": None if per_workspace_mb is None else per_workspace_mb * MEGABYTE,
        "totals": {
            "active_minutes": sum(row["active_minutes"] for row in rows),
            "storage_bytes": sum(row["storage_bytes"] for row in rows),
        },
        "workspaces": rows,
    }
