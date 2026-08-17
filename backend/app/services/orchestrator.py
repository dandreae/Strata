"""Deterministic multi-candidate optimization pipeline.

    STL -> StorageService
        -> generate_candidate_set() [app/agent/default_candidate.py]
        -> PrusaSlicerService, once per candidate, sequentially
        -> parse real metrics per candidate
        -> constraint evaluation per candidate (app/optimization/constraints.py)
        -> Pareto frontier over feasible candidates (app/optimization/pareto.py)
        -> preference-based winner selection (app/optimization/selection.py)
        -> one DecisionRecord summarizing the whole cohort

This is a deliberately narrow stand-in for the future agent loop described
in `app/agent/interfaces.py`: a small FIXED candidate set, no adaptive
second round, no LLM calls anywhere. When `AgentPlanner` is implemented, it
replaces `generate_candidate_set()` with an iterating, previous-result-aware
`propose_candidates()`; everything downstream of "here are some candidates
with real metrics" (constraint checking, Pareto, selection, decision
record) carries over unchanged — those stay deterministic on purpose (see
docs/architecture.md).

Every number in the resulting `CandidateConfiguration`/`DecisionRecord`
comes from an actual `SliceResult` — this module never invents a print time
or filament weight, and never lets one candidate's slicing failure silently
take down candidates that could still be tested.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.agent.default_candidate import generate_candidate_set
from app.core.logging import get_logger
from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.decision import DecisionRecord
from app.models.run import OptimizationRun, RunStatus
from app.optimization.constraints import constraint_violations, filter_feasible
from app.optimization.pareto import pareto_frontier
from app.optimization.selection import SelectionResult, select_winner
from app.services.repository import RunRepository
from app.services.storage import StorageService
from app.slicer.base import SlicerService, SlicerUnavailableError

logger = get_logger(__name__)


@dataclass(frozen=True)
class OptimizationRunResult:
    run: OptimizationRun
    candidates: list[CandidateConfiguration]
    decision: DecisionRecord


def execute_optimization_run(
    run: OptimizationRun,
    stl_path: Path,
    *,
    repository: RunRepository,
    storage: StorageService,
    slicer: SlicerService,
    candidates: list[CandidateConfiguration] | None = None,
) -> OptimizationRunResult:
    """Slice a small deterministic candidate set and select a winner.

    Mutates and persists `run` (status transitions PENDING -> RUNNING ->
    one of COMPLETED / INFEASIBLE / NEEDS_HUMAN_INPUT / FAILED) and every
    candidate via `repository`, independently, as each result becomes known
    — a caller re-reading the repository mid-run sees real partial progress.

    `candidates` defaults to `generate_candidate_set(run.id)`; tests may
    override it with a smaller/fixed list.

    Never raises for expected failure modes — those are captured in
    candidates/decision and returned normally so the API layer never has to
    turn them into a 500. One candidate failing to slice does not abort the
    run; only a run-level fatal condition does (no slicer available, or
    every candidate failed to slice).
    """
    candidates = candidates if candidates is not None else generate_candidate_set(run.id)
    for candidate in candidates:
        repository.save_candidate(candidate)

    run.status = RunStatus.RUNNING
    repository.update_run(run)

    for candidate in candidates:
        try:
            _slice_and_apply(candidate, stl_path, run, storage, slicer)
        except SlicerUnavailableError as exc:
            logger.warning("slicer unavailable", extra={"context": {"run_id": run.id, "error": str(exc)}})
            return _finish_run_aborted(run, candidates, repository, message=str(exc))
        repository.save_candidate(candidate)

    succeeded = [c for c in candidates if c.status == CandidateStatus.SUCCEEDED]
    if not succeeded:
        logger.warning("all candidates failed to slice", extra={"context": {"run_id": run.id}})
        return _finish_run_no_usable_results(run, candidates, repository)

    feasible = filter_feasible(succeeded, run.hard_constraints)
    frontier = pareto_frontier(feasible)
    frontier_ids = {c.id for c in frontier}
    for candidate in feasible:
        candidate.is_pareto_optimal = candidate.id in frontier_ids
        repository.save_candidate(candidate)

    if not feasible:
        return _finish_run_infeasible(run, candidates, succeeded, repository)

    selection = select_winner(feasible, run.optimization_preferences)
    if selection.winner is not None:
        selection.winner.is_selected = True
        repository.save_candidate(selection.winner)

    decision = _build_decision(run, candidates, succeeded, feasible, frontier, selection)
    repository.save_decision(decision)

    run.status = RunStatus.NEEDS_HUMAN_INPUT if selection.requires_human else RunStatus.COMPLETED
    repository.update_run(run)

    return OptimizationRunResult(run=run, candidates=candidates, decision=decision)


def _slice_and_apply(
    candidate: CandidateConfiguration,
    stl_path: Path,
    run: OptimizationRun,
    storage: StorageService,
    slicer: SlicerService,
) -> None:
    """Slice one candidate and mutate it in place with the result.

    Raises `SlicerUnavailableError` unchanged — that's a run-level fatal
    condition the caller handles, not a per-candidate one. Any other
    slicing problem (nonzero exit, timeout, no G-code) is captured on the
    candidate itself, not raised.
    """
    slice_result = slicer.slice(stl_path, run.printer_profile, candidate)  # may raise SlicerUnavailableError

    if not slice_result.success:
        candidate.status = CandidateStatus.FAILED
        candidate.failure_reason = slice_result.error or "Slicing failed for an unknown reason."
        return

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
        logger.warning(
            "slice succeeded with no gcode_path",
            extra={"context": {"run_id": run.id, "candidate_id": candidate.id}},
        )


def _describe(candidate: CandidateConfiguration) -> str:
    return (
        f"layer {candidate.layer_height}mm / infill {candidate.infill_percent}% / "
        f"{candidate.perimeter_count} perimeters"
    )


def _finish_run_aborted(
    run: OptimizationRun,
    candidates: list[CandidateConfiguration],
    repository: RunRepository,
    *,
    message: str,
) -> OptimizationRunResult:
    """PrusaSlicer itself is unavailable — no candidate can ever succeed."""
    for candidate in candidates:
        if candidate.status != CandidateStatus.SUCCEEDED:
            candidate.status = CandidateStatus.FAILED
            candidate.failure_reason = message
            repository.save_candidate(candidate)

    decision = DecisionRecord(
        run_id=run.id,
        observation="PrusaSlicer is not available in this environment.",
        alternatives=[],
        evidence=[message],
        selected_action="abort_run",
        outcome=message,
        requires_human=False,
    )
    repository.save_decision(decision)

    run.status = RunStatus.FAILED
    repository.update_run(run)
    return OptimizationRunResult(run=run, candidates=candidates, decision=decision)


def _finish_run_no_usable_results(
    run: OptimizationRun,
    candidates: list[CandidateConfiguration],
    repository: RunRepository,
) -> OptimizationRunResult:
    """The slicer is available, but every individual candidate failed to slice."""
    evidence = [f"Candidate ({_describe(c)}): {c.failure_reason}" for c in candidates]

    decision = DecisionRecord(
        run_id=run.id,
        observation=f"All {len(candidates)} candidates failed to slice.",
        alternatives=[],
        evidence=evidence,
        selected_action="abort_run",
        outcome="No candidate could be sliced successfully.",
        requires_human=False,
    )
    repository.save_decision(decision)

    run.status = RunStatus.FAILED
    repository.update_run(run)
    return OptimizationRunResult(run=run, candidates=candidates, decision=decision)


def _finish_run_infeasible(
    run: OptimizationRun,
    candidates: list[CandidateConfiguration],
    succeeded: list[CandidateConfiguration],
    repository: RunRepository,
) -> OptimizationRunResult:
    """Every candidate sliced, but none satisfy the user's hard constraints."""
    evidence = [
        f"Candidate ({_describe(c)}): " + "; ".join(constraint_violations(c, run.hard_constraints))
        for c in succeeded
    ]

    decision = DecisionRecord(
        run_id=run.id,
        observation=(
            f"{len(candidates)} configurations were evaluated. "
            f"{len(succeeded)} sliced successfully. "
            f"0 satisfied all hard constraints."
        ),
        alternatives=[],
        evidence=evidence,
        selected_action="no_feasible_candidate",
        outcome="No candidate satisfied all hard constraints.",
        requires_human=False,
    )
    repository.save_decision(decision)

    run.status = RunStatus.INFEASIBLE
    repository.update_run(run)
    return OptimizationRunResult(run=run, candidates=candidates, decision=decision)


