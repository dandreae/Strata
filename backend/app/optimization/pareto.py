"""Pareto dominance and frontier computation over (print_time, filament) pairs.

Both objectives are "lower is better." A candidate dominates another if it
is no worse in both objectives and strictly better in at least one. Only
candidates with known (non-None) metrics are comparable — comparison against
a candidate with missing metrics always returns False (unknown, not equal).
"""

from __future__ import annotations

from app.models.candidate import CandidateConfiguration


def _metrics(candidate: CandidateConfiguration) -> tuple[int, float] | None:
    if candidate.print_time_seconds is None or candidate.filament_grams is None:
        return None
    return candidate.print_time_seconds, candidate.filament_grams


def dominates(a: CandidateConfiguration, b: CandidateConfiguration) -> bool:
    """True if `a` Pareto-dominates `b` (strictly better or equal on both,
    strictly better on at least one). Returns False if either candidate is
    missing metrics."""
    a_metrics = _metrics(a)
    b_metrics = _metrics(b)
    if a_metrics is None or b_metrics is None:
        return False

    a_time, a_material = a_metrics
    b_time, b_material = b_metrics

    no_worse = a_time <= b_time and a_material <= b_material
    strictly_better = a_time < b_time or a_material < b_material
    return no_worse and strictly_better


def pareto_frontier(candidates: list[CandidateConfiguration]) -> list[CandidateConfiguration]:
    """Return the subset of `candidates` not dominated by any other candidate
    in the list. Candidates missing metrics are excluded entirely — they
    cannot be meaningfully compared.
    """
    comparable = [c for c in candidates if _metrics(c) is not None]

    frontier: list[CandidateConfiguration] = []
    for candidate in comparable:
        if any(other.id != candidate.id and dominates(other, candidate) for other in comparable):
            continue
        frontier.append(candidate)
    return frontier


__all__ = ["dominates", "pareto_frontier"]
