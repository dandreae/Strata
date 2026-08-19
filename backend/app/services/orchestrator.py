"""Bounded adaptive optimization pipeline: planner-proposed candidates,
sliced for real, evaluated deterministically, over at most two rounds.

    Round 1: Planner.plan_initial_candidates() [app/agent/*]
        -> up to 8 CandidateConfigurations (validated; see planner_validation.py)
        -> PrusaSlicerService, once per candidate, sequentially
        -> parse real metrics per candidate

    Round 2 (adaptive, optional): Planner.plan_next_round(), given Round 1's
    real measured results (config, real time/material, feasibility, Pareto
    status) — one call decides stop-vs-continue AND (if continuing) proposes
    up to 8 new, unique, bounded candidates in the same response.
        -> if continuing: validated (rejecting duplicates of Round 1 too),
           sliced exactly like Round 1

    Combined evaluation (always over the full candidate pool, regardless of
    how many rounds ran):
        -> constraint evaluation per candidate (app/optimization/constraints.py)
        -> Pareto frontier over ALL feasible candidates (app/optimization/pareto.py)
        -> preference-based winner selection (app/optimization/selection.py)
        -> DecisionRecords: one per round's planning decision, one final

Which planner runs is an injected `AgentPlanner` (see app/agent/factory.py
and STRATA_PLANNER_MODE) — this module doesn't know or care whether
candidates came from the fixed deterministic set or a real Gemini call; it
only knows how to turn validated candidate lists into measured, evaluated,
decided-upon results. That's deliberate: no LLM involvement anywhere below
"here are some candidates" (constraint checking, Pareto, selection,
decision record) — see docs/architecture.md's validation boundary.

Hard bounds, enforced by construction (not a loop with a counter — there are
exactly two sequential round blocks below, so a third round is structurally
impossible): at most 2 rounds, at most 8 candidates per round, at most 1
planner call per round. A Round 2 failure (call error, or nothing usable
proposed) never aborts the run and never falls back to a different planner
— Round 1's real results already stand on their own; the failure is simply
recorded in the decision ledger and the run finalizes on Round 1 alone.

Every number in the resulting `CandidateConfiguration`/`DecisionRecord`
comes from an actual `SliceResult` — this module never invents a print time
or filament weight, and never lets one candidate's slicing failure silently
take down candidates that could still be tested.
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from app.agent.interfaces import AgentPlanner, PlannerError, PlannerResult, RoundDecision
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

DEFAULT_CANDIDATE_COUNT = 8
MAX_ROUNDS = 2  # documentation of the bound; enforced structurally below, not by a counter.


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
    planner: AgentPlanner | None = None,
    candidate_count: int = DEFAULT_CANDIDATE_COUNT,
    candidates: list[CandidateConfiguration] | None = None,
) -> OptimizationRunResult:
    """Plan, slice, and evaluate up to two rounds of candidates, and select
    a winner over the combined pool.

    Mutates and persists `run` (status transitions PENDING -> RUNNING ->
    one of COMPLETED / INFEASIBLE / NEEDS_HUMAN_INPUT / FAILED) and every
    candidate via `repository`, independently, as each result becomes known
    — a caller re-reading the repository mid-run sees real partial progress.

    Pass `candidates` to bypass planning (and the adaptive round 2) entirely
    — tests use this with a fixed list, exactly like before this milestone.
    Otherwise `planner` is required: round 1 comes from
    `plan_initial_candidates`, and — unconditionally, regardless of planner
    type, since it's a single cheap/instant call for `DeterministicPlanner`
    — round 2 is offered via `plan_next_round` once round 1 has at least one
    real result.

    Never raises for expected failure modes — those are captured in
    candidates/decisions and returned normally so the API layer never has to
    turn them into a 500. One candidate failing to slice does not abort the
    run; only a run-level fatal condition does (no slicer available, every
    Round 1 candidate failed to slice, or Round 1 planning itself failed).
    """
    run.status = RunStatus.RUNNING
    repository.update_run(run)

    adaptive = candidates is None
    if adaptive and planner is None:
        raise ValueError("execute_optimization_run requires either `candidates` or `planner`.")

    # --- Round 1 ---
    if adaptive:
        try:
            planner_result = planner.plan_initial_candidates(run, candidate_count)
        except PlannerError as exc:
            logger.warning("round 1 planning failed", extra={"context": {"run_id": run.id, "error": str(exc)}})
            return _finish_run_planning_failed(run, repository, message=str(exc))

        repository.save_decision(_planning_decision(run, planner_result))
        round1_candidates = planner_result.candidates
    else:
        round1_candidates = candidates

    for candidate in round1_candidates:
        repository.save_candidate(candidate)

    for candidate in round1_candidates:
        try:
            _slice_and_apply(candidate, stl_path, run, storage, slicer)
        except SlicerUnavailableError as exc:
            logger.warning("slicer unavailable", extra={"context": {"run_id": run.id, "error": str(exc)}})
            return _finish_run_aborted(run, round1_candidates, repository, message=str(exc))
        repository.save_candidate(candidate)

    all_candidates = list(round1_candidates)
    succeeded = [c for c in all_candidates if c.status == CandidateStatus.SUCCEEDED]
    if not succeeded:
        logger.warning("all round 1 candidates failed to slice", extra={"context": {"run_id": run.id}})
        return _finish_run_no_usable_results(run, all_candidates, repository)

    rounds_run = 1

    # --- Round 2 (adaptive only; never fatal — see module docstring) ---
    if adaptive:
        round2_candidates = _run_round_two(
            run, planner, all_candidates, candidate_count, stl_path, repository, storage, slicer
        )
        if round2_candidates:
            all_candidates.extend(round2_candidates)
            succeeded = [c for c in all_candidates if c.status == CandidateStatus.SUCCEEDED]
            rounds_run = 2

    # --- Combined evaluation, over the full pool regardless of round count ---
    feasible = filter_feasible(succeeded, run.hard_constraints)
    frontier = pareto_frontier(feasible)
    frontier_ids = {c.id for c in frontier}
    for candidate in feasible:
        candidate.is_pareto_optimal = candidate.id in frontier_ids
        repository.save_candidate(candidate)

    if not feasible:
        return _finish_run_infeasible(run, all_candidates, succeeded, repository, rounds_run)

    selection = select_winner(feasible, run.optimization_preferences)
    if selection.winner is not None:
        selection.winner.is_selected = True
        repository.save_candidate(selection.winner)

    decision = _build_decision(run, all_candidates, succeeded, feasible, frontier, selection, rounds_run)
    repository.save_decision(decision)

    run.status = RunStatus.NEEDS_HUMAN_INPUT if selection.requires_human else RunStatus.COMPLETED
    repository.update_run(run)

    return OptimizationRunResult(run=run, candidates=all_candidates, decision=decision)


def _run_round_two(
    run: OptimizationRun,
    planner: AgentPlanner,
    round1_candidates: list[CandidateConfiguration],
    candidate_count: int,
    stl_path: Path,
    repository: RunRepository,
    storage: StorageService,
    slicer: SlicerService,
) -> list[CandidateConfiguration]:
    """Ask the planner whether to run a second round; if so, slice its new
    candidates. Never aborts the whole run: a Round 2 failure at any stage
    (call error, nothing usable proposed, slicer becoming unavailable) just
    means the run finalizes with Round 1's already-real results, with the
    reason recorded plainly in the decision ledger — not silently discarded,
    and never a fallback to a different planner.
    """
    try:
        round_decision = planner.plan_next_round(run, round1_candidates, candidate_count)
    except PlannerError as exc:
        logger.warning("round 2 planning failed", extra={"context": {"run_id": run.id, "error": str(exc)}})
        repository.save_decision(_round_two_unavailable_decision(run, message=str(exc)))
        return []

    repository.save_decision(_round_two_decision(run, round_decision))

    if not round_decision.should_continue or not round_decision.candidates:
        return []

    round2_candidates = round_decision.candidates
    for candidate in round2_candidates:
        repository.save_candidate(candidate)

    for i, candidate in enumerate(round2_candidates):
        try:
            _slice_and_apply(candidate, stl_path, run, storage, slicer)
        except SlicerUnavailableError as exc:
            logger.warning(
                "slicer became unavailable during round 2", extra={"context": {"run_id": run.id, "error": str(exc)}}
            )
            for remaining in round2_candidates[i:]:
                remaining.status = CandidateStatus.FAILED
                remaining.failure_reason = str(exc)
                repository.save_candidate(remaining)
            break
        repository.save_candidate(candidate)

    return round2_candidates


def _slice_and_apply(
    candidate: CandidateConfiguration,
    stl_path: Path,
    run: OptimizationRun,
    storage: StorageService,
    slicer: SlicerService,
) -> None:
    """Slice one candidate and mutate it in place with the result.

    Raises `SlicerUnavailableError` unchanged — that's a fatal condition the
    caller handles (differently depending on which round it happened in —
    see callers). Any other slicing problem (nonzero exit, timeout, no
    G-code) is captured on the candidate itself, not raised.
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
        f"round {candidate.round} / layer {candidate.layer_height}mm / infill {candidate.infill_percent}% / "
        f"{candidate.perimeter_count} perimeters"
    )


