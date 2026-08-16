"""OptimizationRun and its associated value objects.

An OptimizationRun represents one end-to-end user request: "produce N of
this part under these constraints, optimizing for X." It does not itself
contain slicing results — those live in CandidateConfiguration records
linked by `run_id`.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunStatus(StrEnum):
    """Lifecycle state of an optimization run.

    PENDING -> RUNNING -> one of {COMPLETED, INFEASIBLE, NEEDS_HUMAN_INPUT, FAILED}
    """

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    INFEASIBLE = "infeasible"
    NEEDS_HUMAN_INPUT = "needs_human_input"
    FAILED = "failed"


class OptimizationObjective(StrEnum):
    """User-declared optimization priority. Drives deterministic tie-breaking
    in app.optimization.selection — never inferred by the LLM."""

    MINIMIZE_MATERIAL = "minimize_material"
    MINIMIZE_TIME = "minimize_time"
    BALANCED = "balanced"


class HardConstraints(BaseModel):
    """Non-negotiable limits a candidate must satisfy to be feasible.

    Both fields are required: Strata's premise is that the user states
    outcomes ("under 3 hours, under 80g"), so a run without any limit at all
    is almost certainly a mistake at the API boundary rather than a valid
    "anything goes" request.
    """

    max_print_time_seconds: int = Field(gt=0, description="Hard ceiling on print time, in seconds.")
    max_filament_grams: float = Field(gt=0, description="Hard ceiling on filament usage, in grams.")


class OptimizationPreferences(BaseModel):
    """Soft guidance for choosing among feasible candidates."""

    objective: OptimizationObjective = OptimizationObjective.BALANCED


class OptimizationRun(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    filename: str = Field(description="Original uploaded STL filename.")
    model_reference: str | None = Field(
        default=None, description="Storage reference/path returned by StorageService for the uploaded STL."
    )
    status: RunStatus = RunStatus.PENDING
    production_quantity: int = Field(gt=0, description="Number of parts to produce.")
    printer_profile: str = Field(description="Identifier of the printer/profile to slice against.")
    hard_constraints: HardConstraints
    optimization_preferences: OptimizationPreferences = Field(default_factory=OptimizationPreferences)
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
