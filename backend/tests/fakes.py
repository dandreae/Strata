"""Test doubles. Used only to unit-test orchestration without a real
PrusaSlicer binary — never used to fabricate what a real slice would report;
see test_slicer_prusaslicer.py and the (skipped-without-a-binary) real
integration test for that.
"""

from __future__ import annotations

from pathlib import Path

from app.models.candidate import CandidateConfiguration
from app.models.slicer import SliceResult
from app.slicer.base import SlicerService, SlicerUnavailableError


class FakeSlicerService(SlicerService):
    """Returns a pre-programmed SliceResult (or raises), never touches a subprocess."""

    def __init__(self, result: SliceResult | None = None, raise_unavailable: bool = False) -> None:
        self._result = result
        self._raise_unavailable = raise_unavailable
        self.calls: list[tuple[Path, str, CandidateConfiguration]] = []

    def slice(
        self,
        stl_path: Path,
        printer_profile: str,
        candidate_configuration: CandidateConfiguration,
    ) -> SliceResult:
        self.calls.append((stl_path, printer_profile, candidate_configuration))
        if self._raise_unavailable:
            raise SlicerUnavailableError("fake: PrusaSlicer binary not found")
        assert self._result is not None
        return self._result
