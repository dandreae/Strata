"""Aggregates all v1 routers under one APIRouter."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import runs

api_v1_router = APIRouter()
api_v1_router.include_router(runs.router)
