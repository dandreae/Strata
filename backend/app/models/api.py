"""Request/response DTOs for the HTTP API.

Kept separate from the domain models (app.models.run, app.models.candidate,
app.models.decision) so the wire format can evolve independently of internal
representations.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.models.candidate import CandidateStatus
from app.models.run import HardConstraints, OptimizationPreferences, RunStatus


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


class CandidateResponse(BaseModel):
    id: str
    orientation_x: float
    orientation_y: float
    orientation_z: float
    layer_height: float
    infill_percent: int
    supports_enabled: bool
    perimeter_count: int
    status: CandidateStatus
    print_time_seconds: int | None
    filament_grams: float | None
    slicer_output_path: str | None
    failure_reason: str | None


class DecisionResponse(BaseModel):
    id: str
    observation: str
    alternatives: list[str]
    evidence: list[str]
    selected_action: str
    confidence: float | None
    outcome: str | None
    requires_human: bool
    timestamp: datetime


class RunDetailResponse(RunResponse):
    """RunResponse plus the candidate(s) tried and the decision ledger so far.

    Returned by create/get so the frontend can render slicing status,
    metrics, constraint pass/fail, and the decision outcome from one call —
    see docs/architecture.md for the end-to-end pipeline this reflects.
    """

    candidates: list[CandidateResponse] = Field(default_factory=list)
    decisions: list[DecisionResponse] = Field(default_factory=list)
