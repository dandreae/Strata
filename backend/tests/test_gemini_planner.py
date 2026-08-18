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


def _fake_event(text: str | None, final: bool = True) -> MagicMock:
    event = MagicMock()
    event.is_final_response.return_value = final
    if text is None:
        event.content = None
    else:
        part = MagicMock()
        part.text = text
        event.content = MagicMock()
        event.content.parts = [part]
    return event


async def _async_event_gen(events):
    for event in events:
        yield event


def _install_fake_adk(monkeypatch, *, run_return=None, run_side_effect=None) -> MagicMock:
    """Patches the ADK boundary at its source modules so no network call
    happens. Returns the fake Runner instance so tests can assert on calls.

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
        fake_runner_instance.run_async = run_side_effect
    else:
        events = run_return or []
        fake_runner_instance.run_async = lambda **kwargs: _async_event_gen(events)

    monkeypatch.setattr("google.adk.sessions.InMemorySessionService", lambda: fake_session_service_instance)
    monkeypatch.setattr("google.adk.runners.Runner", lambda **kwargs: fake_runner_instance)
    monkeypatch.setattr("google.adk.agents.LlmAgent", lambda **kwargs: MagicMock())

    return fake_runner_instance


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
