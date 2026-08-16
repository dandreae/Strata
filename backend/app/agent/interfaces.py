"""Placeholder contract for the future Gemini/ADK-driven planner.

No Gemini or ADK calls are made anywhere in this codebase yet. This module
only fixes the *shape* of the boundary so the rest of the system (API,
optimization, slicer) can be built against a stable interface ahead of the
actual agent integration.

Responsibility split (see docs/architecture.md for the full rationale):
  - AgentPlanner (this interface): interpret goals, propose candidate
    configurations, diagnose failed slices, decide whether to keep
    searching, explain decisions in plain language.
  - app.optimization.*: numeric comparison, constraint checks, Pareto
    dominance, ranking — always deterministic, never delegated to the LLM.
  - app.slicer.*: ground truth for print time / filament usage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationRun


class AgentPlanner(ABC):
    """Future Gemini/ADK-backed planner. Not implemented in this pass."""

    @abstractmethod
    def propose_candidates(
        self,
        run: OptimizationRun,
        previous_results: list[CandidateConfiguration],
    ) -> list[CandidateConfiguration]:
        """Propose the next batch of candidate configurations to slice,
        given the run's goals and what has been tried so far."""

    @abstractmethod
    def should_continue_searching(
        self,
        run: OptimizationRun,
        results_so_far: list[CandidateConfiguration],
    ) -> bool:
        """Decide whether optimization should keep iterating."""


class NotImplementedAgentPlanner(AgentPlanner):
    """Fails loudly. Wire in the real Gemini/ADK planner to replace this."""

    def propose_candidates(
        self, run: OptimizationRun, previous_results: list[CandidateConfiguration]
    ) -> list[CandidateConfiguration]:
        raise NotImplementedError(
            "AgentPlanner is not implemented yet — this pass only establishes the interface. "
            "See docs/architecture.md for the planned Gemini/ADK integration."
        )

    def should_continue_searching(self, run: OptimizationRun, results_so_far: list[CandidateConfiguration]) -> bool:
        raise NotImplementedError(
            "AgentPlanner is not implemented yet — this pass only establishes the interface."
        )


__all__ = ["AgentPlanner", "NotImplementedAgentPlanner"]
