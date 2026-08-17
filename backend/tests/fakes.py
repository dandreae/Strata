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
    """Returns pre-programmed SliceResult(s) (or raises), never touches a subprocess.

    Pass `result` for a single fixed result applied to every call (single-
    candidate tests), or `results` for a sequence consumed in call order
    (multi-candidate tests where each candidate should get a different
    real-looking result). If more calls happen than `results` provides, the
    last result repeats.
    """

    def __init__(
        self,
        result: SliceResult | None = None,
        results: list[SliceResult] | None = None,
        raise_unavailable: bool = False,
    ) -> None:
        self._result = result
        self._results = list(results) if results is not None else None
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
        if self._results is not None:
            index = min(len(self.calls) - 1, len(self._results) - 1)
            return self._results[index]
        assert self._result is not None
        return self._result
