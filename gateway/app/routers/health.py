# Copyright 2017-present, The Visdom Authors
# All rights reserved.
#
# This source code is licensed under the license found in the
# LICENSE file in the root directory of this source tree.


"""
Health check router to verify the status of the gateway and its database connectin.
"""

# pyrefly: ignore [missing-import]

import logging
import os
import time

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import heartbeat
from app.admin.activity import (
    activity_per_instance,
    certificate_days_left,
    instance_addresses,
    internal_setup_problem,
)
from app.config import settings
from app.dependencies import get_db

router = APIRouter(prefix="/health", tags=["health"])

COMPONENT_TIMEOUT = 2.0
CERTIFICATE_WARNING_DAYS = 30
SLOW_ANSWER_SECONDS = 1.0
LOAD_WARNING_PER_CORE = 1.0


def load_per_core():
    try:
        return os.getloadavg()[1] / (os.cpu_count() or 1)
    except (AttributeError, OSError):
        return None


@router.get("", status_code=status.HTTP_200_OK)
def health_check(db: Session = Depends(get_db)):
    """Verifies that the gateway is operations and the PostgreSQL database is online.

    The failure is logged rather than returned. This endpoint is public, and a
    driver's own message names the host and the user it tried to connect as.
    """
    try:
        db.execute(text("SELECT 1"))
        return {
            "status": "healthy",
            "database": "connected"
        }
    except Exception as e:
        logging.exception("health check could not reach the database")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed."
        ) from e


@router.get("/components")
def component_health(response: Response, db: Session = Depends(get_db)):
    """Every part the product needs, not only the one answering this request.

    ``/health`` says the gateway and its database are up, which is what an
    uptime check wants to poll often. It stays green while every visdom
    instance is down, and a deployment in that state serves the console and no
    plots at all. This asks the instances too, and answers 503 when any part is
    unhealthy, so the same uptime check catches the half-broken stack.

    Metering is one of the parts. A sampler that has stopped loses usage for
    good and shows nowhere else, so it is checked here by how long ago it last
    finished a run.
    """
    checks = {}

    try:
        db.execute(text("SELECT 1"))
        database_ok = True
        checks["database"] = "ok"
    except Exception:
        logging.exception("component health could not reach the database")
        database_ok = False
        checks["database"] = "unreachable"

    addresses = instance_addresses()
    speed_ok = True
    if addresses:
        started = time.monotonic()
        answered = sum(1 for _address, ok, _entries in activity_per_instance(COMPONENT_TIMEOUT) if ok)
        took = time.monotonic() - started
        visdom_ok = answered == len(addresses)
        checks["visdom"] = f"{answered} of {len(addresses)} answering"
        if visdom_ok:
            checks["visdom_speed"] = f"answered in {took * 1000:.0f} ms"
            if took >= SLOW_ANSWER_SECONDS:
                speed_ok = False
                logging.warning("visdom took %.1f seconds to answer the health check", took)
    else:
        visdom_ok = True
        checks["visdom"] = "no instances configured"

    load_ok = True
    per_core = load_per_core()
    if per_core is None:
        checks["load"] = "unknown"
    else:
        checks["load"] = f"{per_core:.2f} per core over 5 minutes"
        if per_core >= LOAD_WARNING_PER_CORE:
            load_ok = False
            logging.warning("the machine has been overloaded, %.2f per core over 5 minutes", per_core)

    setup_problem = internal_setup_problem() if addresses else None
    if setup_problem:
        checks["internal_setup"] = setup_problem

    certificate_ok = True
    readings = [certificate_days_left(a, COMPONENT_TIMEOUT) for a in addresses]
    days_left = [days for days in readings if days is not None]
    unread = len(readings) - len(days_left)
    if unread:
        certificate_ok = False
        checks["internal_certificate"] = f"could not be read on {unread} of {len(readings)}"
    elif days_left:
        soonest = min(days_left)
        checks["internal_certificate"] = f"{int(soonest)} days left"
        if soonest < CERTIFICATE_WARNING_DAYS:
            certificate_ok = False
            logging.warning("the internal certificate expires in %d days", int(soonest))

    metering_ok = True
    if database_ok:
        try:
            metering_ok, checks["metering"] = heartbeat.standing(
                db, heartbeat.USAGE, settings.USAGE_SAMPLE_SECONDS
            )
        except Exception:
            logging.exception("component health could not read the metering heartbeat")
            metering_ok, checks["metering"] = False, "unknown"

    healthy = (
        database_ok and visdom_ok and speed_ok and load_ok and metering_ok and certificate_ok and not setup_problem
    )
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "healthy" if healthy else "degraded", "checks": checks}
