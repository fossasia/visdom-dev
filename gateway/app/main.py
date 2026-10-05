"""
Main FastAPI entrypoint. Mounts routers and configures CORS.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers import api_keys, auth, billing, health, visdom, workspaces

app = FastAPI(
    title="Visdom Gateway",
    description="Microservice authentication sidecar for Visdom",
    version="0.1.0"
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
app.include_router(visdom.router, prefix="/api/v1")
