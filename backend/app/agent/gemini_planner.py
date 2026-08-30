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
manufacturing metric; those come only from a real `SliceResult`. This holds
for both `plan_initial_candidates` (round 1) and `plan_next_round` (round
2) — the latter is *given* round 1's real measured results as read-only
context, never asked to predict new ones.

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

History, for anyone tuning this further (all findings from real calls, not
mocks). Round 1 (`plan_initial_candidates`) has succeeded cleanly on every
real call made against this milestone. Round 2 (`plan_next_round`)
truncated on its first two real attempts with `finish_reason=MAX_TOKENS` —
usage metadata was unambiguous: `thoughts_tokens=1919` out of the
`max_output_tokens=2048` budget, leaving only `candidates_tokens=112` for
the actual visible response. Not a prompt-verbosity problem (round 2's
prompt was short: `prompt_tokens=784`) and not a schema-shape problem
(trimming the instruction/schema and requiring the `candidates` field did
not fix it). The orchestrator's graceful-degradation path (see
app/services/orchestrator.py's `_run_round_two`) handled both failures
exactly as intended — the run still completed successfully on Round 1's
real results alone, never aborting and never silently falling back to a
different planner.

Fix (CONFIRMED against a real call, not just a hypothesis): `google.genai.
types.GenerateContentConfig.thinking_config` is a real, confirmed field —
and its own SDK docstring (on `ReinforcementTuningConfig.thinking_level`,
installed google-genai 2.18.1) states verbatim: "Starting from Gemini 3.5
models, the old thinking_budget will no longer be supported and will result
in a user error if set. Instead, users should use the thinking_level
parameter." That directly matches this project's model
(`gemini-3.5-flash`), so Round 2 sets `thinking_config=ThinkingConfig(
thinking_level="MINIMAL")` — the lowest defined level (MINIMAL < LOW <
MEDIUM < HIGH) — while `max_output_tokens` stays at 2048, unchanged. Round 1
is deliberately left unconfigured (model default); it has never shown this
problem. On the next real run after this change, Round 2 completed
successfully: proposed 8 candidates (1 correctly rejected as a duplicate of
a real Round 1 candidate — the cross-round dedup check working as intended
on live output), sliced all 7 accepted ones for real, and the global Pareto
frontier/winner were correctly recomputed across all 15 candidates from
both rounds. See `_ROUND_TWO_THINKING_LEVEL` and `plan_next_round`.
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Coroutine
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from app.agent.interfaces import AgentPlanner, PlannerError, PlannerResult, RoundDecision
from app.agent.planner_schema import PlannerOutput, RoundDecisionOutput
from app.agent.planner_validation import (
    INFILL_MAX_PERCENT,
    INFILL_MIN_PERCENT,
    LAYER_HEIGHT_MAX_MM,
    LAYER_HEIGHT_MIN_MM,
    PERIMETER_MAX,
    PERIMETER_MIN,
    validate_and_normalize_proposals,
)
from app.core.logging import get_logger
from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.run import OptimizationRun
from app.optimization.constraints import satisfies_hard_constraints

logger = get_logger(__name__)

_PLANNER_APP_NAME = "strata-experiment-planner"
_PLANNER_USER_ID = "strata"

# Cost control: bounds the response so a verbose/looping generation can't
# run away, while staying well below a model's unbounded default. 1024 was
# tried first (an estimate: 8 candidates x 3 short numeric fields + a
# summary sentence) and was too tight in practice — a real call was cut off
# mid-JSON. 2048 fixed Round 1 (confirmed working across multiple real
# calls) but Round 2 has since truncated on every real attempt with
# finish_reason=MAX_TOKENS — real usage data shows ~1900 tokens going to
# the model's internal "thinking" before it starts the visible JSON,
# leaving too little of the 2048 budget for the response itself (see the
# module docstring's "Known open issue" for the full, confirmed diagnosis).
# Deliberately NOT raised past 2048 here: that's a real cost/latency
# tradeoff (a materially larger budget, spent mostly on thinking tokens on
# every Round 2 call) to decide explicitly, not to bump automatically.
_MAX_OUTPUT_TOKENS = 2048

# Round 2 only (see plan_next_round): the lowest defined level in
# `google.genai.types.ThinkingLevel` (MINIMAL < LOW < MEDIUM < HIGH),
# confirmed via SDK introspection to be the CURRENT mechanism for this
# model generation — `google.genai.types` (installed: 2.18.1) documents,
# verbatim, on `ReinforcementTuningConfig.thinking_level`: "Starting from
# Gemini 3.5 models, the old thinking_budget will no longer be supported
# and will result in a user error if set. Instead, users should use the
# thinking_level parameter." `thinking_budget` (a raw token count) is the
# older, now-incompatible mechanism for this model — not used here. Round 1
# is left unconfigured (model default) since it has never shown this
# problem; only Round 2's own real calls have.
_ROUND_TWO_THINKING_LEVEL = "MINIMAL"

