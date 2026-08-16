"""PrusaSlicerService: shells out to the real PrusaSlicer CLI.

STATUS: implemented and verified against a real installed binary
(PrusaSlicer-2.9.6-console on Windows, 2026-08-16) — `--help`/`--help-fff`
matched every flag used below exactly, and a real slice of
`sample_data/cube_20mm.stl` succeeded end to end
(`tests/test_integration_real_prusaslicer.py`). Command construction and
G-code parsing were originally grounded in PrusaSlicer's own C++ source
(master branch) rather than guessed, then corrected against real output
where the source and the live binary disagreed (see the `--filament-density`
note below):

  - `src/CLI/Setup.cpp`            — CLI argument parsing (--key value / =,
                                      --no- prefix for booleans).
  - `src/libslic3r/PrintConfig.cpp` — confirms `layer_height` (coFloat),
                                      `fill_density` (coPercent), `perimeters`
                                      (coInt), `support_material` (coBool,
                                      default false) as real config keys, and
                                      `rotate`/`rotate_x`/`rotate_y` as real
                                      CLI transform options.
  - `src/CLI/ProcessTransform.cpp` — rotation is applied in a FIXED order
                                      (Z via `rotate`, then X, then Y)
                                      regardless of argv order. Not
                                      commutative for compound rotations.
  - `src/CLI/LoadPrintData.cpp`    — `finalize_print_config()` merges CLI
                                      overrides onto a fully-defaulted
                                      `FullPrintConfig` even when no `--load`
                                      profile is given, so slicing with only
                                      the flags below (no profile) is valid
                                      and uses PrusaSlicer's built-in
                                      defaults for everything else.
  - `src/libslic3r/Print.cpp`      — confirms the exact literal G-code
                                      comment `"; filament used [g] ="`.
  - `src/libslic3r/GCode/GCodeProcessor.cpp` — confirms the exact sprintf
                                      format `"; estimated printing time (%s
                                      mode) = %s\\n"`.

Two real bugs this caught, one from source review and one only visible by
actually running the binary:

  1. `--fill-density` MUST be given with a `%` suffix (e.g. `20%`) — caught
     by reading `PrintConfigDef::handle_legacy` in PrintConfig.cpp before
     ever running the binary. A bare `20` is silently reinterpreted as an
     old-style 0..1 fraction and multiplied by 100 ("20%" becomes "2000%").
  2. Without a filament profile, `filament_density` defaults to `0`, so
     PrusaSlicer *correctly* reports `; total filament used [g] = 0.00` no
     matter what the geometry is — a real zero, not a parsing bug. This was
     NOT visible from source review; it only showed up by actually slicing
     `cube_20mm.stl` and reading the output G-code. Fixed by passing
     `--filament-density 1.24` (standard PLA, matching PrusaSlicer's own
     bundled generic PLA profile) unconditionally — see `build_command()`.

Not yet resolved (documented as limitations, not guessed): printer/material
*profile* selection (`--load <file.ini>` / `--printer-profile`) is not wired
up — there is no profile file lookup in this codebase yet, so `printer_profile`
on a candidate is currently informational only. This is fine for this
milestone because (per LoadPrintData.cpp above) PrusaSlicer slices correctly
with built-in defaults in the profile's absence.
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

# Standard PLA density, matching PrusaSlicer's own bundled generic PLA
# profile. Without ANY filament density, PrusaSlicer correctly reports 0g
# (0 volume * cm3 is meaningless without a density) — confirmed live against
# a real PrusaSlicer-2.9.6 binary on 2026-08-16. Not a candidate/search
# variable; see build_command()'s docstring.
PLA_FILAMENT_DENSITY_G_PER_CM3 = 1.24


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

        Every flag here is confirmed against PrusaSlicer's CLI source (see
        module docstring) — none are guessed:
          - `--export-gcode` (aliases `--gcode`, `-g`): action flag, defined
            in `CLIActionsConfigDef` (PrintConfig.cpp) as `export_gcode`.
          - `--layer-height <mm>`: config key `layer_height` (coFloat).
          - `--fill-density <percent>%`: config key `fill_density` (coPercent)
            — MUST include the `%` sign, see module docstring.
          - `--perimeters <n>`: config key `perimeters` (coInt).
          - `--support-material`: config key `support_material` (coBool,
            default false) — presence alone sets true; PrusaSlicer's `--no-`
            prefix convention would set it false explicitly, but we simply
            omit the flag when disabled since false is already the default.
          - `--rotate-x/--rotate-y/--rotate <deg>`: CLI transform options
            confirmed in `CLITransformConfigDef` (PrintConfig.cpp). NOTE:
            `ProcessTransform.cpp` applies these in a fixed order — Z
            (`--rotate`) first, then X, then Y — regardless of argv order,
            because it checks `has("rotate")`, then `has("rotate_x")`, then
            `has("rotate_y")` sequentially. Rotation is not commutative, so
            for compound rotations the *effective* order is always Z, X, Y.
          - `--output <path>`: config key `output`, confirmed in
            `CLIMiscConfigDef`.
          - `--filament-density <g/cm3>`: NOT a candidate variable — a fixed
            baseline needed for PrusaSlicer to report grams at all. Verified
            live against PrusaSlicer 2.9.6 on 2026-08-16: with no filament
            profile loaded, `filament_density` defaults to `0`, so PrusaSlicer
            *correctly* computes `; total filament used [g] = 0.00` — a real
            zero, not a parsing bug (confirmed by diffing G-code output with
            and without this flag; `; filament used [cm3]` was correctly
            non-zero in both runs). Strata's scope is PLA (see project
            README), so a standard PLA density of 1.24 g/cm3 is applied
            unconditionally, matching the value PrusaSlicer's own bundled
            generic PLA profile uses. This is a documented assumption, not a
            per-candidate search variable — it stays out of
            `CandidateConfiguration` on purpose (material choice is out of
            MVP scope, same as printer/material profile loading below).

        Printer/material profile selection (`--load` / `--printer-profile`)
        is intentionally NOT included: no profile file lookup exists in this
        codebase yet. `printer_profile` is accepted for future use and
        currently only affects nothing (PrusaSlicer slices against its
        built-in defaults for anything not set above — confirmed valid by
        `LoadPrintData.cpp::finalize_print_config`, see module docstring).
        """
        output_path = output_dir / f"{candidate_configuration.id}.gcode"

        argv = [
            binary_path,
            "--export-gcode",
            "--layer-height",
            str(candidate_configuration.layer_height),
            "--fill-density",
            f"{candidate_configuration.infill_percent}%",
            "--perimeters",
            str(candidate_configuration.perimeter_count),
            "--filament-density",
            str(PLA_FILAMENT_DENSITY_G_PER_CM3),
        ]

        if candidate_configuration.supports_enabled:
            argv.append("--support-material")

        if candidate_configuration.orientation_x:
            argv += ["--rotate-x", str(candidate_configuration.orientation_x)]
        if candidate_configuration.orientation_y:
            argv += ["--rotate-y", str(candidate_configuration.orientation_y)]
        if candidate_configuration.orientation_z:
            argv += ["--rotate", str(candidate_configuration.orientation_z)]

        # Not yet wired up — see docstring. Accepted now so the signature
        # doesn't need to change again once profile loading is added.
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

        Format confirmed in `src/libslic3r/GCode/GCodeProcessor.cpp`:
        `sprintf(buf, "; estimated printing time (%s mode) = %s\\n", ...)`,
        e.g. `; estimated printing time (normal mode) = 2h 3m 45s`. Silent
        mode (if enabled) and a separate "estimated *first layer* printing
        time" line may also be present; this regex's literal prefix
        "estimated printing time" does not match the first-layer variant
        ("estimated first layer printing time"), and normal mode is always
        emitted before silent mode, so `re.search` (leftmost match) reliably
        picks the total normal-mode time.

        Confirmed against a real PrusaSlicer-2.9.6 binary on 2026-08-16
        (e.g. real output `; estimated printing time (normal mode) = 17m 8s`
        — units omitted when zero, matching the format assumed here).
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

        Literal format confirmed in `src/libslic3r/Print.cpp`
        (`PrintStatistics::FilamentUsedGMask`/`TotalFilamentUsedGMask`) and
        against real PrusaSlicer-2.9.6 output on 2026-08-16, e.g.
        `; total filament used [g] = 3.95`. This regex is unanchored, so it
        matches either that line or a bare (non-"total") `; filament used
        [g] = ...` line, whichever is present — real output was observed to
        include only the "total" line for a single-extruder slice.

        Real-world gotcha this surfaced (not visible from source alone): a
        correctly-parsed `0.00` here does not necessarily mean parsing
        failed — PrusaSlicer's built-in default `filament_density` is `0`
        without a loaded filament profile, so grams is genuinely computed as
        zero. `build_command()` now always passes `--filament-density` to
        avoid this; see its docstring.
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
        # afterward — see app/services/orchestrator.py.
        return SliceResult(
            success=True,
            print_time_seconds=print_time,
            filament_grams=filament_grams,
            gcode_path=str(gcode_files[0]),
            warnings=warnings,
        )


class SlicerTimeoutError(Exception):
    """Raised when the PrusaSlicer subprocess exceeds its configured timeout."""


__all__ = [
    "PrusaSlicerService",
    "PrusaSlicerCommand",
    "SlicerTimeoutError",
    "PLA_FILAMENT_DENSITY_G_PER_CM3",
]
