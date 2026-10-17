"""
Main FastAPI entrypoint. Mounts routers and configures CORS.
"""

import asyncio
import contextlib
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import usage_rollup
from app.admin import mount_admin
from app.admin.activity import activity_per_instance
from app.config import settings
from app.database import SessionLocal
from app.routers import api_keys, auth, billing, health, usage, visdom, workspaces


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


@contextlib.asynccontextmanager
async def lifespan(_app: FastAPI):
    seconds = settings.USAGE_SAMPLE_SECONDS
    tasks = []
    if seconds > 0:
        tasks.append(asyncio.create_task(_sample_usage_forever(seconds)))
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
