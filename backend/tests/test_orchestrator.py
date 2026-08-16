from __future__ import annotations

from pathlib import Path

import pytest

from app.models.candidate import CandidateStatus
from app.models.run import HardConstraints, OptimizationObjective, OptimizationPreferences, OptimizationRun, RunStatus
from app.models.slicer import SliceResult
from app.services.orchestrator import execute_single_candidate_run
from app.services.repository import InMemoryRunRepository
from app.services.storage import LocalStorageService
from tests.fakes import FakeSlicerService


def _make_run(**overrides) -> OptimizationRun:
    defaults = dict(
        filename="part.stl",
        production_quantity=100,
        printer_profile="generic_pla",
        hard_constraints=HardConstraints(max_print_time_seconds=3 * 3600, max_filament_grams=80),
        optimization_preferences=OptimizationPreferences(objective=OptimizationObjective.BALANCED),
    )
    defaults.update(overrides)
    return OptimizationRun(**defaults)


def _fake_gcode_dir(tmp_path: Path, text: str) -> Path:
    gcode_dir = tmp_path / "fake-slice-output"
    gcode_dir.mkdir()
    (gcode_dir / "out.gcode").write_text(text)
    return gcode_dir / "out.gcode"


def test_successful_slice_within_constraints_accepts_candidate(tmp_path: Path) -> None:
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    run = _make_run()
    repository.create_run(run)

    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    gcode_path = _fake_gcode_dir(
        tmp_path,
        "; estimated printing time (normal mode) = 2h 25m 0s\n; filament used [g] = 61.43\n",
    )
    slicer = FakeSlicerService(
        result=SliceResult(success=True, print_time_seconds=8700, filament_grams=61.43, gcode_path=str(gcode_path))
    )

    result = execute_single_candidate_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)

    assert result.run.status == RunStatus.COMPLETED
    assert result.candidate.status == CandidateStatus.SUCCEEDED
    assert result.candidate.print_time_seconds == 8700
    assert result.candidate.filament_grams == 61.43
    assert result.candidate.slicer_output_path is not None
    assert result.decision.selected_action == "accept_candidate"
    assert result.decision.requires_human is False
    assert not gcode_path.parent.exists()  # cleaned up after persisting


def test_successful_slice_exceeding_constraints_rejects_candidate(tmp_path: Path) -> None:
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    run = _make_run(hard_constraints=HardConstraints(max_print_time_seconds=3600, max_filament_grams=10))
    repository.create_run(run)

    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    gcode_path = _fake_gcode_dir(
        tmp_path,
        "; estimated printing time (normal mode) = 2h 25m 0s\n; filament used [g] = 61.43\n",
    )
    slicer = FakeSlicerService(
        result=SliceResult(success=True, print_time_seconds=8700, filament_grams=61.43, gcode_path=str(gcode_path))
    )

    result = execute_single_candidate_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)

    assert result.run.status == RunStatus.COMPLETED
    assert result.candidate.status == CandidateStatus.SUCCEEDED
    assert result.decision.selected_action == "reject_candidate"
    assert "exceeds" in result.decision.outcome
    assert result.decision.requires_human is False


def test_slicer_unavailable_fails_run_without_crashing(tmp_path: Path) -> None:
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    run = _make_run()
    repository.create_run(run)

    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    slicer = FakeSlicerService(raise_unavailable=True)

    result = execute_single_candidate_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)

    assert result.run.status == RunStatus.FAILED
    assert result.candidate.status == CandidateStatus.FAILED
    assert result.decision.selected_action == "abort_run"
    assert "not found" in result.candidate.failure_reason


def test_slice_process_failure_rejects_candidate_without_crashing(tmp_path: Path) -> None:
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    run = _make_run()
    repository.create_run(run)

    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    slicer = FakeSlicerService(result=SliceResult(success=False, error="prusa-slicer exited with code 1"))

    result = execute_single_candidate_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)

    assert result.run.status == RunStatus.FAILED
    assert result.candidate.status == CandidateStatus.FAILED
    assert result.decision.selected_action == "reject_candidate"
    assert result.candidate.failure_reason == "prusa-slicer exited with code 1"


def test_missing_metrics_are_never_fabricated_and_fail_constraints(tmp_path: Path) -> None:
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    run = _make_run()
    repository.create_run(run)

    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    gcode_path = _fake_gcode_dir(tmp_path, "; no usable metadata in this gcode\n")
    slicer = FakeSlicerService(
        result=SliceResult(
            success=True,
            print_time_seconds=None,
            filament_grams=None,
            gcode_path=str(gcode_path),
            warnings=["Could not parse print time from G-code output.", "Could not parse filament usage from G-code output."],
        )
    )

    result = execute_single_candidate_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)

    assert result.candidate.print_time_seconds is None
    assert result.candidate.filament_grams is None
    assert result.decision.selected_action == "reject_candidate"
    assert any("Missing print_time_seconds" in e for e in result.decision.evidence)
    assert any("Missing filament_grams" in e for e in result.decision.evidence)


def test_run_and_candidate_are_persisted_to_repository(tmp_path: Path) -> None:
    repository = InMemoryRunRepository()
    storage = LocalStorageService(tmp_path / "storage")
    run = _make_run()
    repository.create_run(run)

    stl_path = tmp_path / "part.stl"
    stl_path.write_text("solid part\nendsolid part\n")

    gcode_path = _fake_gcode_dir(
        tmp_path, "; estimated printing time (normal mode) = 1h 0m 0s\n; filament used [g] = 10\n"
    )
    slicer = FakeSlicerService(
        result=SliceResult(success=True, print_time_seconds=3600, filament_grams=10.0, gcode_path=str(gcode_path))
    )

    execute_single_candidate_run(run, stl_path, repository=repository, storage=storage, slicer=slicer)

    stored_run = repository.get_run(run.id)
    assert stored_run.status == RunStatus.COMPLETED
    assert len(repository.list_candidates(run.id)) == 1
    assert len(repository.list_decisions(run.id)) == 1
