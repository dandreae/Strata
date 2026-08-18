from __future__ import annotations

from pathlib import Path

import pytest

from app.agent.deterministic_planner import DeterministicPlanner
from app.agent.interfaces import PlannerError
from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.run import HardConstraints, OptimizationObjective, OptimizationPreferences, OptimizationRun, RunStatus
from app.models.slicer import SliceResult
from app.services.orchestrator import execute_optimization_run
from app.services.repository import InMemoryRunRepository
from app.services.storage import LocalStorageService
from tests.fakes import FakePlanner, FakeSlicerService


def _make_run(**overrides) -> OptimizationRun:
    defaults = dict(
        filename="part.stl",
        production_quantity=100,
        printer_profile="generic_pla",
        hard_constraints=HardConstraints(max_print_time_seconds=3 * 3600, max_filament_grams=80),
        optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.BALANCED),
    )
    defaults.update(overrides)
    return OptimizationRun(**defaults)


def _candidate(run_id: str, **overrides) -> CandidateConfiguration:
    defaults = dict(run_id=run_id, layer_height=0.2, infill_percent=20, perimeter_count=2)
    defaults.update(overrides)
    return CandidateConfiguration(**defaults)


def _fake_gcode(tmp_path: Path, name: str, text: str) -> Path:
    gcode_dir = tmp_path / f"fake-slice-{name}"
    gcode_dir.mkdir()
    path = gcode_dir / "out.gcode"
    path.write_text(text)
    return path


def _result(tmp_path: Path, name: str, *, time_s: int, grams: float) -> SliceResult:
    gcode_path = _fake_gcode(
        tmp_path,
        name,
        f"; estimated printing time (normal mode) = {time_s // 3600}h {time_s % 3600 // 60}m {time_s % 60}s\n"
        f"; filament used [g] = {grams}\n",
    )
    return SliceResult(success=True, print_time_seconds=time_s, filament_grams=grams, gcode_path=str(gcode_path))


def _setup(tmp_path: Path):
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")
    return repository, storage, stl_path


# --- multi-candidate happy path --------------------------------------------


def test_all_candidates_attempted_and_persisted_independently(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20, 0.25)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "a", time_s=1000, grams=4.0),
            _result(tmp_path, "b", time_s=900, grams=4.5),
            _result(tmp_path, "c", time_s=1200, grams=3.5),
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    assert len(result.candidates) == 3
    assert all(c.status == CandidateStatus.SUCCEEDED for c in result.candidates)
    assert {c.print_time_seconds for c in result.candidates} == {1000, 900, 1200}
    assert len(slicer.calls) == 3

    stored = repository.list_candidates(run.id)
    assert len(stored) == 3


def test_one_candidate_slicing_failure_does_not_kill_the_run(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20, 0.25)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "a", time_s=1000, grams=4.0),
            SliceResult(success=False, error="prusa-slicer exited with code 1"),
            _result(tmp_path, "c", time_s=1200, grams=3.5),
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    statuses = [c.status for c in result.candidates]
    assert statuses == [CandidateStatus.SUCCEEDED, CandidateStatus.FAILED, CandidateStatus.SUCCEEDED]
    assert result.candidates[1].failure_reason == "prusa-slicer exited with code 1"
    # The run still completes and selects among the two that succeeded.
    assert result.run.status in (RunStatus.COMPLETED, RunStatus.NEEDS_HUMAN_INPUT)


# --- feasibility -------------------------------------------------------


def test_feasible_and_infeasible_candidates_classified_correctly(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run(hard_constraints=HardConstraints(max_print_time_seconds=1100, max_filament_grams=5))
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "feasible", time_s=1000, grams=4.0),
            _result(tmp_path, "infeasible", time_s=1500, grams=9.0),  # violates both
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    feasible_ids = {c.id for c in result.candidates if c.print_time_seconds == 1000}
    assert feasible_ids == {candidates[0].id}
    # The infeasible candidate is never marked Pareto-optimal or selected.
    infeasible = next(c for c in result.candidates if c.id == candidates[1].id)
    assert infeasible.is_pareto_optimal is False
    assert infeasible.is_selected is False


# --- Pareto marking ------------------------------------------------------


def test_dominated_candidate_is_not_marked_pareto_optimal(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20, 0.25)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "dominant", time_s=900, grams=3.0),
            _result(tmp_path, "dominated", time_s=1200, grams=5.0),  # worse on both axes
            _result(tmp_path, "tradeoff", time_s=800, grams=6.0),  # faster, more material: tradeoff
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    by_time = {c.print_time_seconds: c for c in result.candidates}
    assert by_time[900].is_pareto_optimal is True
    assert by_time[1200].is_pareto_optimal is False
    assert by_time[800].is_pareto_optimal is True


# --- selection -------------------------------------------------------


def test_minimize_material_selects_lowest_material_feasible_candidate(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run(optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_MATERIAL))
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20, 0.25)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "a", time_s=1000, grams=4.0),
            _result(tmp_path, "b", time_s=900, grams=3.0),  # lowest material
            _result(tmp_path, "c", time_s=1200, grams=5.0),
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    winner = next(c for c in result.candidates if c.is_selected)
    assert winner.filament_grams == 3.0
    assert winner.id == candidates[1].id
    assert result.decision.selected_action == "select_candidate"
    assert result.run.status == RunStatus.COMPLETED


