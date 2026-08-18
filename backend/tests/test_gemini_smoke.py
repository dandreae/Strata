"""Real, explicit Gemini + Google ADK smoke test.

Unlike every other planner test in this suite, this one makes a genuine,
billable call to the Gemini API — it is never run by default `pytest -q`
and auto-skips when no credentials are configured, so a green default run
never implies this executed. To run it for real:

    STRATA_GEMINI_API_KEY=<your key> pytest -m gemini_smoke -v -s

If PrusaSlicer is ALSO available (STRATA_PRUSASLICER_BINARY_PATH / PATH),
this additionally slices every validated candidate for real and reports
measured results — but never asserts exact values, since Gemini's
proposals are not deterministic across calls. What IS asserted: every
candidate obeys the declared bounds (already guaranteed by
planner_validation.py, checked here as an end-to-end sanity check) and no
manufacturing metric was ever invented by the planner.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.agent.gemini_planner import GeminiAgentPlanner
from app.agent.planner_validation import (
    INFILL_MAX_PERCENT,
    INFILL_MIN_PERCENT,
    LAYER_HEIGHT_MAX_MM,
    LAYER_HEIGHT_MIN_MM,
    PERIMETER_MAX,
    PERIMETER_MIN,
)
from app.core.config import get_settings
from app.models.run import HardConstraints, OptimizationObjective, OptimizationPreferences, OptimizationRun
from app.slicer.prusaslicer import PrusaSlicerService

SAMPLE_STL = Path(__file__).resolve().parents[2] / "sample_data" / "cube_20mm.stl"

pytestmark = pytest.mark.gemini_smoke


def _gemini_available() -> bool:
    return bool(get_settings().gemini_api_key)


def _prusaslicer_available() -> bool:
    settings = get_settings()
    binary_path = settings.prusaslicer_binary_path
    return Path(binary_path).is_file() or shutil.which(binary_path) is not None


@pytest.mark.skipif(not _gemini_available(), reason="No STRATA_GEMINI_API_KEY configured")
def test_gemini_proposes_real_candidates_for_the_cube_scenario() -> None:
    settings = get_settings()
    planner = GeminiAgentPlanner(api_key=settings.gemini_api_key, model=settings.gemini_model)

    run = OptimizationRun(
        filename="cube_20mm.stl",
        production_quantity=500,
        printer_profile="generic_pla",
        hard_constraints=HardConstraints(max_print_time_seconds=1800, max_filament_grams=10),
        optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.MINIMIZE_MATERIAL),
    )

    result = planner.plan_initial_candidates(run, candidate_count=8)

    print(f"\nplanner_name: {result.planner_name}")
    print(f"planning_summary: {result.planning_summary}")
    print(f"rejected_proposals: {result.rejected_proposals}")
    for i, c in enumerate(result.candidates, 1):
        print(f"  #{i}: layer={c.layer_height}mm infill={c.infill_percent}% perimeters={c.perimeter_count}")
        # Every candidate obeys the declared bounds — the real end-to-end
        # proof that the validation boundary actually constrains real
        # Gemini output, not just hand-built test fixtures.
        assert LAYER_HEIGHT_MIN_MM <= c.layer_height <= LAYER_HEIGHT_MAX_MM
        assert INFILL_MIN_PERCENT <= c.infill_percent <= INFILL_MAX_PERCENT
        assert PERIMETER_MIN <= c.perimeter_count <= PERIMETER_MAX
        assert c.supports_enabled is False
        assert c.orientation_x == 0.0 and c.orientation_y == 0.0 and c.orientation_z == 0.0
        # Gemini never supplies manufacturing metrics — only real slicing does.
        assert c.print_time_seconds is None
        assert c.filament_grams is None

    assert 1 <= len(result.candidates) <= 8
    assert result.planning_summary

    if not _prusaslicer_available():
        pytest.skip(
            "Gemini planning succeeded (see output above); skipping the real-slice "
            "half — no PrusaSlicer binary configured. See test_integration_real_prusaslicer.py."
        )

    print("\nSlicing each Gemini-proposed candidate through real PrusaSlicer:")
    slicer = PrusaSlicerService(
        binary_path=settings.prusaslicer_binary_path,
        timeout_seconds=settings.prusaslicer_timeout_seconds,
    )
    for i, c in enumerate(result.candidates, 1):
        slice_result = slicer.slice(SAMPLE_STL, run.printer_profile, c)
        status = "OK" if slice_result.success else f"FAILED ({slice_result.error})"
        print(
            f"  #{i}: layer={c.layer_height}mm infill={c.infill_percent}% perimeters={c.perimeter_count} "
            f"-> {status} time={slice_result.print_time_seconds}s grams={slice_result.filament_grams}g"
        )
        if slice_result.success:
            assert slice_result.print_time_seconds is not None and slice_result.print_time_seconds > 0
            assert slice_result.filament_grams is not None and slice_result.filament_grams > 0
