# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""The staff usage page: every workspace this month, and the machine itself.

Reads the hourly rollup for the workspaces and the host for the machine. Open to
any staff role that can already see workspaces, since it shows the same
workspaces with numbers attached.
"""

from sqladmin import BaseView, expose
from sqlalchemy import func, text
from sqlalchemy.orm import joinedload
from starlette.requests import Request
from starlette.responses import Response

from app.admin import roles, server_stats
from app.admin.panel import ROLE_KEY
from app.database import SessionLocal
from app.models import Workspace, WorkspaceUsageHour
from app.routers.usage import month_start
from app.usage import latest_storage

_UNITS = ("B", "KB", "MB", "GB", "TB")


def format_bytes(size) -> str:
    value = float(max(0, size or 0))
    unit = 0
    while value >= 1024 and unit < len(_UNITS) - 1:
        value /= 1024
        unit += 1
    if unit == 0 or value >= 100:
        return f"{int(round(value))} {_UNITS[unit]}"
    return f"{value:.1f} {_UNITS[unit]}"


def format_minutes(minutes) -> str:
    total = max(0, int(minutes or 0))
    hours, rest = divmod(total, 60)
    if hours == 0:
        return f"{rest}m"
    return f"{hours:,}h" if rest == 0 else f"{hours:,}h {rest}m"


def format_uptime(seconds) -> str | None:
    if seconds is None:
        return None
    days, rest = divmod(int(seconds), 86400)
    hours = rest // 3600
    return f"{days}d {hours}h" if days else f"{hours}h"


def _share(used, total):
    return None if not total else round(100 * used / total)


def database_size(db) -> int | None:
    if db.get_bind().dialect.name != "postgresql":
        return None
    return db.execute(text("SELECT pg_database_size(current_database())")).scalar()


def usage_report(db, since=None) -> dict:
    """Every workspace not in the trash, with what it used since `since`."""
    since = since or month_start()
    workspaces = (
        db.query(Workspace)
        .options(joinedload(Workspace.creator))
        .filter(Workspace.trashed_at.is_(None))
        .all()
    )
    ids = [ws.id for ws in workspaces]
    sums = {}
    if ids:
        rows = (
            db.query(
                WorkspaceUsageHour.workspace_id,
                func.sum(WorkspaceUsageHour.active_minutes),
                func.sum(WorkspaceUsageHour.writes),
                func.sum(WorkspaceUsageHour.broadcasts),
                func.sum(WorkspaceUsageHour.broadcast_bytes),
            )
            .filter(
                WorkspaceUsageHour.workspace_id.in_(ids),
                WorkspaceUsageHour.hour_start >= since,
            )
            .group_by(WorkspaceUsageHour.workspace_id)
            .all()
        )
        sums = {row[0]: [int(value or 0) for value in row[1:]] for row in rows}
    storage = latest_storage(db, ids)

    entries = []
    for ws in workspaces:
        minutes, writes, broadcasts, sent = sums.get(ws.id, [0, 0, 0, 0])
        creator = ws.creator
        entries.append(
            {
                "slug": ws.slug,
                "owner": creator.email if creator else "unknown",
                "plan": (creator.tier or "free") if creator else "-",
                "suspended": not ws.is_active,
                "active_minutes": minutes,
                "writes": writes,
                "broadcasts": broadcasts,
                "sent_bytes": sent,
                "storage_bytes": storage.get(ws.id, 0),
            }
        )
    entries.sort(key=lambda e: (e["active_minutes"], e["storage_bytes"]), reverse=True)

    return {
        "since": since,
        "workspaces": entries,
        "totals": {
            "active_minutes": sum(e["active_minutes"] for e in entries),
            "writes": sum(e["writes"] for e in entries),
            "broadcasts": sum(e["broadcasts"] for e in entries),
            "sent_bytes": sum(e["sent_bytes"] for e in entries),
            "storage_bytes": sum(e["storage_bytes"] for e in entries),
            "active_workspaces": sum(1 for e in entries if e["active_minutes"] or e["writes"]),
        },
    }


def server_report(db) -> dict:
    """The machine, as numbers the page can show without further arithmetic."""
    stats = server_stats.snapshot()
    memory, disk = stats["memory"], stats["disk"]
    load = stats["load"]
    database = database_size(db)
    return {
        "cpus": stats["cpus"],
        "load": None if load is None else round(load, 2),
        "load_share": None if load is None else _share(load, stats["cpus"]),
        "memory": memory and {
            "used": format_bytes(memory["used"]),
            "total": format_bytes(memory["total"]),
            "share": _share(memory["used"], memory["total"]),
        },
        "disk": disk and {
            "used": format_bytes(disk["used"]),
            "total": format_bytes(disk["total"]),
            "free": format_bytes(disk["total"] - disk["used"]),
            "share": _share(disk["used"], disk["total"]),
        },
        "database": None if database is None else format_bytes(database),
        "uptime": format_uptime(stats["uptime_seconds"]),
    }


class UsageView(BaseView):
    """What every workspace used this month, and how busy the machine is."""

    name = "Usage"
    icon = "fa-solid fa-gauge-high"
    category = "Operations"
    category_icon = "fa-solid fa-screwdriver-wrench"
    template = "sqladmin/usage.html"

    def is_visible(self, request: Request) -> bool:
        return self._allowed(request)

    def is_accessible(self, request: Request) -> bool:
        return self._allowed(request)

    @staticmethod
    def _allowed(request: Request) -> bool:
        return roles.can_see(request.session.get(ROLE_KEY), "Workspace")

    @expose("/usage", methods=["GET"])
    async def usage(self, request: Request):
        """Render the usage page.

        The method name is load bearing. sqladmin names a custom view's route
        after its exposed method and the sidebar links to that name, so this
        cannot also be called ``page``, which the cleanup view already uses:
        the two would share a route name, the Usage link would open Cleanup,
        and both would show as selected.

        The role check is load bearing too, as on the cleanup page: sqladmin
        applies ``is_accessible`` to the menu entry only, not to an exposed
        route.
        """
        if not self._allowed(request):
            return Response("Forbidden", status_code=403)
        db = SessionLocal()
        try:
            report = usage_report(db)
            server = server_report(db)
        finally:
            db.close()
        return await self.templates.TemplateResponse(
            request,
            self.template,
            {
                "report": report,
                "server": server,
                "format_bytes": format_bytes,
                "format_minutes": format_minutes,
            },
        )
