"""Preference-based winner selection among feasible candidates.

This is the deterministic half of Strata's escalation philosophy: given an
explicit optimization preference, always pick a winner automatically. With
no clear preference (BALANCED) and multiple non-dominated candidates, this
module says so explicitly (`requires_human=True`) rather than guessing — the
agent layer is responsible for turning that into a user-facing question.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationObjective, OptimizationPreferences
from app.optimization.pareto import pareto_frontier


@dataclass(frozen=True)
class SelectionResult:
    winner: CandidateConfiguration | None
    requires_human: bool
    pareto_frontier: list[CandidateConfiguration] = field(default_factory=list)
    reason: str = ""


def _sort_key_minimize_material(c: CandidateConfiguration) -> tuple[float, int]:
    # Primary: lowest filament usage. Tie-break: lowest print time.
    return (c.filament_grams, c.print_time_seconds)  # type: ignore[return-value]


def _sort_key_minimize_time(c: CandidateConfiguration) -> tuple[int, float]:
    # Primary: lowest print time. Tie-break: lowest filament usage.
    return (c.print_time_seconds, c.filament_grams)  # type: ignore[return-value]


def select_winner(
    candidates: list[CandidateConfiguration],
    preferences: OptimizationPreferences,
) -> SelectionResult:
    """Choose a winner among already-feasible `candidates`.

    Callers should pass only candidates that already satisfy hard
    constraints (see `app.optimization.constraints.filter_feasible`) —
    this function does not re-check feasibility.
    """
    usable = [c for c in candidates if c.print_time_seconds is not None and c.filament_grams is not None]
    if not usable:
        return SelectionResult(winner=None, requires_human=False, reason="No feasible candidates with known metrics.")

    if preferences.objective == OptimizationObjective.MINIMIZE_MATERIAL:
        winner = min(usable, key=_sort_key_minimize_material)
        return SelectionResult(
            winner=winner,
            requires_human=False,
            reason="Selected lowest filament usage (minimize_material), print time as tie-breaker.",
        )

    if preferences.objective == OptimizationObjective.MINIMIZE_TIME:
        winner = min(usable, key=_sort_key_minimize_time)
        return SelectionResult(
            winner=winner,
            requires_human=False,
            reason="Selected lowest print time (minimize_time), filament usage as tie-breaker.",
        )

    # BALANCED: no declared priority. Only auto-decide if there is a single
    # non-dominated candidate; otherwise this is a genuine tradeoff.
    frontier = pareto_frontier(usable)
    if len(frontier) == 1:
        return SelectionResult(
            winner=frontier[0],
            requires_human=False,
            pareto_frontier=frontier,
            reason="Single non-dominated candidate on the Pareto frontier.",
        )

    return SelectionResult(
        winner=None,
        requires_human=True,
        pareto_frontier=frontier,
        reason=(
            "No optimization priority set and multiple candidates are mutually "
            "non-dominated; this tradeoff requires human input."
        ),
    )


__all__ = ["SelectionResult", "select_winner"]
