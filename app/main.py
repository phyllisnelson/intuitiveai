"""FastAPI application factory.

Usage:
    uvicorn app.main:app --reload         # development
    gunicorn -k uvicorn.workers.UvicornWorker app.main:app  # production
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

import httpx
import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1 import router as v1_router
from app.api.v1.endpoints.health import router as health_router
from app.core.config import get_settings
from app.core.handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestLoggingMiddleware

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — runs startup/shutdown logic once."""
    settings = get_settings()
    configure_logging(settings.log_level)
    log.info(
        "app.startup",
        name=settings.app_name,
        version=settings.app_version,
        region=settings.openstack_region_name,
        auth_url=settings.openstack_auth_url,
    )
    async with httpx.AsyncClient(timeout=10.0) as oidc_client:
        app.state.oidc_client = oidc_client
        yield
    log.info("app.shutdown")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="REST API for OpenStack VM lifecycle management",
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Tighten per environment in production.
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    register_exception_handlers(app)

    app.include_router(health_router)  # /health, /ready (no /api/v1 prefix)
    app.include_router(v1_router.router)

    @app.get("/", include_in_schema=False)
    async def root():
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "openapi": "/openapi.json",
        }

    return app


app = create_app()
