"""Deterministic single-candidate run pipeline.

    STL -> StorageService -> one default CandidateConfiguration
    -> PrusaSlicerService -> parse real metrics -> constraint evaluation
    -> DecisionRecord

This is a deliberately narrow stand-in for the future multi-candidate agent
loop described in `app/agent/interfaces.py`: exactly one candidate, no
search, no LLM calls anywhere. When `AgentPlanner` is implemented, it
replaces `build_default_candidate()` + the single `slicer.slice()` call
below with an iterating `propose_candidates()` loop; the constraint
checking and decision-record plumbing here carries over unchanged.

Every number in the resulting `CandidateConfiguration`/`DecisionRecord`
comes from an actual `SliceResult` — this module never invents a print time
or filament weight.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.agent.default_candidate import build_default_candidate
from app.core.logging import get_logger
from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.decision import DecisionRecord
from app.models.run import OptimizationRun, RunStatus
from app.optimization.constraints import constraint_violations
from app.services.repository import RunRepository
from app.services.storage import StorageService
from app.slicer.base import SlicerService, SlicerUnavailableError

logger = get_logger(__name__)


@dataclass(frozen=True)
class SingleCandidateRunResult:
    run: OptimizationRun
    candidate: CandidateConfiguration
    decision: DecisionRecord


def execute_single_candidate_run(
    run: OptimizationRun,
    stl_path: Path,
    *,
    repository: RunRepository,
    storage: StorageService,
    slicer: SlicerService,
) -> SingleCandidateRunResult:
    """Run the full pipeline for one run against one default candidate.

    Mutates and persists `run` (status transitions PENDING -> RUNNING ->
    COMPLETED/FAILED) via `repository`. Never raises for expected failure
    modes (slicer unavailable, slicer failure, timeout, missing metrics) —
    those are captured in the candidate/decision and returned normally so
    the API layer never has to turn them into a 500.
    """
    candidate = build_default_candidate(run.id)
    repository.save_candidate(candidate)

    run.status = RunStatus.RUNNING
    repository.update_run(run)

    try:
        slice_result = slicer.slice(stl_path, run.printer_profile, candidate)
    except SlicerUnavailableError as exc:
        logger.warning("slicer unavailable", extra={"context": {"run_id": run.id, "error": str(exc)}})
        return _finish_failed(
            run, candidate, repository,
            observation="PrusaSlicer is not available in this environment.",
            selected_action="abort_run",
            message=str(exc),
        )

    if not slice_result.success:
        message = slice_result.error or "Slicing failed for an unknown reason."
        logger.warning("slice failed", extra={"context": {"run_id": run.id, "error": message}})
        return _finish_failed(
            run, candidate, repository,
            observation="Candidate slicing failed.",
            selected_action="reject_candidate",
            message=message,
        )

    candidate.print_time_seconds = slice_result.print_time_seconds
    candidate.filament_grams = slice_result.filament_grams
    candidate.status = CandidateStatus.SUCCEEDED

    if slice_result.gcode_path:
        gcode_file = Path(slice_result.gcode_path)
        try:
            candidate.slicer_output_path = storage.save_gcode(run.id, candidate.id, gcode_file.read_bytes())
        finally:
            # The slicer left its working directory on disk for us to read
            # from (see PrusaSlicerService.slice); we own cleaning it up now
            # that the G-code has been persisted via StorageService.
            shutil.rmtree(gcode_file.parent, ignore_errors=True)
    else:
        logger.warning("slice succeeded with no gcode_path", extra={"context": {"run_id": run.id}})

    violations = constraint_violations(candidate, run.hard_constraints)
    decision = _build_acceptance_decision(run, candidate, slice_result.warnings, violations)

    repository.save_candidate(candidate)
    repository.save_decision(decision)

    run.status = RunStatus.COMPLETED
    repository.update_run(run)

    return SingleCandidateRunResult(run=run, candidate=candidate, decision=decision)


def _finish_failed(
    run: OptimizationRun,
    candidate: CandidateConfiguration,
    repository: RunRepository,
    *,
    observation: str,
    selected_action: str,
    message: str,
) -> SingleCandidateRunResult:
    candidate.status = CandidateStatus.FAILED
    candidate.failure_reason = message
    repository.save_candidate(candidate)

    decision = DecisionRecord(
        run_id=run.id,
        observation=observation,
        alternatives=[],
        evidence=[message],
        selected_action=selected_action,
        outcome=message,
        requires_human=False,
    )
    repository.save_decision(decision)

    run.status = RunStatus.FAILED
    repository.update_run(run)
    return SingleCandidateRunResult(run=run, candidate=candidate, decision=decision)


def _build_acceptance_decision(
    run: OptimizationRun,
    candidate: CandidateConfiguration,
    warnings: list[str],
    violations: list[str],
) -> DecisionRecord:
    evidence = [
        f"Estimated print time: {candidate.print_time_seconds}s"
        if candidate.print_time_seconds is not None
        else "Estimated print time: unavailable (could not be parsed from G-code).",
        f"Filament usage: {candidate.filament_grams}g"
        if candidate.filament_grams is not None
        else "Filament usage: unavailable (could not be parsed from G-code).",
        *warnings,
    ]

    if violations:
        return DecisionRecord(
            run_id=run.id,
            observation="Candidate slicing completed successfully.",
            alternatives=[],
            evidence=[*evidence, *violations],
            selected_action="reject_candidate",
            outcome="Candidate does not satisfy hard constraints: " + "; ".join(violations),
            requires_human=False,
        )

    return DecisionRecord(
        run_id=run.id,
        observation="Candidate slicing completed successfully.",
        alternatives=[],
        evidence=evidence,
        selected_action="accept_candidate",
        outcome="Candidate satisfies all hard constraints.",
        requires_human=False,
    )


__all__ = ["execute_single_candidate_run", "SingleCandidateRunResult"]
