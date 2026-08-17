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
    """Build a single conservative default candidate configuration.

    Superseded as the live `/api/v1/runs` path by `generate_candidate_set`
    below, but kept as a small, still-useful/tested building block (e.g. for
    isolated slicer tests that only need one candidate).
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


# --- Deterministic multi-candidate set -------------------------------------
#
# (layer_height_mm, infill_percent, perimeter_count) tuples, hand-chosen to
# create real print-time/material tradeoffs without a full Cartesian product
# (3 layer heights x 3 infills x 2 perimeters = 18 combinations; we use 8).
#
# Orientation and supports are deliberately NOT varied yet: orientation's
# effect hasn't been verified against a real binary beyond "the flag exists"
# (see app/slicer/prusaslicer.py), and support material's effect on output
# metrics has never been observed against real PrusaSlicer output either —
# both are candidates for a future milestone once verified the same way
# --filament-density was. Varying them now would risk an unverified variable
# silently skewing the comparison.
_CANDIDATE_SPECS: tuple[tuple[float, int, int], ...] = (
    (0.15, 10, 2),  # fine layers, light infill, minimal walls: material-lean, slower
    (0.15, 20, 3),  # fine layers, moderate infill/walls
    (0.20, 10, 2),  # baseline layer height, light infill: fast + material-lean
    (0.20, 20, 2),  # the original single-candidate default, for continuity
    (0.20, 30, 3),  # baseline layer height, heavier infill/walls: more material
    (0.25, 10, 2),  # coarse layers, light infill: fastest, low material
    (0.25, 20, 2),  # coarse layers, moderate infill
    (0.25, 30, 3),  # coarse layers, heavy infill/walls: fastest path to more material
)


def generate_candidate_set(run_id: str) -> list[CandidateConfiguration]:
    """Build the fixed, deterministic set of candidates evaluated per run.

    This is the seam `AgentPlanner.propose_candidates` (app/agent/interfaces.py)
    will eventually replace with an adaptive, previous-result-informed search.
    Until then, Strata always tries the same `_CANDIDATE_SPECS`, in the same
    order, with supports off and no rotation — no randomness, no LLM calls.
    """
    return [
        CandidateConfiguration(
            run_id=run_id,
            orientation_x=0.0,
            orientation_y=0.0,
            orientation_z=0.0,
            layer_height=layer_height,
            infill_percent=infill_percent,
            supports_enabled=DEFAULT_SUPPORTS_ENABLED,
            perimeter_count=perimeter_count,
        )
        for layer_height, infill_percent, perimeter_count in _CANDIDATE_SPECS
    ]


__all__ = ["build_default_candidate", "generate_candidate_set"]
