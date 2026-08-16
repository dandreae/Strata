"""PrusaSlicerService: shells out to the real PrusaSlicer CLI.

STATUS: skeleton. Command construction and G-code parsing below are based on
commonly-documented PrusaSlicer/Slic3r CLI conventions but have **not** been
verified against a specific installed PrusaSlicer version on this machine
(PrusaSlicer is not installed in this environment). Every flag/parsing
assumption that needs verification is marked with `# TODO(verify):`.

Do not wire this into a live optimization loop until those TODOs are
resolved against `prusa-slicer --help` / `--help-fff` output from the actual
binary that will run in production.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from app.core.logging import get_logger
from app.models.candidate import CandidateConfiguration
from app.models.slicer import SliceResult
from app.slicer.base import SlicerService, SlicerUnavailableError

logger = get_logger(__name__)


@dataclass(frozen=True)
class PrusaSlicerCommand:
    """A fully-built CLI invocation, kept separate from execution so it can
    be unit-tested (assert on argv) without ever spawning a process."""

    argv: list[str]
    output_dir: Path


class PrusaSlicerService(SlicerService):
    def __init__(self, binary_path: str = "prusa-slicer", timeout_seconds: int = 300) -> None:
        self._binary_path = binary_path
        self._timeout_seconds = timeout_seconds

    # --- availability -----------------------------------------------------

    def _resolve_binary(self) -> str:
        """Return an executable path for the configured binary, or raise.

        Accepts either a bare command name (resolved via PATH) or an
        explicit path to the executable.
        """
        candidate = Path(self._binary_path)
        if candidate.is_file():
            return str(candidate)

        resolved = shutil.which(self._binary_path)
        if resolved:
            return resolved

        raise SlicerUnavailableError(
            f"PrusaSlicer binary not found: '{self._binary_path}'. "
            "Install PrusaSlicer and/or set STRATA_PRUSASLICER_BINARY_PATH."
        )

    # --- command construction ----------------------------------------------

    def build_command(
        self,
        stl_path: Path,
        printer_profile: str,
        candidate_configuration: CandidateConfiguration,
        output_dir: Path,
        binary_path: str,
    ) -> PrusaSlicerCommand:
        """Build the CLI argv for slicing `stl_path` with `candidate_configuration`.

        Flags used here and their confidence level:
          - `-g` / `--export-gcode`     : documented, high confidence.
          - `--layer-height <mm>`        : documented, high confidence.
          - `--fill-density <percent>`   : documented, high confidence.
          - `--perimeters <n>`           : documented, high confidence.
          - `--support-material`         : documented (boolean flag), high confidence.
          - `--rotate-x/--rotate-y <deg>`, `--rotate <deg>` (Z)
            # TODO(verify): confirm exact rotation flag names/semantics
            # (combined multi-axis rotation may require a transform matrix
            # or `--rotate-x`/`--rotate-y` may not exist in all versions)
            # against the actual PrusaSlicer CLI help before relying on it.
          - `--output <path>`            : documented, high confidence.
          - printer/profile selection
            # TODO(verify): whether to pass `--load <config.ini>` for a
            # saved profile bundle, or individual `--printer-*` flags. This
            # skeleton assumes a pre-exported PrusaSlicer config `.ini`
            # named after `printer_profile` is available on disk; that
            # lookup is NOT implemented yet.
        """
        output_path = output_dir / f"{candidate_configuration.id}.gcode"

        argv = [
            binary_path,
            "--export-gcode",
            "--layer-height",
            str(candidate_configuration.layer_height),
            "--fill-density",
            str(candidate_configuration.infill_percent),
            "--perimeters",
            str(candidate_configuration.perimeter_count),
        ]

        if candidate_configuration.supports_enabled:
            argv.append("--support-material")

        # TODO(verify): rotation flag names/units against real CLI help.
        if candidate_configuration.orientation_x:
            argv += ["--rotate-x", str(candidate_configuration.orientation_x)]
        if candidate_configuration.orientation_y:
            argv += ["--rotate-y", str(candidate_configuration.orientation_y)]
        if candidate_configuration.orientation_z:
            argv += ["--rotate", str(candidate_configuration.orientation_z)]

        # TODO(verify): printer profile loading strategy (see docstring above).
        _ = printer_profile

        argv += ["--output", str(output_path), str(stl_path)]

        return PrusaSlicerCommand(argv=argv, output_dir=output_dir)

    # --- execution -----------------------------------------------------------

    def _run(self, command: PrusaSlicerCommand) -> subprocess.CompletedProcess[str]:
        """Run a built command in isolation. The only place subprocess is invoked."""
        try:
            return subprocess.run(
                command.argv,
                cwd=command.output_dir,
                capture_output=True,
                text=True,
                timeout=self._timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SlicerTimeoutError(
                f"PrusaSlicer did not complete within {self._timeout_seconds}s"
            ) from exc

    # --- parsing ---------------------------------------------------------

    @staticmethod
    def parse_print_time_seconds(gcode_text: str) -> int | None:
        """Extract estimated print time from PrusaSlicer's G-code header comment.

        # TODO(verify): PrusaSlicer typically emits a line similar to
        # `; estimated printing time (normal mode) = 2h 3m 45s` but the exact
        # wording/format can vary by version and print mode (normal/silent).
        # This regex should be validated against real slicer output.
        """
        match = re.search(
            r"estimated printing time.*?=\s*(?:(\d+)d\s*)?(?:(\d+)h\s*)?(?:(\d+)m\s*)?(?:(\d+)s)?",
            gcode_text,
            re.IGNORECASE,
        )
        if not match:
            return None
        days, hours, minutes, seconds = (int(g) if g else 0 for g in match.groups())
        total = days * 86400 + hours * 3600 + minutes * 60 + seconds
        return total or None

    @staticmethod
    def parse_filament_grams(gcode_text: str) -> float | None:
        """Extract filament usage in grams from PrusaSlicer's G-code header comment.

        # TODO(verify): PrusaSlicer typically emits
        # `; filament used [g] = 12.34` (grams) alongside a `[mm]`/`[cm3]`
        # variant. Confirm which are always present for the configured
        # printer profile before depending on this in the optimization loop.
        """
        match = re.search(r"filament used \[g\]\s*=\s*([\d.]+)", gcode_text, re.IGNORECASE)
        if not match:
            return None
        return float(match.group(1))

    # --- public API --------------------------------------------------------

    def slice(
        self,
        stl_path: Path,
        printer_profile: str,
        candidate_configuration: CandidateConfiguration,
    ) -> SliceResult:
        if not stl_path.exists():
            return SliceResult(success=False, error=f"STL not found: {stl_path}")

        binary_path = self._resolve_binary()  # raises SlicerUnavailableError

        # Deliberately NOT a `TemporaryDirectory` context manager: that would
        # delete the produced .gcode file on exit, before the returned
        # `gcode_path` could ever be used (e.g. persisted via StorageService).
        # The caller owns cleanup of this directory once it has copied out
        # whatever it needs.
        output_dir = Path(tempfile.mkdtemp(prefix="strata-slice-"))
        command = self.build_command(
            stl_path=stl_path,
            printer_profile=printer_profile,
            candidate_configuration=candidate_configuration,
            output_dir=output_dir,
            binary_path=binary_path,
        )

        logger.info("running prusaslicer", extra={"context": {"argv": command.argv}})
        try:
            result = self._run(command)
        except SlicerTimeoutError as exc:
            shutil.rmtree(output_dir, ignore_errors=True)
            return SliceResult(success=False, error=str(exc))

        if result.returncode != 0:
            shutil.rmtree(output_dir, ignore_errors=True)
            return SliceResult(
                success=False,
                error=result.stderr.strip() or f"prusa-slicer exited with code {result.returncode}",
                warnings=[result.stdout.strip()] if result.stdout.strip() else [],
            )

        gcode_files = list(output_dir.glob("*.gcode"))
        if not gcode_files:
            shutil.rmtree(output_dir, ignore_errors=True)
            return SliceResult(success=False, error="Slicer reported success but produced no G-code file.")

        gcode_text = gcode_files[0].read_text(errors="ignore")
        print_time = self.parse_print_time_seconds(gcode_text)
        filament_grams = self.parse_filament_grams(gcode_text)

        warnings = []
        if print_time is None:
            warnings.append("Could not parse print time from G-code output.")
        if filament_grams is None:
            warnings.append("Could not parse filament usage from G-code output.")

        # NOTE: gcode_path points into a working directory that persists
        # after this call returns. The caller is responsible for persisting
        # the artifact via StorageService and removing this directory
        # afterward (not yet wired up in this skeleton).
        return SliceResult(
            success=True,
            print_time_seconds=print_time,
            filament_grams=filament_grams,
            gcode_path=str(gcode_files[0]),
            warnings=warnings,
        )


class SlicerTimeoutError(Exception):
    """Raised when the PrusaSlicer subprocess exceeds its configured timeout."""


__all__ = ["PrusaSlicerService", "PrusaSlicerCommand", "SlicerTimeoutError"]
