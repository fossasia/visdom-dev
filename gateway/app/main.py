"""
Main FastAPI entrypoint. Mounts routers and configures CORS.
"""

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import account_deletion, retention, usage_rollup
from app.admin import mount_admin
from app.admin.activity import activity_per_instance
from app.config import settings
from app.database import SessionLocal
from app.routers import api_keys, auth, billing, health, usage, visdom, workspaces

FIRST_TICK_SECONDS = 300


async def _sample_usage_forever(seconds: int) -> None:
    """Bank what the instances have counted, on a tick.

    Their counters live in memory and go with them, so the interval is how much
    usage a restart can cost. It is also a fan-out to every instance, which is
    why this is a tick rather than something done per request.
    """
    while True:
        await asyncio.sleep(seconds)
        db = SessionLocal()
        try:
            await asyncio.to_thread(usage_rollup.sample_once, db, activity_per_instance)
        except Exception:
            logging.exception("usage sample failed")
            db.rollback()
        finally:
            db.close()


async def _sweep_retention_forever(hours: int) -> None:
    """Remove what the plans no longer keep, on a slow tick.

    Slow because nothing here is urgent: a plan that keeps seven days is not
    broken by keeping seven days and an hour. One worker does it, the same way
    the usage tick does, though under a lock of its own, since several workers
    sweeping the same workspaces at once would each ask every instance for the
    same answer.

    The first sweep comes a few minutes after start-up rather than a full
    interval later, so a gateway restarted more often than that still sweeps.
    """
    delay = FIRST_TICK_SECONDS
    while True:
        await asyncio.sleep(delay)
        delay = hours * 3600
        try:
            summary = await asyncio.to_thread(retention.sweep_once)
            if summary and summary["with_expired"]:
                logging.info(
                    "retention swept %d workspace(s), removed %d env(s)%s",
                    summary["with_expired"],
                    summary["removed"],
                    "" if retention.enforcing() else " (reporting only)",
                )
        except Exception:
            logging.exception("retention sweep failed")


async def _delete_accounts_forever(hours: int) -> None:
    """Remove the accounts whose waiting period has run out, on a slow tick.

    Under a lock of its own, held for the whole run, and first run a few
    minutes after start-up, the same as the retention sweep.
    """
    delay = FIRST_TICK_SECONDS
    while True:
        await asyncio.sleep(delay)
        delay = hours * 3600
        try:
            erased = await asyncio.to_thread(account_deletion.erase_once)
            if erased:
                logging.info("deleted %d account(s) at the end of their waiting period", erased)
        except Exception:
            logging.exception("account deletion tick failed")


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    seconds = settings.USAGE_SAMPLE_SECONDS
    hours = settings.RETENTION_SWEEP_HOURS
    tasks = []
    if seconds > 0:
        tasks.append(asyncio.create_task(_sample_usage_forever(seconds)))
    if hours > 0:
        tasks.append(asyncio.create_task(_sweep_retention_forever(hours)))
    if settings.ACCOUNT_DELETION_HOURS > 0:
        tasks.append(asyncio.create_task(_delete_accounts_forever(settings.ACCOUNT_DELETION_HOURS)))
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="Visdom Gateway",
    description="Microservice authentication sidecar for Visdom",
    version="1.0.0",
    lifespan=lifespan,
)


# CORS middleware configuration, origin sourced from env (FRONTEND_URL)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Mount all endpoint routers
app.include_router(auth.router, prefix="/api/v1")
app.include_router(api_keys.router, prefix="/api/v1")
app.include_router(health.router, prefix="/api/v1")
app.include_router(workspaces.router, prefix="/api/v1")
app.include_router(billing.router, prefix="/api/v1")
app.include_router(usage.router, prefix="/api/v1")
app.include_router(visdom.router, prefix="/api/v1")


if settings.ADMIN_ENABLED:
    if not settings.ADMIN_SECRET:
        raise RuntimeError("ADMIN_ENABLED is set but ADMIN_SECRET is empty")
    mount_admin(app, settings.ADMIN_SECRET)