def _planning_decision(run: OptimizationRun, planner_result: PlannerResult) -> DecisionRecord:
    """Audit entry for what the planner proposed in Round 1, recorded
    before any slicing happens. Never contains raw model chain-of-thought —
    only the planner's own concise `planning_summary` plus a note about
    anything deterministic validation rejected."""
    evidence = [planner_result.planning_summary] if planner_result.planning_summary else []
    if planner_result.rejected_proposals:
        evidence.append(
            f"{len(planner_result.rejected_proposals)} proposed candidate(s) were rejected by "
            "deterministic validation: " + "; ".join(planner_result.rejected_proposals)
        )

    return DecisionRecord(
        run_id=run.id,
        observation=(
            f"Planner '{planner_result.planner_name}' proposed "
            f"{len(planner_result.candidates)} candidate(s) for the first experiment round."
        ),
        alternatives=[],
        evidence=evidence,
        selected_action="plan_initial_candidates",
        outcome=planner_result.planning_summary or None,
        requires_human=False,
    )


def _round_two_decision(run: OptimizationRun, decision: RoundDecision) -> DecisionRecord:
    """Audit entry for the planner's Round 2 stop/continue decision — the
    core visibility requirement for the adaptive loop: why did it stop, or
    why did it continue. Never contains chain-of-thought, only the
    planner's own concise `reasoning_summary`."""
    evidence = [decision.reasoning_summary] if decision.reasoning_summary else []
    if decision.rejected_proposals:
        evidence.append(
            f"{len(decision.rejected_proposals)} proposed candidate(s) were rejected by deterministic "
            "validation: " + "; ".join(decision.rejected_proposals)
        )

    if decision.should_continue:
        observation = (
            f"Planner '{decision.planner_name}' decided to continue after Round 1, proposing "
            f"{len(decision.candidates)} new candidate(s) for Round 2."
        )
        action = "continue_optimization"
    else:
        observation = f"Planner '{decision.planner_name}' decided to stop after Round 1."
        action = "stop_optimization"

    return DecisionRecord(
        run_id=run.id,
        observation=observation,
        alternatives=[],
        evidence=evidence,
        selected_action=action,
        outcome=decision.reasoning_summary or None,
        requires_human=False,
    )


