from __future__ import annotations

from pathlib import Path

import pytest

from app.services.storage import LocalStorageService, StorageError


def test_save_and_retrieve_stl(tmp_path: Path) -> None:
    service = LocalStorageService(tmp_path)
    reference = service.save_stl("run-1", "part.stl", b"solid part\nendsolid part\n")

    assert service.exists(reference)
    resolved = service.get_artifact_path(reference)
    assert resolved.read_bytes() == b"solid part\nendsolid part\n"


def test_save_and_retrieve_gcode(tmp_path: Path) -> None:
    service = LocalStorageService(tmp_path)
    reference = service.save_gcode("run-1", "candidate-1", b"G28\nG1 X0 Y0\n")

    resolved = service.get_artifact_path(reference)
    assert resolved.read_bytes() == b"G28\nG1 X0 Y0\n"


def test_get_artifact_path_rejects_traversal_outside_root(tmp_path: Path) -> None:
    service = LocalStorageService(tmp_path)
    with pytest.raises(StorageError):
        service.get_artifact_path("../outside.stl")


def test_get_artifact_path_missing_reference_raises(tmp_path: Path) -> None:
    service = LocalStorageService(tmp_path)
    with pytest.raises(StorageError):
        service.get_artifact_path("runs/does-not-exist/uploads/part.stl")
