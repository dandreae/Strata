"""Real integration test against an actual PrusaSlicer binary.

Unlike every other test in this suite, this one does NOT mock the
subprocess — it shells out to a real `prusa-slicer` and slices the real
`sample_data/cube_20mm.stl` fixture. It is automatically skipped when no
PrusaSlicer binary can be found (the case in this project's current
development environment — see docs/architecture.md), so a green test run
never implies this test actually executed.

To run it for real: install PrusaSlicer, ensure it's on PATH (or set
STRATA_PRUSASLICER_BINARY_PATH to its full path), then run
`pytest -m integration -q`.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.core.config import get_settings
from app.models.candidate import CandidateConfiguration
from app.slicer.prusaslicer import PrusaSlicerService

SAMPLE_STL = Path(__file__).resolve().parents[2] / "sample_data" / "cube_20mm.stl"


def _binary_available() -> bool:
    binary_path = get_settings().prusaslicer_binary_path
    return Path(binary_path).is_file() or shutil.which(binary_path) is not None


pytestmark = pytest.mark.integration


@pytest.mark.skipif(not _binary_available(), reason="No PrusaSlicer binary found on PATH / STRATA_PRUSASLICER_BINARY_PATH")
def test_real_slice_of_sample_cube_produces_real_metrics() -> None:
    assert SAMPLE_STL.exists(), f"Missing fixture: {SAMPLE_STL}"

    settings = get_settings()
    service = PrusaSlicerService(
        binary_path=settings.prusaslicer_binary_path,
        timeout_seconds=settings.prusaslicer_timeout_seconds,
    )
    candidate = CandidateConfiguration(
        run_id="integration-test", layer_height=0.2, infill_percent=20, perimeter_count=2
    )

    result = service.slice(SAMPLE_STL, "generic_pla", candidate)

    assert result.success is True, f"Real slice failed: {result.error}"
    assert result.print_time_seconds is not None and result.print_time_seconds > 0
    assert result.filament_grams is not None and result.filament_grams > 0
