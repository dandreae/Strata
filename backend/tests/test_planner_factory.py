from __future__ import annotations

import pytest

from app.agent.deterministic_planner import DeterministicPlanner
from app.agent.factory import build_planner
from app.agent.gemini_planner import GeminiAgentPlanner
from app.agent.interfaces import PlannerError
from app.core.config import Settings


def _settings(**overrides) -> Settings:
    # Bypass the .env file / real environment for these tests entirely.
    return Settings(_env_file=None, **overrides)  # type: ignore[call-arg]


def test_deterministic_mode_builds_deterministic_planner() -> None:
    planner = build_planner(_settings(planner_mode="deterministic"))
    assert isinstance(planner, DeterministicPlanner)


def test_gemini_mode_builds_gemini_planner_when_key_present() -> None:
    planner = build_planner(_settings(planner_mode="gemini", gemini_api_key="test-key"))
    assert isinstance(planner, GeminiAgentPlanner)


def test_gemini_mode_without_api_key_fails_clearly() -> None:
    with pytest.raises(PlannerError, match="STRATA_GEMINI_API_KEY"):
        build_planner(_settings(planner_mode="gemini", gemini_api_key=None))


def test_unknown_mode_raises_value_error() -> None:
    with pytest.raises(ValueError, match="Unknown STRATA_PLANNER_MODE"):
        build_planner(_settings(planner_mode="not-a-real-mode"))