def _round_two_unavailable_decision(run: OptimizationRun, *, message: str) -> DecisionRecord:
    """Round 2 planning itself failed (network/auth/malformed output) —
    recorded plainly; the run still finalizes on Round 1's real results."""
    return DecisionRecord(
        run_id=run.id,
        observation="Round 2 planning failed; proceeding with Round 1 results only.",
        alternatives=[],
        evidence=[message],
        selected_action="round_two_unavailable",
        outcome=message,
        requires_human=False,
    )


def _finish_run_planning_failed(
    run: OptimizationRun,
    repository: RunRepository,
    *,
    message: str,
) -> OptimizationRunResult:
    """Round 1 planning itself failed (e.g. Gemini call errored) — no
    candidates were ever proposed, so there is nothing to slice. Unlike a
    Round 2 failure, this IS fatal: there is no prior round to fall back on."""
    decision = DecisionRecord(
        run_id=run.id,
        observation="Candidate planning failed before any slicing was attempted.",
        alternatives=[],
        evidence=[message],
        selected_action="abort_run",
        outcome=message,
        requires_human=False,
    )
    repository.save_decision(decision)

    run.status = RunStatus.FAILED
    repository.update_run(run)
    return OptimizationRunResult(run=run, candidates=[], decision=decision)


def _finish_run_aborted(
    run: OptimizationRun,
    candidates: list[CandidateConfiguration],
    repository: RunRepository,
    *,
    message: str,
) -> OptimizationRunResult:
    """PrusaSlicer itself is unavailable during Round 1 — no candidate can
    ever succeed."""
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
    """The slicer is available, but every Round 1 candidate failed to slice."""
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
    rounds_run: int,
) -> OptimizationRunResult:
    """Every candidate sliced, but none — across all rounds run — satisfy
    the user's hard constraints."""
    evidence = [
        f"Candidate ({_describe(c)}): " + "; ".join(constraint_violations(c, run.hard_constraints))
        for c in succeeded
    ]

    decision = DecisionRecord(
        run_id=run.id,
        observation=(
            f"{len(candidates)} configurations were evaluated across {rounds_run} round(s). "
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
    rounds_run: int,
) -> DecisionRecord:
    observation = (
        f"{len(candidates)} configurations were evaluated across {rounds_run} round(s). "
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
