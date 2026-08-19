"""Unit tests for GeminiAgentPlanner with the ADK/Gemini boundary mocked.

These never touch the network — `google.adk.agents.LlmAgent`,
`google.adk.runners.Runner`, and `google.adk.sessions.InMemorySessionService`
are patched at their source modules (the same lookup a lazy `from ... import`
resolves against). `pytest -q` must never require credentials; see
test_gemini_smoke.py for the real, explicitly-separate, credential-gated call.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agent.gemini_planner import GeminiAgentPlanner
from app.agent.interfaces import PlannerError
from app.models.candidate import CandidateConfiguration, CandidateStatus
from app.models.run import HardConstraints, OptimizationObjective, OptimizationPreferences, OptimizationRun


def _make_run(**overrides) -> OptimizationRun:
    defaults = dict(
        filename="part.stl",
        production_quantity=500,
        printer_profile="generic_pla",
        hard_constraints=HardConstraints(max_print_time_seconds=1800, max_filament_grams=10),
        optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_MATERIAL),
    )
    defaults.update(overrides)
    return OptimizationRun(**defaults)


def _fake_event(
    text: str | None,
    final: bool = True,
    finish_reason: str | None = None,
    usage_metadata: MagicMock | None = None,
) -> MagicMock:
    event = MagicMock()
    event.is_final_response.return_value = final
    event.finish_reason = finish_reason
    event.usage_metadata = usage_metadata
    if text is None:
        event.content = None
    else:
        part = MagicMock()
        part.text = text
        event.content = MagicMock()
        event.content.parts = [part]
    return event


def _fake_usage(*, prompt=100, thoughts=0, candidates=0, total=100) -> MagicMock:
    usage = MagicMock()
    usage.prompt_token_count = prompt
    usage.thoughts_token_count = thoughts
    usage.candidates_token_count = candidates
    usage.total_token_count = total
    return usage


async def _async_event_gen(events):
    for event in events:
        yield event


def _install_fake_adk(monkeypatch, *, run_return=None, run_side_effect=None) -> tuple[MagicMock, MagicMock]:
    """Patches the ADK boundary at its source modules so no network call
    happens. Returns (fake Runner instance, fake LlmAgent constructor) so
    tests can assert on calls, including exactly what LlmAgent was built
    with (e.g. the output-token cap).

    Mocks `run_async` (an async generator method), not the synchronous
    `run()` wrapper — that's what GeminiAgentPlanner actually calls; see
    its module docstring for why `run()` isn't used.
    """
    fake_session = MagicMock()
    fake_session.id = "fake-session"

    fake_session_service_instance = MagicMock()
    fake_session_service_instance.create_session = AsyncMock(return_value=fake_session)

    fake_runner_instance = MagicMock()
    if run_side_effect is not None:
        fake_runner_instance.run_async = MagicMock(side_effect=run_side_effect)
    else:
        events = run_return or []
        # A MagicMock wrapper (not a bare lambda) so tests can assert
        # call_count — the actual proxy for "how many model calls were made".
        fake_runner_instance.run_async = MagicMock(side_effect=lambda **kwargs: _async_event_gen(events))

    fake_llm_agent_ctor = MagicMock(side_effect=lambda **kwargs: MagicMock())

    monkeypatch.setattr("google.adk.sessions.InMemorySessionService", lambda: fake_session_service_instance)
    monkeypatch.setattr("google.adk.runners.Runner", lambda **kwargs: fake_runner_instance)
    monkeypatch.setattr("google.adk.agents.LlmAgent", fake_llm_agent_ctor)

    return fake_runner_instance, fake_llm_agent_ctor


VALID_RESPONSE = json.dumps(
    {
        "candidates": [
            {"layer_height": 0.15, "infill_percent": 10, "perimeter_count": 2},
            {"layer_height": 0.25, "infill_percent": 30, "perimeter_count": 3},
        ],
        "planning_summary": "Exploring low-material and higher-infill configurations.",
    }
)


# --- construction / credentials ------------------------------------------


def test_construction_without_api_key_raises_immediately() -> None:
    with pytest.raises(PlannerError, match="STRATA_GEMINI_API_KEY"):
        GeminiAgentPlanner(api_key="", model="gemini-3.5-flash")


def test_construction_sets_google_api_key_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    GeminiAgentPlanner(api_key="test-key-123", model="gemini-3.5-flash")
    import os

    assert os.environ["GOOGLE_API_KEY"] == "test-key-123"


# --- successful call ---------------------------------------------------


def test_successful_call_returns_validated_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_adk(monkeypatch, run_return=[_fake_event(VALID_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    result = planner.plan_initial_candidates(_make_run(), candidate_count=2)

    assert len(result.candidates) == 2
    assert {c.layer_height for c in result.candidates} == {0.15, 0.25}
    assert result.planner_name == "gemini:gemini-3.5-flash"
    assert "material" in result.planning_summary.lower()
    assert result.rejected_proposals == []
    # Never invents manufacturing metrics — nothing here should populate them.
    assert all(c.print_time_seconds is None and c.filament_grams is None for c in result.candidates)


def test_exactly_one_model_call_per_plan_invocation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cost control: one plan_initial_candidates() call must issue exactly
    one underlying model call — no retries/duplicate calls on the happy path."""
    fake_runner_instance, fake_llm_agent_ctor = _install_fake_adk(
        monkeypatch, run_return=[_fake_event(VALID_RESPONSE)]
    )
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    planner.plan_initial_candidates(_make_run(), candidate_count=2)

    assert fake_llm_agent_ctor.call_count == 1  # one LlmAgent built
    assert fake_runner_instance.run_async.call_count == 1  # one model turn


