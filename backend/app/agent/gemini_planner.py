"""GeminiAgentPlanner: Gemini + Google ADK as a bounded experiment planner.

Uses the official `google-adk` package (`LlmAgent` + `Runner`), not the raw
Gemini SDK directly — this is the hackathon's required agent framework.
`google-genai` (ADK's own dependency) supplies the `types.Content`/`Part`
wire format for the single-turn request.

Safety boundary (mandatory, see app/agent/planner_validation.py):

    Gemini (via ADK LlmAgent, output_schema-constrained JSON)
        ↓
    CandidateProposal (typed schema, still untrusted)
        ↓
    validate_and_normalize_proposals() — bounds, finiteness, duplicates, count cap
        ↓
    CandidateConfiguration
        ↓
    PrusaSlicer command builder

Gemini never sees a shell, a subprocess argument list, a file path, or a
CLI flag, and its output never reaches PrusaSlicer without passing through
deterministic validation first. Gemini also never predicts print time or
filament usage — it isn't asked to, and nothing it returns is used as a
manufacturing metric; those come only from a real `SliceResult`.

Uses `Runner.run_async()`, run to completion via `_run_coroutine_sync()`
below — not `asyncio.run()` directly, and not ADK's own synchronous
`Runner.run()` wrapper. Both were tried first, for real, against this
milestone's own real end-to-end path (not just mocks), and both had a real
bug:

  - `Runner.run()` drives `run_async()` on a background thread via a queue,
    and its `try/finally` around that thread's async task does NOT re-raise
    the task's exception — an auth/network/model error there becomes an
    *unhandled background-thread exception* (visible only as a Python
    warning), not a Python exception `run()`'s caller can catch. Found by a
    real (invalid-credential) smoke test run.
  - Calling `asyncio.run(_call_once())` directly fixed that, but broke as
    soon as this ran through the real FastAPI request path instead of a
    bare script/test: `asyncio.run()` cannot be called from inside a
    already-running event loop, and `create_run`'s route handler runs on
    uvicorn's. Found by a real browser round-trip through `POST
    /api/v1/runs` with `STRATA_PLANNER_MODE=gemini` — the mocked unit tests
    never had a running loop to expose this, and the smoke test call sites
    don't go through FastAPI.

`_run_coroutine_sync()` always runs the coroutine on a dedicated thread
with its own fresh event loop (so it never collides with a loop that may
already be running on the calling thread) and retrieves the result via
`concurrent.futures.Future.result()`, which properly re-raises any
exception the coroutine raised — both problems fixed by the same,
standard-library-only mechanism.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.agent.interfaces import AgentPlanner, PlannerError, PlannerResult
from app.agent.planner_schema import PlannerOutput
from app.agent.planner_validation import validate_and_normalize_proposals
from app.core.logging import get_logger
from app.models.candidate import CandidateConfiguration
from app.models.run import OptimizationRun

logger = get_logger(__name__)

_PLANNER_APP_NAME = "strata-experiment-planner"
_PLANNER_USER_ID = "strata"

_T = TypeVar("_T")


def _run_coroutine_sync(coro: Coroutine[object, object, _T]) -> _T:
    """Run `coro` to completion from synchronous code, regardless of
    whether the calling thread already has an event loop running (FastAPI's
    request path) or not (tests, scripts) — see module docstring for the
    two real bugs this specifically fixes.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()

_INSTRUCTION = """You are Strata's manufacturing experiment planner for FDM 3D printing.

Your job is to propose a diverse, bounded set of manufacturing configurations
(experiments) worth actually testing — not to predict how they will perform.
You have no way to know real print time or filament usage; those are only
knowable after a real slicer runs. Treat every candidate you propose as a
hypothesis, not a prediction.

You may only choose values for exactly three parameters, each within a hard
range you must never violate:
  - layer_height: millimeters, between 0.10 and 0.30
  - infill_percent: percent, between 5 and 40
  - perimeter_count: integer, between 2 and 4

You do not control orientation, supports, temperatures, speeds, extrusion,
acceleration, or any other slicer setting — those are fixed elsewhere and
are not your concern.

Propose configurations that are genuinely diverse and span meaningful
tradeoffs across the allowed ranges (e.g. some biased toward thinner
layers/lower infill for less material, some biased toward thicker
layers/lower infill for less time, and some intermediate points) so that,
once really sliced, they reveal the actual print-time/material tradeoff
surface for this part under the user's constraints. Do not cluster all
proposals near the same values.

Return exactly the number of candidates requested. `planning_summary` must
be one or two plain, concise sentences describing your experiment strategy
in a way suitable for an audit log — not your reasoning process, not a
step-by-step justification, just what the experiment set is trying to
establish."""


