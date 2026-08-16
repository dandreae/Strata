"""Liveness/readiness endpoint."""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(tags=["health"])


class HealthResponse(BaseModel):
    status: str = "ok"
    app_name: str
    environment: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    from app.core.config import get_settings

    settings = get_settings()
    return HealthResponse(app_name=settings.app_name, environment=settings.environment)