# Retry handling for transient Gemini/ADK failures only — real capacity/rate
# limiting the model API itself reports, confirmed via source introspection
# of the installed google-genai 2.18.1 (`google/genai/errors.py`):
# `APIError` carries a real `.code` (HTTP status) and `.status` (e.g.
# "UNAVAILABLE", "RESOURCE_EXHAUSTED"); 4xx raises `ClientError`, 5xx raises
# `ServerError`, both `APIError` subclasses. These five codes are the
# conventional retryable set (rate limiting + server-side unavailability) —
# NOT a blanket "retry all errors": a 400 (malformed request) or 401/403
# (auth failure) is a real, permanent problem a retry cannot fix and is
# deliberately excluded. Backoff (1s, 2s, 4s) is sized for an interactive
# demo request, not a background job — worst case adds ~7s before giving up,
# never hangs indefinitely.
_RETRYABLE_GEMINI_STATUS_CODES = frozenset({429, 500, 502, 503, 504})
_MAX_RETRY_ATTEMPTS = 3
_RETRY_BACKOFF_SECONDS = (1, 2, 4)


def _is_transient_gemini_error(exc: Exception) -> bool:
    """True only for a real `google.genai.errors.APIError` (or subclass)
    whose `.code` is one of the conventional retryable HTTP status codes.
    Any other exception — malformed output, auth failure, a plain
    `ValueError`, anything not this specific, real error shape — is treated
    as non-transient and is never retried."""
    from google.genai.errors import APIError

    return isinstance(exc, APIError) and exc.code in _RETRYABLE_GEMINI_STATUS_CODES


_T = TypeVar("_T")


def _run_coroutine_sync(coro: Coroutine[object, object, _T]) -> _T:
    """Run `coro` to completion from synchronous code, regardless of
    whether the calling thread already has an event loop running (FastAPI's
    request path) or not (tests, scripts) — see module docstring for the
    two real bugs this specifically fixes.
    """
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _describe_event(event: object) -> str:
    """Real diagnostic summary of one ADK event — finish reason and token
    usage, when the SDK exposes them — for PlannerError messages. Not
    guessed: `finish_reason`/`usage_metadata` are real fields on
    `google.adk.events.Event` (confirmed via introspection). Notably
    includes `thoughts_token_count`: a model's internal "thinking" tokens
    are billed against the same `max_output_tokens` budget as its visible
    response, so a large thoughts count with a small/absent visible response
    is real evidence the budget was consumed before the visible JSON could
    be written — as opposed to a content filter or a network issue.
    """
    finish_reason = getattr(event, "finish_reason", None)
    usage = getattr(event, "usage_metadata", None)
    parts = [f"finish_reason={finish_reason}"]
    if usage is not None:
        parts.append(f"prompt_tokens={usage.prompt_token_count}")
        parts.append(f"thoughts_tokens={usage.thoughts_token_count}")
        parts.append(f"candidates_tokens={usage.candidates_token_count}")
        parts.append(f"total_tokens={usage.total_token_count}")
    else:
        parts.append("usage_metadata=unavailable")
    return ", ".join(parts)


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

_ROUND_TWO_INSTRUCTION = """You are Strata's manufacturing experiment planner for FDM 3D printing,
reviewing real measured results from Round 1.

You are given each Round 1 candidate's configuration, its real measured
print time and filament usage (or its slicing failure reason), whether it
met the user's hard constraints, and whether it is Pareto-optimal.

Decide: continue with a new round, or stop. Stop if Round 1 already covers
the useful tradeoff space or the constraints rule out further gains.

If you continue, propose up to the requested number of new candidates,
each different from every Round 1 configuration and from each other, within
the same layer_height/infill_percent/perimeter_count bounds as before,
targeting tradeoff regions Round 1 did not cover.

`reasoning_summary`: one or two plain sentences for an audit log. Not a
step-by-step justification."""


