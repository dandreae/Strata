"""SlicerService interface and the error raised when no slicer is available."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from app.models.candidate import CandidateConfiguration
from app.models.slicer import SliceResult


class SlicerUnavailableError(Exception):
    """Raised when no working slicer binary/backend can be found.

    Callers must not treat this as "slicing failed" (a `SliceResult` with
    `success=False`); it means slicing could not even be attempted, which is
    a configuration/environment problem the caller should surface distinctly.
    """


class SlicerService(ABC):
    """Abstraction over "turn an STL + configuration into manufacturing estimates"."""

    @abstractmethod
    def slice(
        self,
        stl_path: Path,
        printer_profile: str,
        candidate_configuration: CandidateConfiguration,
    ) -> SliceResult:
        """Slice `stl_path` with the given candidate configuration.

        Must never fabricate results: if slicing cannot be attempted, raise
        `SlicerUnavailableError`; if it is attempted but fails, return a
        `SliceResult(success=False, error=...)`.
        """


__all__ = ["SlicerService", "SlicerUnavailableError"]
