from __future__ import annotations

from pathlib import Path

import pytest

from app.models.candidate import CandidateConfiguration
from app.slicer.base import SlicerUnavailableError
from app.slicer.prusaslicer import PrusaSlicerService


def test_slice_raises_when_binary_missing(tmp_path: Path) -> None:
    service = PrusaSlicerService(binary_path="definitely-not-a-real-binary-xyz")
    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    candidate = CandidateConfiguration(
        run_id="run-1", layer_height=0.2, infill_percent=20, perimeter_count=3
    )

    with pytest.raises(SlicerUnavailableError):
        service.slice(stl_path, "generic_pla", candidate)


def test_build_command_includes_mvp_variables(tmp_path: Path) -> None:
    service = PrusaSlicerService()
    candidate = CandidateConfiguration(
        run_id="run-1",
        layer_height=0.28,
        infill_percent=15,
        perimeter_count=4,
        supports_enabled=True,
        orientation_z=90,
    )

    command = service.build_command(
        stl_path=tmp_path / "part.stl",
        printer_profile="generic_pla",
        candidate_configuration=candidate,
        output_dir=tmp_path,
        binary_path="prusa-slicer",
    )

    assert "--layer-height" in command.argv
    assert "0.28" in command.argv
    assert "--fill-density" in command.argv
    assert "15" in command.argv
    assert "--perimeters" in command.argv
    assert "4" in command.argv
    assert "--support-material" in command.argv
    assert "--rotate" in command.argv


def test_parse_print_time_seconds_from_typical_header() -> None:
    gcode = "; estimated printing time (normal mode) = 2h 25m 12s\n"
    assert PrusaSlicerService.parse_print_time_seconds(gcode) == 2 * 3600 + 25 * 60 + 12


def test_parse_filament_grams_from_typical_header() -> None:
    gcode = "; filament used [g] = 61.43\n"
    assert PrusaSlicerService.parse_filament_grams(gcode) == pytest.approx(61.43)


def test_parse_functions_return_none_when_absent() -> None:
    gcode = "; no relevant metadata here\n"
    assert PrusaSlicerService.parse_print_time_seconds(gcode) is None
    assert PrusaSlicerService.parse_filament_grams(gcode) is None