def test_minimize_time_selects_fastest_feasible_candidate(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run(optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_TIME))
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20, 0.25)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "a", time_s=1000, grams=4.0),
            _result(tmp_path, "b", time_s=1200, grams=3.0),
            _result(tmp_path, "c", time_s=800, grams=5.0),  # fastest
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    winner = next(c for c in result.candidates if c.is_selected)
    assert winner.print_time_seconds == 800
    assert winner.id == candidates[2].id


def test_balanced_with_genuine_tradeoff_escalates_without_choosing(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run(optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.BALANCED))
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "a", time_s=900, grams=6.0),  # faster, more material
            _result(tmp_path, "b", time_s=1200, grams=3.0),  # slower, less material
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    assert not any(c.is_selected for c in result.candidates)
    assert result.decision.selected_action == "escalate_tradeoff"
    assert result.decision.requires_human is True
    assert result.run.status == RunStatus.NEEDS_HUMAN_INPUT
    # Both mutually non-dominated candidates are still marked Pareto-optimal.
    assert all(c.is_pareto_optimal for c in result.candidates)


# --- no feasible candidates -------------------------------------------


def test_no_feasible_candidates_selects_no_winner(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run(hard_constraints=HardConstraints(max_print_time_seconds=100, max_filament_grams=1))
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20)]
    slicer = FakeSlicerService(
        results=[
            _result(tmp_path, "a", time_s=1000, grams=4.0),
            _result(tmp_path, "b", time_s=1200, grams=5.0),
        ]
    )

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    assert not any(c.is_selected for c in result.candidates)
    assert not any(c.is_pareto_optimal for c in result.candidates)
    assert result.decision.selected_action == "no_feasible_candidate"
    assert result.run.status == RunStatus.INFEASIBLE


# --- run-level fatal conditions -----------------------------------------


def test_slicer_unavailable_aborts_run_and_marks_all_candidates_failed(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20, 0.25)]
    slicer = FakeSlicerService(raise_unavailable=True)

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    assert result.run.status == RunStatus.FAILED
    assert all(c.status == CandidateStatus.FAILED for c in result.candidates)
    assert result.decision.selected_action == "abort_run"
    # Only the first candidate should have actually been attempted before aborting.
    assert len(slicer.calls) == 1


def test_all_candidates_failing_to_slice_fails_the_run_without_crashing(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    candidates = [_candidate(run.id, layer_height=h) for h in (0.15, 0.20)]
    slicer = FakeSlicerService(result=SliceResult(success=False, error="no G-code produced"))

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, candidates=candidates
    )

    assert result.run.status == RunStatus.FAILED
    assert all(c.status == CandidateStatus.FAILED for c in result.candidates)
    assert result.decision.selected_action == "abort_run"
    assert len(slicer.calls) == 2  # both were attempted; failure is per-candidate, not fatal on its own


# --- default candidate set ----------------------------------------------


def test_uses_deterministic_planner_when_no_candidates_override_given(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    slicer = FakeSlicerService(result=SliceResult(success=True, print_time_seconds=100, filament_grams=1.0))

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, planner=DeterministicPlanner()
    )

    assert len(result.candidates) >= 6  # spec: ~6-8 candidates
    assert len(slicer.calls) == len(result.candidates)

    decisions = repository.list_decisions(run.id)
    plan_decision = next(d for d in decisions if d.selected_action == "plan_initial_candidates")
    assert "deterministic" in plan_decision.observation


# --- planner integration (proves the orchestrator uses the AgentPlanner
# abstraction, not the fixed generator directly) ----------------------


def test_orchestrator_uses_injected_planner_not_the_fixed_generator(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    fake_candidates = [_candidate(run.id, layer_height=h) for h in (0.11, 0.12, 0.13)]
    planner = FakePlanner(candidates=fake_candidates, planning_summary="fake strategy", planner_name="fake-v1")
    slicer = FakeSlicerService(result=SliceResult(success=True, print_time_seconds=500, filament_grams=2.0))

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, planner=planner, candidate_count=3
    )

    assert planner.calls == [(run.id, 3)]
    assert len(result.candidates) == 3
    assert {c.layer_height for c in result.candidates} == {0.11, 0.12, 0.13}

    decisions = repository.list_decisions(run.id)
    plan_decision = next(d for d in decisions if d.selected_action == "plan_initial_candidates")
    assert "fake-v1" in plan_decision.observation
    assert "fake strategy" in plan_decision.evidence


def test_planner_failure_aborts_run_before_any_slicing(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)

    planner = FakePlanner(raise_error=PlannerError("Gemini planner call failed: connection refused"))
    slicer = FakeSlicerService(result=SliceResult(success=True, print_time_seconds=100, filament_grams=1.0))

    result = execute_optimization_run(
        run, stl_path, repository=repository, storage=storage, slicer=slicer, planner=planner
    )

    assert result.candidates == []
    assert result.run.status == RunStatus.FAILED
    assert result.decision.selected_action == "abort_run"
    assert "connection refused" in result.decision.outcome
    assert len(slicer.calls) == 0  # never reached the slicer


def test_execute_optimization_run_requires_candidates_or_planner(tmp_path: Path) -> None:
    repository, storage, stl_path = _setup(tmp_path)
    run = _make_run()
    repository.create_run(run)
    slicer = FakeSlicerService(result=SliceResult(success=True))

    with pytest.raises(ValueError):
        execute_optimization_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)