def test_llm_agent_configured_with_output_token_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cost control: the call must bound max_output_tokens, not rely on the
    model's unbounded default. See _MAX_OUTPUT_TOKENS in gemini_planner.py."""
    from app.agent.gemini_planner import _MAX_OUTPUT_TOKENS

    _, fake_llm_agent_ctor = _install_fake_adk(monkeypatch, run_return=[_fake_event(VALID_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    planner.plan_initial_candidates(_make_run(), candidate_count=2)

    assert fake_llm_agent_ctor.call_count == 1
    config = fake_llm_agent_ctor.call_args.kwargs["generate_content_config"]
    assert config.max_output_tokens == _MAX_OUTPUT_TOKENS
    assert fake_llm_agent_ctor.call_args.kwargs["output_schema"] is not None


def test_planning_summary_never_used_as_a_manufacturing_metric(monkeypatch: pytest.MonkeyPatch) -> None:
    """Regression guard: even if Gemini's summary text mentions numbers, they
    must never end up on a CandidateConfiguration's metric fields."""
    response = json.dumps(
        {
            "candidates": [{"layer_height": 0.2, "infill_percent": 20, "perimeter_count": 2}],
            "planning_summary": "This should take about 17 minutes and use 4 grams.",
        }
    )
    _install_fake_adk(monkeypatch, run_return=[_fake_event(response)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    result = planner.plan_initial_candidates(_make_run(), candidate_count=1)

    assert result.candidates[0].print_time_seconds is None
    assert result.candidates[0].filament_grams is None


# --- malformed / rejected output ------------------------------------------


def test_malformed_json_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_adk(monkeypatch, run_return=[_fake_event("not valid json at all")])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="malformed"):
        planner.plan_initial_candidates(_make_run(), candidate_count=2)


def test_missing_required_field_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    bad_response = json.dumps({"candidates": [{"layer_height": 0.2}]})  # missing infill/perimeters
    _install_fake_adk(monkeypatch, run_return=[_fake_event(bad_response)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="malformed"):
        planner.plan_initial_candidates(_make_run(), candidate_count=1)


def test_no_final_response_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_adk(monkeypatch, run_return=[_fake_event(None, final=False)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="no response"):
        planner.plan_initial_candidates(_make_run(), candidate_count=2)


def test_no_final_response_error_includes_finish_reason_and_token_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real diagnostic capture: a truncated/cut-off generation (no final
    event ever arrives) must surface finish_reason and token usage —
    including thoughts_token_count — in the error, not just "no response"."""
    truncated_event = _fake_event(
        None, final=False, finish_reason="MAX_TOKENS", usage_metadata=_fake_usage(thoughts=1900, candidates=5, total=2000)
    )
    _install_fake_adk(monkeypatch, run_return=[truncated_event])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError) as exc_info:
        planner.plan_initial_candidates(_make_run(), candidate_count=2)

    message = str(exc_info.value)
    assert "MAX_TOKENS" in message
    assert "thoughts_tokens=1900" in message


def test_malformed_output_error_includes_diagnostics(monkeypatch: pytest.MonkeyPatch) -> None:
    event = _fake_event(
        "not valid json", finish_reason="STOP", usage_metadata=_fake_usage(thoughts=50, candidates=10, total=160)
    )
    _install_fake_adk(monkeypatch, run_return=[event])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError) as exc_info:
        planner.plan_initial_candidates(_make_run(), candidate_count=2)

    message = str(exc_info.value)
    assert "malformed" in message
    assert "finish_reason=STOP" in message
    assert "thoughts_tokens=50" in message


def test_all_proposals_failing_validation_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    out_of_bounds = json.dumps(
        {
            "candidates": [{"layer_height": 5.0, "infill_percent": -20, "perimeter_count": 100}],
            "planning_summary": "Testing extremes.",
        }
    )
    _install_fake_adk(monkeypatch, run_return=[_fake_event(out_of_bounds)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="none passed"):
        planner.plan_initial_candidates(_make_run(), candidate_count=1)


def test_partially_invalid_proposals_surfaces_rejections_but_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    mixed = json.dumps(
        {
            "candidates": [
                {"layer_height": 0.2, "infill_percent": 20, "perimeter_count": 2},  # valid
                {"layer_height": 5.0, "infill_percent": 20, "perimeter_count": 2},  # invalid
            ],
            "planning_summary": "Mixed batch.",
        }
    )
    _install_fake_adk(monkeypatch, run_return=[_fake_event(mixed)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    result = planner.plan_initial_candidates(_make_run(), candidate_count=2)

    assert len(result.candidates) == 1
    assert len(result.rejected_proposals) == 1
    assert "layer_height" in result.rejected_proposals[0]


# --- network/call failure -------------------------------------------------


def test_runner_exception_raises_planner_error_not_silent_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**kwargs):
        raise ConnectionError("connection refused")

    _install_fake_adk(monkeypatch, run_side_effect=_boom)
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="Gemini planner call failed"):
        planner.plan_initial_candidates(_make_run(), candidate_count=2)


def test_candidate_count_is_still_capped_for_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    """Even a well-formed, in-bounds Gemini response cannot cause more
    slicing jobs than the requested/allowed count."""
    many = json.dumps(
        {
            "candidates": [
                {"layer_height": round(0.10 + 0.01 * i, 2), "infill_percent": 10 + i, "perimeter_count": 2}
                for i in range(20)
            ],
            "planning_summary": "Wide sweep.",
        }
    )
    _install_fake_adk(monkeypatch, run_return=[_fake_event(many)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    result = planner.plan_initial_candidates(_make_run(), candidate_count=8)

    assert len(result.candidates) == 8


# --- round 2: plan_next_round ---------------------------------------------


def _round1_result(**overrides) -> CandidateConfiguration:
    defaults = dict(
        run_id="run-1",
        layer_height=0.20,
        infill_percent=20,
        perimeter_count=2,
        status=CandidateStatus.SUCCEEDED,
        print_time_seconds=1000,
        filament_grams=4.0,
        round=1,
    )
    defaults.update(overrides)
    return CandidateConfiguration(**defaults)


ROUND_TWO_STOP_RESPONSE = json.dumps(
    {
        "continue_optimization": False,
        "reasoning_summary": "Round 1 already covers the useful tradeoff space.",
        "candidates": [],
    }
)

ROUND_TWO_CONTINUE_RESPONSE = json.dumps(
    {
        "continue_optimization": True,
        "reasoning_summary": "Targeting a lower-material region not yet explored.",
        "candidates": [
            {"layer_height": 0.12, "infill_percent": 8, "perimeter_count": 2},
        ],
    }
)


def test_round_two_stop_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_adk(monkeypatch, run_return=[_fake_event(ROUND_TWO_STOP_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    decision = planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)

    assert decision.should_continue is False
    assert decision.candidates == []
    assert "tradeoff space" in decision.reasoning_summary
    assert decision.planner_name == "gemini:gemini-3.5-flash"


def test_round_two_continue_decision_returns_validated_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_adk(monkeypatch, run_return=[_fake_event(ROUND_TWO_CONTINUE_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    decision = planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)

    assert decision.should_continue is True
    assert len(decision.candidates) == 1
    assert decision.candidates[0].layer_height == 0.12
    assert decision.candidates[0].round == 2
    # Never invents manufacturing metrics for the new proposals either.
    assert decision.candidates[0].print_time_seconds is None
    assert decision.candidates[0].filament_grams is None


def test_round_two_duplicate_of_round_one_gracefully_stops_not_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini says continue but proposes only a duplicate of Round 1 — this
    must NOT raise PlannerError (Round 1's results are already valid); it
    should be treated as an effective stop."""
    duplicate_response = json.dumps(
        {
            "continue_optimization": True,
            "reasoning_summary": "Retrying the same configuration.",
            "candidates": [{"layer_height": 0.20, "infill_percent": 20, "perimeter_count": 2}],
        }
    )
    _install_fake_adk(monkeypatch, run_return=[_fake_event(duplicate_response)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    decision = planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)

    assert decision.should_continue is False
    assert decision.candidates == []
    assert len(decision.rejected_proposals) == 1
    assert "duplicate" in decision.rejected_proposals[0]


def test_round_two_call_failure_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**kwargs):
        raise ConnectionError("connection refused")

    _install_fake_adk(monkeypatch, run_side_effect=_boom)
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="Gemini planner call failed"):
        planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)


def test_round_two_malformed_output_raises_planner_error(monkeypatch: pytest.MonkeyPatch) -> None:
    _install_fake_adk(monkeypatch, run_return=[_fake_event("not json")])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    with pytest.raises(PlannerError, match="malformed"):
        planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)


def test_round_two_exactly_one_model_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cost control: one plan_next_round() call must issue exactly one
    underlying model call, same as round 1."""
    fake_runner_instance, fake_llm_agent_ctor = _install_fake_adk(
        monkeypatch, run_return=[_fake_event(ROUND_TWO_CONTINUE_RESPONSE)]
    )
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)

    assert fake_llm_agent_ctor.call_count == 1
    assert fake_runner_instance.run_async.call_count == 1


def test_round_two_uses_same_output_token_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.agent.gemini_planner import _MAX_OUTPUT_TOKENS

    _, fake_llm_agent_ctor = _install_fake_adk(monkeypatch, run_return=[_fake_event(ROUND_TWO_STOP_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)

    config = fake_llm_agent_ctor.call_args.kwargs["generate_content_config"]
    assert config.max_output_tokens == _MAX_OUTPUT_TOKENS


def test_round_two_sets_minimal_thinking_level(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 2 must configure the lowest defined thinking level, via the
    real `google.genai.types.ThinkingConfig` (not a stand-in), while keeping
    max_output_tokens=2048 unchanged. See _ROUND_TWO_THINKING_LEVEL."""
    from google.genai import types

    from app.agent.gemini_planner import _MAX_OUTPUT_TOKENS, _ROUND_TWO_THINKING_LEVEL

    _, fake_llm_agent_ctor = _install_fake_adk(monkeypatch, run_return=[_fake_event(ROUND_TWO_STOP_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    planner.plan_next_round(_make_run(), [_round1_result()], candidate_count=8)

    config = fake_llm_agent_ctor.call_args.kwargs["generate_content_config"]
    assert isinstance(config, types.GenerateContentConfig)
    assert config.max_output_tokens == _MAX_OUTPUT_TOKENS  # unchanged, per requirement
    assert config.thinking_config is not None
    assert isinstance(config.thinking_config, types.ThinkingConfig)
    assert config.thinking_config.thinking_level == types.ThinkingLevel.MINIMAL
    assert _ROUND_TWO_THINKING_LEVEL == "MINIMAL"
    # thinking_budget (the OLDER, now-incompatible-with-gemini-3.5 mechanism)
    # must never be set alongside thinking_level.
    assert config.thinking_config.thinking_budget is None


def test_round_one_does_not_set_thinking_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Round 1 has never shown the truncation problem — it stays
    unconfigured (model default), only Round 2 sets thinking_level."""
    _, fake_llm_agent_ctor = _install_fake_adk(monkeypatch, run_return=[_fake_event(VALID_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    planner.plan_initial_candidates(_make_run(), candidate_count=2)

    config = fake_llm_agent_ctor.call_args.kwargs["generate_content_config"]
    assert config.thinking_config is None


def test_round_two_prompt_contains_real_round_one_metrics_not_predictions(monkeypatch: pytest.MonkeyPatch) -> None:
    """Gemini is given Round 1's REAL measured results as read-only context
    — it must never be asked to predict them. Verify the actual prompt text
    sent contains the real numbers, proving they came from SliceResult, not
    from Gemini itself."""
    fake_runner_instance, _ = _install_fake_adk(monkeypatch, run_return=[_fake_event(ROUND_TWO_STOP_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    previous = [_round1_result(print_time_seconds=1234, filament_grams=5.67)]
    planner.plan_next_round(_make_run(), previous, candidate_count=8)

    sent_content = fake_runner_instance.run_async.call_args.kwargs["new_message"]
    prompt_text = sent_content.parts[0].text
    assert "1234" in prompt_text
    assert "5.67" in prompt_text
    assert "feasible=" in prompt_text
    assert "pareto_optimal=" in prompt_text


def test_round_two_includes_failed_round_one_candidates_in_context(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Round 1 candidate that failed to slice is still described (with its
    failure reason), not silently dropped from Gemini's context."""
    fake_runner_instance, _ = _install_fake_adk(monkeypatch, run_return=[_fake_event(ROUND_TWO_STOP_RESPONSE)])
    planner = GeminiAgentPlanner(api_key="test-key", model="gemini-3.5-flash")

    failed = _round1_result(
        status=CandidateStatus.FAILED,
        print_time_seconds=None,
        filament_grams=None,
        failure_reason="prusa-slicer exited with code 1",
    )
    planner.plan_next_round(_make_run(), [failed], candidate_count=8)

    sent_content = fake_runner_instance.run_async.call_args.kwargs["new_message"]
    prompt_text = sent_content.parts[0].text
    assert "SLICING FAILED" in prompt_text
    assert "prusa-slicer exited with code 1" in prompt_text
