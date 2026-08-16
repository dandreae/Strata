"""FastAPI dependency providers.

Service singletons are created once at app startup (see app/main.py) and
stored on `app.state`; these dependency functions just retrieve them so
route handlers stay decoupled from *how* each service is constructed
(local filesystem today, GCS/Firestore later).
"""

from __future__ import annotations

from fastapi import Request

from app.services.repository import RunRepository
from app.services.storage import StorageService


def get_run_repository(request: Request) -> RunRepository:
    return request.app.state.run_repository


def get_storage_service(request: Request) -> StorageService:
    return request.app.state.storage_service
