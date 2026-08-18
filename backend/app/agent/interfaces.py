"""The AgentPlanner contract: the seam between candidate generation and
everything downstream of it (real PrusaSlicer, deterministic constraint
evaluation, Pareto analysis, winner selection).

Two implementations satisfy this contract:
  - DeterministicPlanner (app/agent/deterministic_planner.py): wraps the
    original fixed `generate_candidate_set` — offline, free, no network.
  - GeminiAgentPlanner (app/agent/gemini_planner.py): Gemini + Google ADK,
    bounded to domain-level parameters, deterministically revalidated.

Responsibility split (see docs/architecture.md for the full rationale):
  - AgentPlanner (this interface): propose a first round of candidate
    configurations and (once the adaptive-loop milestone lands)
    diagnose results and decide whether to keep searching.
  - app.optimization.*: numeric comparison, constraint checks, Pareto
    dominance, ranking — always deterministic, never delegated to the LLM.
  - app.slicer.*: ground truth for print time / filament usage.

This milestone only exercises `plan_initial_candidates` — no adaptive
second round yet, so `should_continue_searching` is defined for contract
completeness but always returns False in both implementations for now.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationRun


class PlannerError(Exception):
    """Raised when a planner cannot produce a usable candidate set at all —
    e.g. the Gemini call failed, or every proposal was rejected by
    deterministic validation. Distinct from a per-candidate slicing
    failure: this happens before any slicing is attempted. Callers must
    surface this clearly, not silently substitute another planner.
    """


@dataclass(frozen=True)
class PlannerResult:
    candidates: list[CandidateConfiguration]
    planning_summary: str = ""
    planner_name: str = ""
    rejected_proposals: list[str] = field(default_factory=list)


class AgentPlanner(ABC):
    """Proposes candidate configurations. Never computes manufacturing
    truth, constraint pass/fail, or Pareto dominance — those stay
    deterministic downstream regardless of which planner is active."""

    @abstractmethod
    def plan_initial_candidates(self, run: OptimizationRun, candidate_count: int) -> PlannerResult:
        """Propose the first round of candidate configurations for `run`.

        Must raise `PlannerError` rather than returning an empty or
        partially-unusable result — callers should never have to guess
        whether an empty candidate list means "no ideas" or "call failed".
        """

    @abstractmethod
    def should_continue_searching(
        self,
        run: OptimizationRun,
        results_so_far: list[CandidateConfiguration],
    ) -> bool:
        """Decide whether optimization should keep iterating.

        Unused until the adaptive multi-round milestone (explicitly out of
        scope here) — both current implementations return False.
        """


__all__ = ["AgentPlanner", "PlannerResult", "PlannerError"]
