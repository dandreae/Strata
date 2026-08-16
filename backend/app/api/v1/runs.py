"""/api/v1/runs — create and inspect optimization runs.

This is a placeholder route for this infrastructure pass: it persists run
*metadata* via RunRepository so the API/model shape is real and testable,
but does not yet trigger slicing or agent orchestration. STL file upload
(via StorageService) is also not wired to this endpoint yet — see
docs/architecture.md for the intended next step.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.deps import get_run_repository
from app.core.errors import NotFoundError
from app.models.api import CreateRunRequest, RunListResponse, RunResponse
from app.models.run import OptimizationRun
from app.services.repository import RunRepository, RunRepositoryError

router = APIRouter(prefix="/runs", tags=["runs"])


@router.post("", response_model=RunResponse, status_code=201)
async def create_run(
    payload: CreateRunRequest,
    repository: RunRepository = Depends(get_run_repository),
) -> RunResponse:
    run = OptimizationRun(
        filename=payload.filename,
        production_quantity=payload.production_quantity,
        printer_profile=payload.printer_profile,
        hard_constraints=payload.hard_constraints,
        optimization_preferences=payload.optimization_preferences,
    )
    created = repository.create_run(run)
    return RunResponse(**created.model_dump())


@router.get("", response_model=RunListResponse)
async def list_runs(repository: RunRepository = Depends(get_run_repository)) -> RunListResponse:
    runs = repository.list_runs()
    return RunListResponse(runs=[RunResponse(**r.model_dump()) for r in runs])


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(run_id: str, repository: RunRepository = Depends(get_run_repository)) -> RunResponse:
    try:
        run = repository.get_run(run_id)
    except RunRepositoryError as exc:
        raise NotFoundError(f"No run found with id={run_id}") from exc
    return RunResponse(**run.model_dump())
