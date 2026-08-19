"""Test doubles. Used only to unit-test orchestration without a real
PrusaSlicer binary — never used to fabricate what a real slice would report;
see test_slicer_prusaslicer.py and the (skipped-without-a-binary) real
integration test for that.
"""

from __future__ import annotations

from pathlib import Path

from app.agent.interfaces import AgentPlanner, PlannerError, PlannerResult, RoundDecision
from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationRun
from app.models.slicer import SliceResult
from app.slicer.base import SlicerService, SlicerUnavailableError


class FakeSlicerService(SlicerService):
    """Returns pre-programmed SliceResult(s) (or raises), never touches a subprocess.

    Pass `result` for a single fixed result applied to every call (single-
    candidate tests), or `results` for a sequence consumed in call order
    (multi-candidate tests where each candidate should get a different
    real-looking result). If more calls happen than `results` provides, the
    last result repeats.
    """

    def __init__(
        self,
        result: SliceResult | None = None,
        results: list[SliceResult] | None = None,
        raise_unavailable: bool = False,
    ) -> None:
        self._result = result
        self._results = list(results) if results is not None else None
        self._raise_unavailable = raise_unavailable
        self.calls: list[tuple[Path, str, CandidateConfiguration]] = []

    def slice(
        self,
        stl_path: Path,
        printer_profile: str,
        candidate_configuration: CandidateConfiguration,
    ) -> SliceResult:
        self.calls.append((stl_path, printer_profile, candidate_configuration))
        if self._raise_unavailable:
            raise SlicerUnavailableError("fake: PrusaSlicer binary not found")
        if self._results is not None:
            index = min(len(self.calls) - 1, len(self._results) - 1)
            return self._results[index]
        assert self._result is not None
        return self._result


class FakePlanner(AgentPlanner):
    """Returns pre-programmed PlannerResult/RoundDecision (or raises
    PlannerError), never touches Gemini/ADK. Used to prove the orchestrator
    calls the planner abstraction rather than the fixed generator directly,
    and to drive the bounded adaptive (round 2) loop deterministically."""

    def __init__(
        self,
        candidates: list[CandidateConfiguration] | None = None,
        planning_summary: str = "fake planning summary",
        planner_name: str = "fake",
        raise_error: PlannerError | None = None,
        round_two: RoundDecision | None = None,
        round_two_raise_error: PlannerError | None = None,
    ) -> None:
        self._candidates = candidates or []
        self._planning_summary = planning_summary
        self._planner_name = planner_name
        self._raise_error = raise_error
        # Default: no round 2 candidates, matching DeterministicPlanner's
        # real "never adapts" behavior unless a test opts in.
        self._round_two = round_two or RoundDecision(should_continue=False, reasoning_summary="fake: stop", planner_name=planner_name)
        self._round_two_raise_error = round_two_raise_error
        self.calls: list[tuple[str, int]] = []
        self.round_two_calls: list[tuple[str, int]] = []

    def plan_initial_candidates(self, run: OptimizationRun, candidate_count: int) -> PlannerResult:
        self.calls.append((run.id, candidate_count))
        if self._raise_error is not None:
            raise self._raise_error
        return PlannerResult(
            candidates=self._candidates,
            planning_summary=self._planning_summary,
            planner_name=self._planner_name,
        )

    def plan_next_round(
        self,
        run: OptimizationRun,
        previous_results: list[CandidateConfiguration],
        candidate_count: int,
    ) -> RoundDecision:
        self.round_two_calls.append((run.id, candidate_count))
        if self._round_two_raise_error is not None:
            raise self._round_two_raise_error
        return self._round_two