def _build_prompt(run: OptimizationRun, candidate_count: int) -> str:
    prefs = run.optimization_preferences
    constraints = run.hard_constraints
    return (
        f"Propose {candidate_count} candidate configurations for this manufacturing run.\n\n"
        f"Production quantity: {run.production_quantity}\n"
        f"Hard constraint - max print time: {constraints.max_print_time_seconds} seconds\n"
        f"Hard constraint - max filament usage: {constraints.max_filament_grams} grams\n"
        f"User's optimization preference: {prefs.objective.value}\n"
        f"Allowed layer_height range: {LAYER_HEIGHT_MIN_MM}-{LAYER_HEIGHT_MAX_MM} mm\n"
        f"Allowed infill_percent range: {INFILL_MIN_PERCENT}-{INFILL_MAX_PERCENT} %\n"
        f"Allowed perimeter_count range: {PERIMETER_MIN}-{PERIMETER_MAX}\n"
        f"Number of candidates to propose: {candidate_count}\n"
    )


def _build_round_two_prompt(
    run: OptimizationRun,
    previous_results: list[CandidateConfiguration],
    candidate_count: int,
) -> str:
    prefs = run.optimization_preferences
    constraints = run.hard_constraints

    lines = [f"Round 1 measured results for this manufacturing run ({len(previous_results)} candidates tested):", ""]
    for i, c in enumerate(previous_results, 1):
        if c.status == CandidateStatus.SUCCEEDED:
            feasible = satisfies_hard_constraints(c, constraints)
            lines.append(
                f"#{i}: layer_height={c.layer_height}mm infill_percent={c.infill_percent}% "
                f"perimeter_count={c.perimeter_count} -> print_time_seconds={c.print_time_seconds} "
                f"filament_grams={c.filament_grams} feasible={feasible} pareto_optimal={c.is_pareto_optimal}"
            )
        else:
            lines.append(
                f"#{i}: layer_height={c.layer_height}mm infill_percent={c.infill_percent}% "
                f"perimeter_count={c.perimeter_count} -> SLICING FAILED ({c.failure_reason})"
            )

    lines += [
        "",
        f"Production quantity: {run.production_quantity}",
        f"Hard constraint - max print time: {constraints.max_print_time_seconds} seconds",
        f"Hard constraint - max filament usage: {constraints.max_filament_grams} grams",
        f"User's optimization preference: {prefs.objective.value}",
        f"Allowed layer_height range: {LAYER_HEIGHT_MIN_MM}-{LAYER_HEIGHT_MAX_MM} mm",
        f"Allowed infill_percent range: {INFILL_MIN_PERCENT}-{INFILL_MAX_PERCENT} %",
        f"Allowed perimeter_count range: {PERIMETER_MIN}-{PERIMETER_MAX}",
        f"Maximum new candidates you may propose: {candidate_count}",
    ]
    return "\n".join(lines)


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

    def _call_llm(
        self,
        *,
        run_id: str,
        agent_name: str,
        description: str,
        instruction: str,
        output_schema: type,
        prompt: str,
        thinking_level: str | None = None,
    ) -> tuple[str, str]:
        """Shared ADK boundary for both rounds: build a single-turn LlmAgent,
        run it (retrying only real, transient Gemini errors — see
        `_is_transient_gemini_error`), and return (raw structured-output
        text, diagnostics string). Diagnostics include finish reason and
        token usage — including `thoughts_token_count`, since "thinking"
        tokens count against the same `max_output_tokens` budget as the
        visible response and can starve it. Raises PlannerError for any
        failure (network, auth, empty response, or a transient error that
        didn't clear within the retry budget) — never returns a fabricated/
        partial result, and never silently falls back to a different
        planner.

        `thinking_level` (a `google.genai.types.ThinkingLevel` value, e.g.
        "MINIMAL") is optional and unset by default — pass it to cap how
        much of the output-token budget a call spends on internal
        deliberation before writing its visible response; see
        `_ROUND_TWO_THINKING_LEVEL`.
        """
        from google.adk.agents import LlmAgent
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types

        content_config_kwargs: dict[str, object] = {"max_output_tokens": _MAX_OUTPUT_TOKENS}
        if thinking_level is not None:
            content_config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_level=thinking_level)

        agent = LlmAgent(
            model=self._model,
            name=agent_name,
            description=description,
            instruction=instruction,
            output_schema=output_schema,
            generate_content_config=types.GenerateContentConfig(**content_config_kwargs),
        )

        async def _call_once() -> tuple[str | None, str]:
            session_service = InMemorySessionService()
            session = await session_service.create_session(app_name=_PLANNER_APP_NAME, user_id=_PLANNER_USER_ID)
            runner = Runner(agent=agent, app_name=_PLANNER_APP_NAME, session_service=session_service)
            content = types.Content(role="user", parts=[types.Part(text=prompt)])

            text: str | None = None
            diagnostics = "no events received"
            async for event in runner.run_async(user_id=_PLANNER_USER_ID, session_id=session.id, new_message=content):
                diagnostics = _describe_event(event)
                if event.is_final_response() and event.content and event.content.parts:
                    text = event.content.parts[0].text
            return text, diagnostics

        attempt = 1
        while True:
            try:
                raw_text, diagnostics = _run_coroutine_sync(_call_once())
                break
            except Exception as exc:
                retries_left = _MAX_RETRY_ATTEMPTS - (attempt - 1)
                if not _is_transient_gemini_error(exc) or retries_left <= 0:
                    # Non-transient (auth failure, malformed request, quota
                    # exhausted with no retry left, model-not-found, etc.) or
                    # the retry budget is spent — surface clearly. No silent
                    # fallback to the deterministic planner from inside
                    # "gemini" mode.
                    raise PlannerError(f"Gemini planner call failed: {exc}") from exc

                delay = _RETRY_BACKOFF_SECONDS[attempt - 1]
                logger.warning(
                    f"transient Gemini error (attempt {attempt}/{_MAX_RETRY_ATTEMPTS + 1}), "
                    f"retrying in {delay}s",
                    extra={
                        "context": {
                            "run_id": run_id,
                            "attempt": attempt,
                            "max_attempts": _MAX_RETRY_ATTEMPTS + 1,
                            "delay_seconds": delay,
                            "error_code": getattr(exc, "code", None),
                            "error_status": getattr(exc, "status", None),
                        }
                    },
                )
                time.sleep(delay)
                attempt += 1

        if not raw_text:
            raise PlannerError(f"Gemini planner returned no response. ({diagnostics})")
        return raw_text, diagnostics

    def plan_initial_candidates(self, run: OptimizationRun, candidate_count: int) -> PlannerResult:
        raw_text, diagnostics = self._call_llm(
            run_id=run.id,
            agent_name="strata_experiment_planner",
            description="Proposes bounded FDM 3D-printing manufacturing experiments for Strata.",
            instruction=_INSTRUCTION,
            output_schema=PlannerOutput,
            prompt=_build_prompt(run, candidate_count),
        )

        try:
            parsed = PlannerOutput.model_validate_json(raw_text)
        except Exception as exc:
            raise PlannerError(f"Gemini planner returned malformed output: {exc} ({diagnostics})") from exc

        outcome = validate_and_normalize_proposals(run.id, parsed.candidates, candidate_count, round_number=1)
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

    def plan_next_round(
        self,
        run: OptimizationRun,
        previous_results: list[CandidateConfiguration],
        candidate_count: int,
    ) -> RoundDecision:
        raw_text, diagnostics = self._call_llm(
            run_id=run.id,
            agent_name="strata_round_two_planner",
            description=(
                "Decides whether to continue experimenting and proposes new bounded "
                "FDM 3D-printing candidates informed by real Round 1 results."
            ),
            instruction=_ROUND_TWO_INSTRUCTION,
            output_schema=RoundDecisionOutput,
            prompt=_build_round_two_prompt(run, previous_results, candidate_count),
            thinking_level=_ROUND_TWO_THINKING_LEVEL,
        )

        try:
            parsed = RoundDecisionOutput.model_validate_json(raw_text)
        except Exception as exc:
            raise PlannerError(f"Gemini round-2 planner returned malformed output: {exc} ({diagnostics})") from exc

        planner_name = f"gemini:{self._model}"

        if not parsed.continue_optimization:
            return RoundDecision(
                should_continue=False,
                reasoning_summary=parsed.reasoning_summary.strip(),
                planner_name=planner_name,
            )

        outcome = validate_and_normalize_proposals(
            run.id, parsed.candidates, candidate_count, existing=previous_results, round_number=2
        )

        if not outcome.accepted:
            # Gemini wanted to continue but proposed nothing usable (e.g.
            # every proposal duplicated Round 1, or was out of bounds).
            # Round 1's real results are already complete and valid — treat
            # this as an effective stop rather than a planner failure.
            summary = parsed.reasoning_summary.strip()
            if outcome.rejected:
                summary += " (All proposed candidates were rejected by validation: " + "; ".join(outcome.rejected) + ")"
            return RoundDecision(
                should_continue=False,
                reasoning_summary=summary,
                planner_name=planner_name,
                rejected_proposals=outcome.rejected,
            )

        if outcome.rejected:
            logger.warning(
                "some gemini round-2 candidate proposals were rejected by deterministic validation",
                extra={"context": {"run_id": run.id, "rejected": outcome.rejected}},
            )

        return RoundDecision(
            should_continue=True,
            reasoning_summary=parsed.reasoning_summary.strip(),
            candidates=outcome.accepted,
            planner_name=planner_name,
            rejected_proposals=outcome.rejected,
        )


__all__ = ["GeminiAgentPlanner"]
