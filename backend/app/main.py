"""Strata backend entrypoint.

Run locally with:
    uvicorn app.main:app --reload
"""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health import router as health_router
from app.api.v1.router import api_v1_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.services.repository import InMemoryRunRepository
from app.services.storage import LocalStorageService
from app.slicer.prusaslicer import PrusaSlicerService

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    # Service wiring. Backend selection is read from settings so swapping in
    # cloud-backed implementations later is a config change, not a code
    # change at call sites (see docs/architecture.md).
    if settings.repository_backend != "memory":
        raise NotImplementedError(
            f"repository_backend={settings.repository_backend!r} is not implemented yet; use 'memory'."
        )
    if settings.storage_backend != "local":
        raise NotImplementedError(
            f"storage_backend={settings.storage_backend!r} is not implemented yet; use 'local'."
        )

    app.state.run_repository = InMemoryRunRepository()
    app.state.storage_service = LocalStorageService(settings.local_storage_dir)
    app.state.slicer_service = PrusaSlicerService(
        binary_path=settings.prusaslicer_binary_path,
        timeout_seconds=settings.prusaslicer_timeout_seconds,
    )

    logger.info(
        "strata backend starting",
        extra={"context": {"environment": settings.environment, "storage_backend": settings.storage_backend}},
    )
    yield
    logger.info("strata backend shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description="Autonomous manufacturing optimization agent for 3D printing.",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(health_router)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
