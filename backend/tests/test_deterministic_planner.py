from __future__ import annotations

from app.agent.deterministic_planner import DeterministicPlanner
from app.agent.default_candidate import generate_candidate_set
from app.models.run import HardConstraints, OptimizationObjective, OptimizationPreferences, OptimizationRun


def _make_run() -> OptimizationRun:
    return OptimizationRun(
        filename="part.stl",
        production_quantity=100,
        printer_profile="generic_pla",
        hard_constraints=HardConstraints(max_print_time_seconds=1800, max_filament_grams=10),
        optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.BALANCED),
    )


def test_matches_generate_candidate_set_exactly() -> None:
    run = _make_run()
    planner = DeterministicPlanner()

    result = planner.plan_initial_candidates(run, candidate_count=8)
    expected = generate_candidate_set(run.id)

    got_specs = [(c.layer_height, c.infill_percent, c.perimeter_count) for c in result.candidates]
    expected_specs = [(c.layer_height, c.infill_percent, c.perimeter_count) for c in expected]
    assert got_specs == expected_specs


def test_planner_name_and_summary_present() -> None:
    result = DeterministicPlanner().plan_initial_candidates(_make_run(), candidate_count=8)
    assert result.planner_name == "deterministic"
    assert result.planning_summary
    assert result.rejected_proposals == []


def test_is_stable_across_calls() -> None:
    run = _make_run()
    planner = DeterministicPlanner()
    a = planner.plan_initial_candidates(run, candidate_count=8)
    b = planner.plan_initial_candidates(run, candidate_count=8)

    a_specs = [(c.layer_height, c.infill_percent, c.perimeter_count) for c in a.candidates]
    b_specs = [(c.layer_height, c.infill_percent, c.perimeter_count) for c in b.candidates]
    assert a_specs == b_specs


def test_plan_next_round_always_stops() -> None:
    """DeterministicPlanner never adapts — a deterministic run is always
    exactly one round, deterministically."""
    planner = DeterministicPlanner()
    run = _make_run()
    previous_results = planner.plan_initial_candidates(run, candidate_count=8).candidates

    decision = planner.plan_next_round(run, previous_results, candidate_count=8)

    assert decision.should_continue is False
    assert decision.candidates == []
    assert decision.planner_name == "deterministic"
    assert decision.reasoning_summary
