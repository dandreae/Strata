"""The AgentPlanner contract: the seam between candidate generation and
everything downstream of it (real PrusaSlicer, deterministic constraint
evaluation, Pareto analysis, winner selection).

Two implementations satisfy this contract:
  - DeterministicPlanner (app/agent/deterministic_planner.py): wraps the
    original fixed `generate_candidate_set` — offline, free, no network.
    Its `plan_next_round` always says stop; it never adapts.
  - GeminiAgentPlanner (app/agent/gemini_planner.py): Gemini + Google ADK,
    bounded to domain-level parameters, deterministically revalidated.

Responsibility split (see docs/architecture.md for the full rationale):
  - AgentPlanner (this interface): propose a first round of candidates,
    then — given the first round's real measured results — decide whether
    a second round is worth proposing.
  - app.optimization.*: numeric comparison, constraint checks, Pareto
    dominance, ranking — always deterministic, never delegated to the LLM,
    and computed once over the *combined* candidate pool regardless of how
    many rounds ran.
  - app.slicer.*: ground truth for print time / filament usage.

Bounded on purpose: at most two rounds total (one initial, one adaptive),
at most one planner call per round — see app/services/orchestrator.py. This
is not yet a general adaptive loop with unbounded iteration or convergence
detection; it's a single bounded refinement step.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationRun


class PlannerError(Exception):
    """Raised when a planner cannot produce a usable result at all — e.g.
    the Gemini call failed, or (for the first round only) every proposal
    was rejected by deterministic validation. Distinct from a per-candidate
    slicing failure: this happens before any slicing is attempted.

    Round 1: fatal — callers must surface this clearly (abort the run), not
    silently substitute another planner.
    Round 2: NOT fatal to the run — Round 1 already produced real, valid
    results. Callers (see orchestrator._run_round_two) catch this, record it
    plainly in the decision ledger, and finalize on Round 1 alone. That is
    a transparent degradation of an already-successful process, not a
    silent fallback to a different planner.
    """


@dataclass(frozen=True)
class PlannerResult:
    """Result of `plan_initial_candidates` — a full round of new proposals."""

    candidates: list[CandidateConfiguration]
    planning_summary: str = ""
    planner_name: str = ""
    rejected_proposals: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RoundDecision:
    """Result of `plan_next_round` — whether to continue, and if so, with what."""

    should_continue: bool
    reasoning_summary: str = ""
    candidates: list[CandidateConfiguration] = field(default_factory=list)
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
    def plan_next_round(
        self,
        run: OptimizationRun,
        previous_results: list[CandidateConfiguration],
        candidate_count: int,
    ) -> RoundDecision:
        """Given the previous round's real, measured results (configuration,
        real print time, real filament usage, slicing status), decide
        whether a further round of experimentation is likely to meaningfully
        improve the result and, if so, propose up to `candidate_count` new
        candidates not already tested.

        A legitimate "nothing more worth trying" outcome is a normal return
        (`RoundDecision(should_continue=False, ...)`), not an error. Raise
        `PlannerError` only for a genuine call failure (network, auth,
        malformed output) — see `PlannerError`'s docstring for how callers
        must treat that differently from a Round 1 failure.
        """


__all__ = ["AgentPlanner", "PlannerResult", "RoundDecision", "PlannerError"]
