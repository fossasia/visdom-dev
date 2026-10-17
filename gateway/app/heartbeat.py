# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.

"""
Proof that a background job is still running.

The usage sampler only writes when a workspace did something, so an hour with
no rows could be a quiet hour or a sampler that died, and metering that stops
silently is usage nobody is ever billed for. Each run leaves a timestamp here,
which the health check reads.
"""

import datetime

from sqlalchemy.orm import Session

from app.models import Heartbeat, utcnow

USAGE = "usage"

STARTED = utcnow()


def mark(db: Session, name: str, when: datetime.datetime | None = None) -> None:
    """Record that the named job has just finished a run. The caller commits."""
    db.merge(Heartbeat(name=name, beat_at=when or utcnow()))


def last(db: Session, name: str) -> datetime.datetime | None:
    row = db.get(Heartbeat, name)
    if row is None:
        return None
    beat = row.beat_at
    return beat.replace(tzinfo=datetime.timezone.utc) if beat.tzinfo is None else beat


def standing(db: Session, name: str, every_seconds: int, now: datetime.datetime | None = None) -> tuple[bool, str]:
    """Whether the job is keeping up, and a phrase saying so.

    Five missed runs, or five minutes if that is longer, is the allowance. A
    restart misses a run or two, and an alert on every deploy would be ignored
    by the time a real one came. A job that has never run is given the same
    allowance from when this process started.
    """
    if every_seconds <= 0:
        return True, "off"
    now = now or utcnow()
    allowed = max(5 * every_seconds, 300)
    beat = last(db, name)
    if beat is None:
        waited = (now - STARTED).total_seconds()
        return (True, "waiting for the first run") if waited <= allowed else (False, "has never run")
    age = int((now - beat).total_seconds())
    if age <= allowed:
        return True, "ok"
    return False, f"last ran {age // 60} minutes ago"
