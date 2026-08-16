from __future__ import annotations

from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.optimization.pareto import dominates, pareto_frontier


def _candidate(id_: str, time_s: int | None, grams: float | None) -> CandidateConfiguration:
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


def test_faster_and_less_material_dominates() -> None:
    a = _candidate("a", 100, 10)
    b = _candidate("b", 200, 20)
    assert dominates(a, b)
    assert not dominates(b, a)


def test_tradeoff_candidates_do_not_dominate_each_other() -> None:
    # A is faster, B uses less material — neither wins outright.
    a = _candidate("a", 8700, 79)   # 2h25m, 79g
    b = _candidate("b", 10500, 61)  # 2h55m, 61g
    assert not dominates(a, b)
    assert not dominates(b, a)


def test_equal_candidates_do_not_dominate() -> None:
    a = _candidate("a", 100, 10)
    b = _candidate("b", 100, 10)
    assert not dominates(a, b)
    assert not dominates(b, a)


def test_missing_metrics_never_dominate() -> None:
    a = _candidate("a", None, None)
    b = _candidate("b", 100, 10)
    assert not dominates(a, b)
    assert not dominates(b, a)


def test_pareto_frontier_excludes_dominated_candidates() -> None:
    dominated = _candidate("dominated", 300, 30)
    winner = _candidate("winner", 100, 10)
    tradeoff = _candidate("tradeoff", 50, 40)

    frontier = pareto_frontier([dominated, winner, tradeoff])
    frontier_ids = {c.id for c in frontier}

    assert frontier_ids == {"winner", "tradeoff"}
    assert "dominated" not in frontier_ids


def test_pareto_frontier_excludes_candidates_missing_metrics() -> None:
    unsliced = _candidate("unsliced", None, None)
    sliced = _candidate("sliced", 100, 10)

    frontier = pareto_frontier([unsliced, sliced])
    assert [c.id for c in frontier] == ["sliced"]