def _build_decision(
    run: OptimizationRun,
    candidates: list[CandidateConfiguration],
    succeeded: list[CandidateConfiguration],
    feasible: list[CandidateConfiguration],
    frontier: list[CandidateConfiguration],
    selection: SelectionResult,
) -> DecisionRecord:
    observation = (
        f"{len(candidates)} configurations were evaluated. "
        f"{len(succeeded)} sliced successfully. "
        f"{len(feasible)} satisfied all hard constraints. "
        f"{len(frontier)} lie on the Pareto frontier."
    )

    if selection.winner is not None:
        winner = selection.winner
        alternatives = [_describe(c) for c in frontier if c.id != winner.id]
        evidence = [
            selection.reason,
            f"Selected candidate print time: {winner.print_time_seconds}s",
            f"Selected candidate filament usage: {winner.filament_grams}g",
        ]
        return DecisionRecord(
            run_id=run.id,
            observation=observation,
            alternatives=alternatives,
            evidence=evidence,
            selected_action="select_candidate",
            outcome=(
                f"Selected {_describe(winner)} "
                f"(preference: {run.optimization_preferences.objective.value})."
            ),
            requires_human=False,
        )

    # Balanced objective, multiple mutually non-dominated feasible candidates:
    # a genuine tradeoff select_winner correctly refuses to guess at.
    return DecisionRecord(
        run_id=run.id,
        observation=observation,
        alternatives=[_describe(c) for c in frontier],
        evidence=[selection.reason],
        selected_action="escalate_tradeoff",
        outcome=(
            "Multiple feasible candidates are mutually non-dominated and no optimization "
            "priority resolves the tradeoff; human input is required to choose."
        ),
        requires_human=True,
    )


__all__ = ["execute_optimization_run", "OptimizationRunResult"]
