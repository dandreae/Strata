"""/api/v1/runs — create an optimization run and evaluate a candidate set.

`POST /api/v1/runs` accepts a real STL upload plus goal metadata, wires it
through the full multi-candidate optimization pipeline synchronously (see
app/services/orchestrator.py), and returns the run together with every
candidate tried, its real metrics, feasibility, Pareto-optimality, the
selected winner, and the decision record produced — including the planning
decision (which planner, how many candidates, why) recorded before slicing.
This is deliberately synchronous and single-round for this milestone — no
background jobs, no adaptive second round. See docs/architecture.md for
what replaces this once the adaptive agent loop exists.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.agent.interfaces import AgentPlanner
from app.api.deps import get_agent_planner, get_run_repository, get_slicer_service, get_storage_service
from app.core.errors import NotFoundError, ValidationFailedError
from app.models.api import (
    CandidateResponse,
    ConstraintCheckResponse,
    DecisionResponse,
    OptimizationSummaryResponse,
    RunDetailResponse,
    RunListResponse,
    RunResponse,
)
from app.models.candidate import CandidateConfiguration
from app.models.decision import DecisionRecord
from app.models.run import HardConstraints, OptimizationObjective, OptimizationPreferences, OptimizationRun
from app.optimization.constraints import evaluate_constraint_checks
from app.services.orchestrator import execute_optimization_run
from app.services.repository import RunRepository, RunRepositoryError
from app.services.storage import StorageService
from app.services.stl_validation import validate_stl
from app.slicer.base import SlicerService

router = APIRouter(prefix="/runs", tags=["runs"])


def _to_candidate_response(candidate: CandidateConfiguration, constraints: HardConstraints) -> CandidateResponse:
    checks = evaluate_constraint_checks(candidate, constraints)
    return CandidateResponse(
        **candidate.model_dump(exclude={"is_pareto_optimal", "is_selected"}),
        constraint_checks=[ConstraintCheckResponse(**vars(c)) for c in checks],
        is_feasible=bool(checks) and all(c.passed for c in checks),
        is_pareto_optimal=candidate.is_pareto_optimal,
        is_selected=candidate.is_selected,
    )


def _to_detail_response(
    run: OptimizationRun,
    candidates: list[CandidateConfiguration],
    decisions: list[DecisionRecord],
) -> RunDetailResponse:
    candidate_responses = [_to_candidate_response(c, run.hard_constraints) for c in candidates]
    return RunDetailResponse(
        **run.model_dump(),
        candidates=candidate_responses,
        decisions=[DecisionResponse(**d.model_dump()) for d in decisions],
        optimization_summary=OptimizationSummaryResponse(
            candidates_tested=len(candidate_responses),
            succeeded=sum(1 for c in candidate_responses if c.status.value == "succeeded"),
            feasible=sum(1 for c in candidate_responses if c.is_feasible),
            pareto_optimal=sum(1 for c in candidate_responses if c.is_pareto_optimal),
        ),
    )


@router.post("", response_model=RunDetailResponse, status_code=201)
async def create_run(
    file: Annotated[UploadFile, File(description="STL file to slice.")],
    production_quantity: Annotated[int, Form(gt=0)],
    printer_profile: Annotated[str, Form()],
    max_print_time_seconds: Annotated[int, Form(gt=0)],
    max_filament_grams: Annotated[float, Form(gt=0)],
    objective: Annotated[OptimizationObjective, Form()] = OptimizationObjective.BALANCED,
    repository: RunRepository = Depends(get_run_repository),
    storage: StorageService = Depends(get_storage_service),
    slicer: SlicerService = Depends(get_slicer_service),
    planner: AgentPlanner = Depends(get_agent_planner),
) -> RunDetailResponse:
    """Create a run, save the STL, plan a candidate set (see
    STRATA_PLANNER_MODE — deterministic or Gemini+ADK), slice it, and return
    the full result. This can take a while (planning plus several real
    PrusaSlicer invocations, each up to STRATA_PRUSASLICER_TIMEOUT_SECONDS)
    — expected to move to a background job before this grows further.
    """
    content = await file.read()
    errors = validate_stl(file.filename or "", content)
    if errors:
        raise ValidationFailedError("Uploaded file failed STL validation.", details={"errors": errors})

    run = OptimizationRun(
        filename=file.filename or "unnamed.stl",
        production_quantity=production_quantity,
        printer_profile=printer_profile,
        hard_constraints=HardConstraints(
            max_print_time_seconds=max_print_time_seconds,
            max_filament_grams=max_filament_grams,
        ),
        optimization_preferences=OptimizationPreferences(objective=objective),
    )
    repository.create_run(run)

    reference = storage.save_stl(run.id, run.filename, content)
    run.model_reference = reference
    repository.update_run(run)

    stl_path = storage.get_artifact_path(reference)
    execute_optimization_run(run, stl_path, repository=repository, storage=storage, slicer=slicer, planner=planner)

    candidates = repository.list_candidates(run.id)
    decisions = repository.list_decisions(run.id)
    return _to_detail_response(run, candidates, decisions)


@router.get("", response_model=RunListResponse)
async def list_runs(repository: RunRepository = Depends(get_run_repository)) -> RunListResponse:
    runs = repository.list_runs()
    return RunListResponse(runs=[RunResponse(**r.model_dump()) for r in runs])


@router.get("/{run_id}", response_model=RunDetailResponse)
async def get_run(run_id: str, repository: RunRepository = Depends(get_run_repository)) -> RunDetailResponse:
    try:
        run = repository.get_run(run_id)
    except RunRepositoryError as exc:
        raise NotFoundError(f"No run found with id={run_id}") from exc
    candidates = repository.list_candidates(run_id)
    decisions = repository.list_decisions(run_id)
    return _to_detail_response(run, candidates, decisions)
