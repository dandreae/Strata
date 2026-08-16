"""StorageService: abstracts where uploaded STLs and generated G-code live.

`LocalStorageService` is a filesystem-backed implementation for local
development. A future `GcsStorageService` should implement the same
interface backed by a Cloud Storage bucket (see `Settings.gcs_bucket_name`
in app/core/config.py) so business logic never has to know which backend is
in use.
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from pathlib import Path


class StorageError(Exception):
    """Raised when an artifact cannot be saved or retrieved."""


class StorageService(ABC):
    """Abstract artifact storage: uploaded STLs and generated G-code."""

    @abstractmethod
    def save_stl(self, run_id: str, filename: str, content: bytes) -> str:
        """Persist an uploaded STL and return an opaque storage reference."""

    @abstractmethod
    def save_gcode(self, run_id: str, candidate_id: str, content: bytes) -> str:
        """Persist generated G-code and return an opaque storage reference."""

    @abstractmethod
    def get_artifact_path(self, reference: str) -> Path:
        """Resolve a storage reference to a local filesystem path.

        For cloud-backed implementations this may need to download the
        artifact to a temporary local path first (e.g. for PrusaSlicer,
        which needs a real file on disk).
        """

    @abstractmethod
    def exists(self, reference: str) -> bool:
        """Return whether a storage reference currently points at a real artifact."""


class LocalStorageService(StorageService):
    """Filesystem-backed StorageService for local development.

    Layout: `{base_dir}/runs/{run_id}/uploads/{filename}`
            `{base_dir}/runs/{run_id}/candidates/{candidate_id}.gcode`

    References returned are relative POSIX paths under `base_dir`; callers
    should treat them as opaque and always go through `get_artifact_path`.
    """

    def __init__(self, base_dir: Path) -> None:
        self._base_dir = base_dir
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def save_stl(self, run_id: str, filename: str, content: bytes) -> str:
        safe_name = Path(filename).name  # strip any path components
        if not safe_name:
            safe_name = f"{uuid.uuid4()}.stl"
        target_dir = self._base_dir / "runs" / run_id / "uploads"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / safe_name
        target_path.write_bytes(content)
        return str(target_path.relative_to(self._base_dir).as_posix())

    def save_gcode(self, run_id: str, candidate_id: str, content: bytes) -> str:
        target_dir = self._base_dir / "runs" / run_id / "candidates"
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"{candidate_id}.gcode"
        target_path.write_bytes(content)
        return str(target_path.relative_to(self._base_dir).as_posix())

    def get_artifact_path(self, reference: str) -> Path:
        path = (self._base_dir / reference).resolve()
        if self._base_dir.resolve() not in path.parents and path != self._base_dir.resolve():
            raise StorageError(f"Reference resolves outside storage root: {reference}")
        if not path.exists():
            raise StorageError(f"No artifact found for reference: {reference}")
        return path

    def exists(self, reference: str) -> bool:
        return (self._base_dir / reference).exists()


__all__ = ["StorageService", "LocalStorageService", "StorageError"]
