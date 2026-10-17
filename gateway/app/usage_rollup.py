# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""Turn the instances' live counters into a durable hourly record.

What an instance reports is cumulative since that instance last started, so a
sample is worth only its difference from the one before. Three things make that
harder than it sounds, and each is handled here rather than left to chance.

The difference is taken per instance, never on a sum across them. A restart is
only visible in the instance that had it; on the sum it looks like every other
instance's total vanishing.

The last totals seen are kept in the database, per instance and workspace, so a
gateway restart or a different worker taking the next tick carries on from where
the last one stopped. A workspace seen for the first time is only given a
baseline: there is no way to know how much of its total was banked before.

Only one worker samples a given tick. The gateway runs several, each with its
own timer, and two of them folding the same interval would count it twice. A
Postgres advisory lock taken for the length of the tick's transaction decides
which one; the others skip. The instances are read after the lock is taken, so
the totals used are always at least as new as the baseline they are compared to.

Active minutes are not differenced. Each instance reports which minutes of an
hour had work in them as a mask, masks from different instances are unioned, and
the count lands on the hour the mask belongs to, keeping the highest seen.
"""

import datetime
import logging
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from app import heartbeat
from app.models import UsageBaseline, Workspace, WorkspaceUsageHour, utcnow

_COUNTERS = ("writes", "broadcasts", "broadcast_bytes")
_TICK_LOCK = 7234091


def hour_start(moment: datetime.datetime | None = None) -> datetime.datetime:
    """The top of the hour a moment belongs to."""
    moment = moment or utcnow()
    return moment.replace(minute=0, second=0, microsecond=0)


def hour_of(epoch_hour) -> datetime.datetime:
    """The top of an hour an instance names by its number since the epoch."""
    return datetime.datetime.fromtimestamp(int(epoch_hour) * 3600, tz=datetime.timezone.utc)


def active_minutes_from(mask) -> int:
    """How many minutes of an hour a mask says had work in them."""
    try:
        return int(mask).bit_count()
    except (TypeError, ValueError):
        return 0


def counter_delta(previous: int, current: int) -> int:
    """How much of one instance's cumulative counter is new since it was read."""
    if current < previous:
        return max(current, 0)
    return current - previous


def take_tick(db: Session) -> bool:
    """Whether this worker is the one to sample now."""
    if db.get_bind().dialect.name != "postgresql":
        return True
    granted = db.execute(
        text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": _TICK_LOCK}
    ).scalar()
    return bool(granted)


def _advance(db: Session, instance: str, workspace_id: str, entry: dict) -> dict:
    """Move one instance's baseline for one workspace on, returning what is new."""
    current = {name: int(entry.get(name) or 0) for name in _COUNTERS}
    baseline = db.get(UsageBaseline, {"instance": instance, "workspace_id": workspace_id})
    if baseline is None:
        db.add(UsageBaseline(instance=instance, workspace_id=workspace_id, **current))
        return dict.fromkeys(_COUNTERS, 0)
    new = {
        name: counter_delta(getattr(baseline, name) or 0, current[name])
        for name in _COUNTERS
    }
    for name in _COUNTERS:
        setattr(baseline, name, current[name])
    return new


def gather(db: Session, answers) -> dict:
    """Per workspace: new counts, the largest stored size, and the latest mask."""
    totals: dict = {}
    for instance, answered, entries in answers:
        if not answered:
            continue
        for entry in entries:
            workspace_id = entry.get("workspace_id")
            if not workspace_id:
                continue
            new = _advance(db, instance, workspace_id, entry)
            slot = totals.setdefault(
                workspace_id,
                {**dict.fromkeys(_COUNTERS, 0), "peak_bytes": 0, "hour": None, "mask": 0},
            )
            for name in _COUNTERS:
                slot[name] += new[name]
            slot["peak_bytes"] = max(slot["peak_bytes"], int(entry.get("bytes") or 0))
            hour = entry.get("active_hour")
            if hour is None:
                continue
            mask = int(entry.get("active_minutes_mask") or 0)
            if slot["hour"] is None or hour > slot["hour"]:
                slot["hour"], slot["mask"] = hour, mask
            elif hour == slot["hour"]:
                slot["mask"] |= mask
    return totals


def _as_uuid(value):
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (AttributeError, TypeError, ValueError):
        return None


def _row(db: Session, rows: dict, workspace_id, bucket) -> WorkspaceUsageHour:
    key = (workspace_id, bucket)
    if key in rows:
        return rows[key]
    row = (
        db.query(WorkspaceUsageHour)
        .filter(
            WorkspaceUsageHour.workspace_id == workspace_id,
            WorkspaceUsageHour.hour_start == bucket,
        )
        .first()
    )
    if row is None:
        row = WorkspaceUsageHour(
            workspace_id=workspace_id,
            hour_start=bucket,
            active_minutes=0,
            writes=0,
            broadcasts=0,
            broadcast_bytes=0,
            peak_bytes=0,
        )
        db.add(row)
    rows[key] = row
    return row


def record(db: Session, totals: dict, when: datetime.datetime | None = None) -> int:
    """Fold gathered totals into the hourly rows. Returns the workspaces folded."""
    wanted = {k: _as_uuid(k) for k in totals}
    ids = [v for v in wanted.values() if v is not None]
    if not ids:
        return 0
    known = {str(row_id) for (row_id,) in db.query(Workspace.id).filter(Workspace.id.in_(ids))}

    bucket = hour_start(when)
    rows: dict = {}
    folded = 0
    for workspace_id, slot in totals.items():
        as_uuid = wanted[workspace_id]
        if as_uuid is None or str(as_uuid) not in known:
            continue
        worked = any(slot[name] for name in _COUNTERS) or slot["peak_bytes"]
        minutes = active_minutes_from(slot["mask"])
        if not worked and not minutes:
            continue
        if worked:
            row = _row(db, rows, as_uuid, bucket)
            for name in _COUNTERS:
                setattr(row, name, (getattr(row, name) or 0) + slot[name])
            row.peak_bytes = max(row.peak_bytes or 0, slot["peak_bytes"])
        if minutes:
            row = _row(db, rows, as_uuid, hour_of(slot["hour"]))
            row.active_minutes = max(row.active_minutes or 0, minutes)
        folded += 1
    return folded


def sample_once(db: Session, answers_fn, when: datetime.datetime | None = None) -> int:
    """One tick: if this worker holds the tick, fold what the instances report."""
    if not take_tick(db):
        db.rollback()
        return 0
    try:
        answers = answers_fn()
    except Exception as exc:
        logging.warning("usage sample could not reach the instances: %s", exc)
        db.rollback()
        return 0
    folded = record(db, gather(db, answers), when=when)
    heartbeat.mark(db, heartbeat.USAGE)
    db.commit()
    return folded
