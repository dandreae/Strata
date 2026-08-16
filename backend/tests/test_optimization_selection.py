from __future__ import annotations

from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.run import OptimizationObjective, OptimizationPreferences
from app.optimization.selection import select_winner


def _candidate(id_: str, time_s: int, grams: float) -> CandidateConfiguration:
    return CandidateConfiguration(
        id=id_,
        run_id="run-1",
        layer_height=0.2,
        infill_percent=20,
        perimeter_count=3,
        status=CandidateStatus.SUCCEEDED,
        print_time_seconds=time_s,
        filament_grams=grams,
    )


def test_minimize_material_picks_lowest_filament_usage() -> None:
    a = _candidate("a", 8700, 79)   # 2h25m, 79g
    b = _candidate("b", 10500, 61)  # 2h55m, 61g

    result = select_winner([a, b], OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_MATERIAL))

    assert result.winner is not None
    assert result.winner.id == "b"
    assert not result.requires_human


def test_minimize_time_picks_lowest_print_time() -> None:
    a = _candidate("a", 8700, 79)
    b = _candidate("b", 10500, 61)

    result = select_winner([a, b], OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_TIME))

    assert result.winner is not None
    assert result.winner.id == "a"
    assert not result.requires_human


def test_minimize_material_tie_breaks_on_time() -> None:
    a = _candidate("a", 200, 10)
    b = _candidate("b", 100, 10)  # same material, faster

    result = select_winner([a, b], OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_MATERIAL))

    assert result.winner.id == "b"


def test_balanced_with_single_dominant_candidate_auto_selects() -> None:
    dominant = _candidate("dominant", 100, 10)
    dominated = _candidate("dominated", 300, 30)

    result = select_winner([dominant, dominated], OptimizationPreferences(objective=OptimizationObjective.BALANCED))

    assert result.winner is not None
    assert result.winner.id == "dominant"
    assert not result.requires_human


def test_balanced_with_genuine_tradeoff_requires_human() -> None:
    a = _candidate("a", 8700, 79)   # faster, more material
    b = _candidate("b", 10500, 61)  # slower, less material

    result = select_winner([a, b], OptimizationPreferences(objective=OptimizationObjective.BALANCED))

    assert result.winner is None
    assert result.requires_human
    assert {c.id for c in result.pareto_frontier} == {"a", "b"}


def test_no_usable_candidates_returns_no_winner_without_escalating() -> None:
    result = select_winner([], OptimizationPreferences(objective=OptimizationObjective.BALANCED))
    assert result.winner is None
    assert not result.requires_human
