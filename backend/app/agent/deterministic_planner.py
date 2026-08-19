"""DeterministicPlanner: the original fixed candidate generator, wrapped to
satisfy the AgentPlanner contract.

No network, no cost, no variance — used whenever STRATA_PLANNER_MODE is
"deterministic" (the default), and as the offline/CI-safe path regardless
of what Gemini support exists. `generate_candidate_set` itself is
untouched; this is purely an adapter. It never adapts across rounds —
`plan_next_round` always stops, so a deterministic run is always exactly
one round, deterministically.
"""

from __future__ import annotations

from app.agent.default_candidate import generate_candidate_set
from app.agent.interfaces import AgentPlanner, PlannerResult, RoundDecision
from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationRun


class DeterministicPlanner(AgentPlanner):
    def plan_initial_candidates(self, run: OptimizationRun, candidate_count: int) -> PlannerResult:
        # The fixed set's size is a deliberate, documented design choice
        # (see app/agent/default_candidate.py) — candidate_count is not
        # honored here the way it is for an adaptive planner; deterministic
        # mode always returns the same set regardless of what's requested.
        candidates = generate_candidate_set(run.id)
        return PlannerResult(
            candidates=candidates,
            planning_summary=(
                f"Deterministic fixed candidate set: {len(candidates)} configurations spanning "
                "layer height 0.15-0.25mm, infill 10-30%, and 2-3 perimeters, chosen to create "
                "real print-time/material tradeoffs without a full parameter sweep."
            ),
            planner_name="deterministic",
        )

    def plan_next_round(
        self,
        run: OptimizationRun,
        previous_results: list[CandidateConfiguration],
        candidate_count: int,
    ) -> RoundDecision:
        return RoundDecision(
            should_continue=False,
            reasoning_summary="Deterministic planner does not adapt across rounds.",
            planner_name="deterministic",
        )


__all__ = ["DeterministicPlanner"]
