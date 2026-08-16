"""Request/response DTOs for the HTTP API.

Kept separate from the domain models (app.models.run, app.models.candidate)
so the wire format can evolve independently of internal representations.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.run import HardConstraints, OptimizationPreferences, RunStatus


class CreateRunRequest(BaseModel):
    """Metadata needed to start an optimization run.

    NOTE: this MVP pass only accepts run *metadata*. Actual STL file upload
    (via StorageService) is not yet wired to this endpoint — see
    docs/architecture.md for the intended next step.
    """

    filename: str
    production_quantity: int = Field(gt=0)
    printer_profile: str
    hard_constraints: HardConstraints
    optimization_preferences: OptimizationPreferences = Field(default_factory=OptimizationPreferences)


class RunResponse(BaseModel):
    id: str
    filename: str
    model_reference: str | None
    status: RunStatus
    production_quantity: int
    printer_profile: str
    hard_constraints: HardConstraints
    optimization_preferences: OptimizationPreferences
    created_at: datetime
    updated_at: datetime


class RunListResponse(BaseModel):
    runs: list[RunResponse]