def _build_prompt(run: OptimizationRun, candidate_count: int) -> str:
    prefs = run.optimization_preferences
    constraints = run.hard_constraints
    return (
        f"Propose {candidate_count} candidate configurations for this manufacturing run.\n\n"
        f"Production quantity: {run.production_quantity}\n"
        f"Hard constraint - max print time: {constraints.max_print_time_seconds} seconds\n"
        f"Hard constraint - max filament usage: {constraints.max_filament_grams} grams\n"
        f"User's optimization preference: {prefs.objective.value}\n"
        f"Allowed layer_height range: 0.10-0.30 mm\n"
        f"Allowed infill_percent range: 5-40 %\n"
        f"Allowed perimeter_count range: 2-4\n"
        f"Number of candidates to propose: {candidate_count}\n"
    )


class GeminiAgentPlanner(AgentPlanner):
    def __init__(self, api_key: str, model: str) -> None:
        if not api_key:
            raise PlannerError("STRATA_PLANNER_MODE=gemini requires STRATA_GEMINI_API_KEY to be set.")
        # google-genai (ADK's underlying SDK) reads its API key from the
        # process environment — GOOGLE_API_KEY or GEMINI_API_KEY — not from
        # a constructor argument (confirmed in google/genai/_api_client.py).
        # Route it through explicitly from Strata's own settings rather
        # than relying on an ambient env var of the right name existing.
        os.environ.setdefault("GOOGLE_API_KEY", api_key)
        self._model = model

    def plan_initial_candidates(self, run: OptimizationRun, candidate_count: int) -> PlannerResult:
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        agent = LlmAgent(
            model=self._model,
            name="strata_experiment_planner",
            description="Proposes bounded FDM 3D-printing manufacturing experiments for Strata.",
            instruction=_INSTRUCTION,
            output_schema=PlannerOutput,
        )

        async def _call_once() -> str | None:
            session_service = InMemorySessionService()
            session = await session_service.create_session(app_name=_PLANNER_APP_NAME, user_id=_PLANNER_USER_ID)
            runner = Runner(agent=agent, app_name=_PLANNER_APP_NAME, session_service=session_service)
            content = types.Content(role="user", parts=[types.Part(text=_build_prompt(run, candidate_count))])

            text: str | None = None
            async for event in runner.run_async(user_id=_PLANNER_USER_ID, session_id=session.id, new_message=content):
                if event.is_final_response() and event.content and event.content.parts:
                    text = event.content.parts[0].text
            return text

        try:
            raw_text = _run_coroutine_sync(_call_once())
        except Exception as exc:
            # Network error, auth failure, quota, model-not-found, etc. —
            # surface clearly. No silent fallback to the deterministic
            # planner from inside "gemini" mode (see Step 3/Step 9: an
            # explicitly requested planner that fails must fail loudly).
            raise PlannerError(f"Gemini planner call failed: {exc}") from exc

        if not raw_text:
            raise PlannerError("Gemini planner returned no response.")

        try:
            parsed = PlannerOutput.model_validate_json(raw_text)
        except Exception as exc:
            raise PlannerError(f"Gemini planner returned malformed output: {exc}") from exc

        outcome = validate_and_normalize_proposals(run.id, parsed.candidates, candidate_count)
        if not outcome.accepted:
            raise PlannerError(
                "Gemini proposed candidates but none passed deterministic validation: "
                + "; ".join(outcome.rejected)
            )

        if outcome.rejected:
            logger.warning(
                "some gemini candidate proposals were rejected by deterministic validation",
                extra={"context": {"run_id": run.id, "rejected": outcome.rejected}},
            )

        return PlannerResult(
            candidates=outcome.accepted,
            planning_summary=parsed.planning_summary.strip(),
            planner_name=f"gemini:{self._model}",
            rejected_proposals=outcome.rejected,
        )

    def should_continue_searching(self, run: OptimizationRun, results_so_far: list[CandidateConfiguration]) -> bool:
        return False


__all__ = ["GeminiAgentPlanner"]
