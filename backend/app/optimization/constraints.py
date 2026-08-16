"""Hard-constraint validation.

A candidate must have actually been sliced successfully before it can be
evaluated against constraints — Strata never guesses at print time or
filament usage.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.run import HardConstraints


def constraint_violations(candidate: CandidateConfiguration, constraints: HardConstraints) -> list[str]:
    """Return human-readable reasons the candidate fails hard constraints.

    An empty list means the candidate is feasible. A candidate that never
    successfully sliced is always reported as failing, since its real
    print time/filament usage is unknown.
    """
    if candidate.status != CandidateStatus.SUCCEEDED:
        return [f"Candidate has not successfully sliced (status={candidate.status.value})."]

    violations: list[str] = []

    if candidate.print_time_seconds is None:
        violations.append("Missing print_time_seconds; cannot verify max_print_time_seconds.")
    elif candidate.print_time_seconds > constraints.max_print_time_seconds:
        violations.append(
            f"Print time {candidate.print_time_seconds}s exceeds max "
            f"{constraints.max_print_time_seconds}s."
        )

    if candidate.filament_grams is None:
        violations.append("Missing filament_grams; cannot verify max_filament_grams.")
    elif candidate.filament_grams > constraints.max_filament_grams:
        violations.append(
            f"Filament usage {candidate.filament_grams}g exceeds max "
            f"{constraints.max_filament_grams}g."
        )

    return violations


def satisfies_hard_constraints(candidate: CandidateConfiguration, constraints: HardConstraints) -> bool:
    """True if `candidate` violates none of `constraints`."""
    return not constraint_violations(candidate, constraints)


def filter_feasible(
    candidates: list[CandidateConfiguration], constraints: HardConstraints
) -> list[CandidateConfiguration]:
    """Return only the candidates that satisfy the hard constraints."""
    return [c for c in candidates if satisfies_hard_constraints(c, constraints)]


@dataclass(frozen=True)
class ConstraintCheck:
    """One structured, per-constraint pass/fail result.

    Exists so API consumers (the frontend) can render a requirements
    checklist without recomputing `actual <= limit` themselves — that
    comparison stays deterministic backend code, per the project's
    Gemini/deterministic-code split (see docs/architecture.md).
    """

    key: str
    label: str
    passed: bool
    limit: float
    actual: float | None
    unit: str


def evaluate_constraint_checks(
    candidate: CandidateConfiguration, constraints: HardConstraints
) -> list[ConstraintCheck]:
    """Structured, per-constraint version of `constraint_violations`.

    One entry per hard constraint the MVP supports (print time, material).
    `actual` is `None` when the metric is missing (unsliced/failed candidate,
    or a metric PrusaSlicer's output didn't contain) — such checks are
    always reported as failed, never silently passed or guessed.
    """
    return [
        ConstraintCheck(
            key="max_print_time_seconds",
            label="Print time",
            passed=candidate.print_time_seconds is not None
            and candidate.print_time_seconds <= constraints.max_print_time_seconds,
            limit=constraints.max_print_time_seconds,
            actual=candidate.print_time_seconds,
            unit="s",
        ),
        ConstraintCheck(
            key="max_filament_grams",
            label="Material",
            passed=candidate.filament_grams is not None
            and candidate.filament_grams <= constraints.max_filament_grams,
            limit=constraints.max_filament_grams,
            actual=candidate.filament_grams,
            unit="g",
        ),
    ]


__all__ = [
    "constraint_violations",
    "satisfies_hard_constraints",
    "filter_feasible",
    "ConstraintCheck",
    "evaluate_constraint_checks",
]
