"""Deterministic placeholder for candidate generation.

This is NOT the agent — it's the seam where `AgentPlanner.propose_candidates`
(see `app/agent/interfaces.py`) will eventually plug in. Until Gemini/ADK
planning exists, Strata always tries exactly one, fixed, conservative
configuration rather than searching. No LLM calls happen here.
"""

from __future__ import annotations

from app.models.candidate import CandidateConfiguration

# Conservative MVP defaults: no rotation, a common general-purpose layer
# height/infill, no supports, a minimal-but-reasonable perimeter count.
DEFAULT_LAYER_HEIGHT_MM = 0.20
DEFAULT_INFILL_PERCENT = 20
DEFAULT_SUPPORTS_ENABLED = False
DEFAULT_PERIMETER_COUNT = 2


def build_default_candidate(run_id: str) -> CandidateConfiguration:
    """Build the single default candidate configuration for `run_id`.

    Replace the call site of this function (not this function itself) once
    `AgentPlanner.propose_candidates` exists and can generate — and
    iterate on — multiple candidates informed by prior results.
    """
    return CandidateConfiguration(
        run_id=run_id,
        orientation_x=0.0,
        orientation_y=0.0,
        orientation_z=0.0,
        layer_height=DEFAULT_LAYER_HEIGHT_MM,
        infill_percent=DEFAULT_INFILL_PERCENT,
        supports_enabled=DEFAULT_SUPPORTS_ENABLED,
        perimeter_count=DEFAULT_PERIMETER_COUNT,
    )


__all__ = ["build_default_candidate"]
