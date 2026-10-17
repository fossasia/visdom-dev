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

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import heartbeat
from app.admin.activity import activity_per_instance, instance_addresses
from app.config import settings
from app.dependencies import get_db

router = APIRouter(prefix="/health", tags=["health"])

COMPONENT_TIMEOUT = 2.0


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
    if addresses:
        answered = sum(1 for _address, ok, _entries in activity_per_instance(COMPONENT_TIMEOUT) if ok)
        visdom_ok = answered == len(addresses)
        checks["visdom"] = f"{answered} of {len(addresses)} answering"
    else:
        visdom_ok = True
        checks["visdom"] = "no instances configured"

    metering_ok = True
    if database_ok:
        try:
            metering_ok, checks["metering"] = heartbeat.standing(
                db, heartbeat.USAGE, settings.USAGE_SAMPLE_SECONDS
            )
        except Exception:
            logging.exception("component health could not read the metering heartbeat")
            metering_ok, checks["metering"] = False, "unknown"

    healthy = database_ok and visdom_ok and metering_ok
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return {"status": "healthy" if healthy else "degraded", "checks": checks}
