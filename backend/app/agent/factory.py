"""Resolves STRATA_PLANNER_MODE into a concrete AgentPlanner at startup.

Deliberately fails fast and loud: if `gemini` mode is requested without
credentials, this raises immediately (see app/main.py's lifespan) rather
than letting the server start and fail on the first real request.
"""

from __future__ import annotations

from app.agent.deterministic_planner import DeterministicPlanner
from app.agent.gemini_planner import GeminiAgentPlanner
from app.agent.interfaces import AgentPlanner
from app.core.config import Settings

PLANNER_MODE_DETERMINISTIC = "deterministic"
PLANNER_MODE_GEMINI = "gemini"


def build_planner(settings: Settings) -> AgentPlanner:
    if settings.planner_mode == PLANNER_MODE_DETERMINISTIC:
        return DeterministicPlanner()

    if settings.planner_mode == PLANNER_MODE_GEMINI:
        # Raises PlannerError if gemini_api_key is unset — intentional,
        # see module docstring.
        return GeminiAgentPlanner(api_key=settings.gemini_api_key or "", model=settings.gemini_model)

    raise ValueError(
        f"Unknown STRATA_PLANNER_MODE: {settings.planner_mode!r} "
        f"(expected {PLANNER_MODE_DETERMINISTIC!r} or {PLANNER_MODE_GEMINI!r})."
    )


__all__ = ["build_planner", "PLANNER_MODE_DETERMINISTIC", "PLANNER_MODE_GEMINI"]
