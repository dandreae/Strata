from __future__ import annotations

from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.run import HardConstraints
from app.optimization.constraints import (
    constraint_violations,
    evaluate_constraint_checks,
    filter_feasible,
    satisfies_hard_constraints,
)

CONSTRAINTS = HardConstraints(max_print_time_seconds=3 * 3600, max_filament_grams=80)


def _candidate(**overrides) -> CandidateConfiguration:
    defaults = dict(
        run_id="run-1",
        layer_height=0.2,
        infill_percent=20,
        perimeter_count=3,
        status=CandidateStatus.SUCCEEDED,
        print_time_seconds=8700,
        filament_grams=61.0,
    )
    defaults.update(overrides)
    return CandidateConfiguration(**defaults)


def test_feasible_candidate_satisfies_constraints() -> None:
    candidate = _candidate()
    assert satisfies_hard_constraints(candidate, CONSTRAINTS)
    assert constraint_violations(candidate, CONSTRAINTS) == []


def test_candidate_exceeding_time_is_infeasible() -> None:
    candidate = _candidate(print_time_seconds=4 * 3600)
    assert not satisfies_hard_constraints(candidate, CONSTRAINTS)
    violations = constraint_violations(candidate, CONSTRAINTS)
    assert any("Print time" in v for v in violations)


def test_candidate_exceeding_material_is_infeasible() -> None:
    candidate = _candidate(filament_grams=95.0)
    assert not satisfies_hard_constraints(candidate, CONSTRAINTS)
    violations = constraint_violations(candidate, CONSTRAINTS)
    assert any("Filament usage" in v for v in violations)


def test_unsliced_candidate_is_never_feasible() -> None:
    candidate = _candidate(status=CandidateStatus.PENDING, print_time_seconds=None, filament_grams=None)
    assert not satisfies_hard_constraints(candidate, CONSTRAINTS)


def test_failed_candidate_is_never_feasible() -> None:
    candidate = _candidate(status=CandidateStatus.FAILED, print_time_seconds=None, filament_grams=None)
    assert not satisfies_hard_constraints(candidate, CONSTRAINTS)


def test_filter_feasible_keeps_only_passing_candidates() -> None:
    good = _candidate()
    bad = _candidate(filament_grams=999)
    assert filter_feasible([good, bad], CONSTRAINTS) == [good]


def test_constraint_checks_both_pass() -> None:
    checks = evaluate_constraint_checks(_candidate(), CONSTRAINTS)
    by_key = {c.key: c for c in checks}

    assert by_key["max_print_time_seconds"].passed is True
    assert by_key["max_print_time_seconds"].actual == 8700
    assert by_key["max_print_time_seconds"].limit == 3 * 3600

    assert by_key["max_filament_grams"].passed is True
    assert by_key["max_filament_grams"].actual == 61.0
    assert by_key["max_filament_grams"].limit == 80


def test_constraint_checks_material_fails_independently_of_time() -> None:
    candidate = _candidate(filament_grams=95.0)
    checks = evaluate_constraint_checks(candidate, CONSTRAINTS)
    by_key = {c.key: c for c in checks}

    assert by_key["max_print_time_seconds"].passed is True
    assert by_key["max_filament_grams"].passed is False
    assert by_key["max_filament_grams"].actual == 95.0


def test_constraint_checks_missing_metric_fails_and_reports_none() -> None:
    candidate = _candidate(status=CandidateStatus.FAILED, print_time_seconds=None, filament_grams=None)
    checks = evaluate_constraint_checks(candidate, CONSTRAINTS)

    assert all(not c.passed for c in checks)
    assert all(c.actual is None for c in checks)


def test_constraint_checks_boundary_value_passes() -> None:
    """A candidate exactly at the limit satisfies it (<=, not <)."""
    candidate = _candidate(print_time_seconds=CONSTRAINTS.max_print_time_seconds, filament_grams=CONSTRAINTS.max_filament_grams)
    checks = evaluate_constraint_checks(candidate, CONSTRAINTS)
    assert all(c.passed for c in checks)
