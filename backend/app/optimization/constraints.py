"""Hard-constraint validation.

A candidate must have actually been sliced successfully before it can be
evaluated against constraints — Strata never guesses at print time or
filament usage.
"""

from __future__ import annotations

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


__all__ = ["constraint_violations", "satisfies_hard_constraints", "filter_feasible"]
