"""CandidateConfiguration: one proposed set of slicer parameters plus its result.

The MVP intentionally restricts the optimization search space to the six
variables below (see project scope). Additional variables can be added later
without breaking the shape of this model.
"""

from __future__ import annotations

from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


class CandidateStatus(StrEnum):
    PENDING = "pending"
    SLICING = "slicing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class CandidateConfiguration(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str

    # --- MVP optimization variables ---
    orientation_x: float = Field(default=0.0, description="Rotation about X axis, degrees.")
    orientation_y: float = Field(default=0.0, description="Rotation about Y axis, degrees.")
    orientation_z: float = Field(default=0.0, description="Rotation about Z axis, degrees.")
    layer_height: float = Field(gt=0, description="Layer height in millimeters.")
    infill_percent: int = Field(ge=0, le=100, description="Infill density percentage.")
    supports_enabled: bool = False
    perimeter_count: int = Field(gt=0, description="Number of perimeter/wall loops.")

    # --- Result, populated after slicing ---
    status: CandidateStatus = CandidateStatus.PENDING
    print_time_seconds: int | None = None
    filament_grams: float | None = None
    slicer_output_path: str | None = None
    failure_reason: str | None = None

    # --- Cross-candidate comparison, populated after the whole cohort in a
    # run has been sliced and evaluated (app/services/orchestrator.py).
    # Both are derived/denormalized for API convenience — the frontend
    # should never need to recompute dominance or re-run selection itself.
    is_pareto_optimal: bool = Field(
        default=False, description="True if no other feasible candidate in this run dominates this one."
    )
    is_selected: bool = Field(
        default=False, description="True if this is the candidate the run's DecisionRecord selected."
    )
