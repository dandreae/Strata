"""The mandatory validation boundary between untrusted planner output and
real `CandidateConfiguration` objects that reach PrusaSlicer.

    Planner output (any planner, including Gemini)
        ↓
    Typed schema (app.agent.planner_schema.CandidateProposal)
        ↓
    THIS MODULE: bounds, finiteness, duplicates, count cap
        ↓
    CandidateConfiguration
        ↓
    PrusaSlicer command builder (app.slicer.prusaslicer)

Every proposal is treated as untrusted input, planner-agnostic — this
module doesn't know or care whether a proposal came from Gemini or a
deterministic generator. Nothing here ever reaches a shell, a subprocess,
a file path, or a G-code file: only three bounded numeric fields ever flow
through, into a `CandidateConfiguration` whose other fields (orientation,
supports) are fixed by this module, never by the proposal.

Out-of-bounds values are REJECTED, not clamped — a proposal for
layer_height=5 doesn't become layer_height=0.30; it's dropped, with a
logged reason, so the audit trail always shows what a planner actually
asked for and why it didn't fly.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.agent.planner_schema import CandidateProposal
from app.models.candidate import CandidateConfiguration

LAYER_HEIGHT_MIN_MM = 0.10
LAYER_HEIGHT_MAX_MM = 0.30
INFILL_MIN_PERCENT = 5
INFILL_MAX_PERCENT = 40
PERIMETER_MIN = 2
PERIMETER_MAX = 4

# Hard ceiling regardless of what a planner requests or proposes — a
# planner cannot cause an unbounded number of real (paid-in-time,
# paid-in-money-if-Gemini) slicing jobs.
MAX_CANDIDATES_PER_ROUND = 8


@dataclass(frozen=True)
class ValidationOutcome:
    accepted: list[CandidateConfiguration]
    rejected: list[str] = field(default_factory=list)


def validate_and_normalize_proposals(
    run_id: str,
    proposals: list[CandidateProposal],
    requested_count: int,
) -> ValidationOutcome:
    """Validate and normalize raw proposals into real `CandidateConfiguration`s.

    `requested_count` caps how many are accepted (further clamped to
    `MAX_CANDIDATES_PER_ROUND`); excess valid proposals are rejected, not
    silently truncated without a trace.
    """
    accepted: list[CandidateConfiguration] = []
    rejected: list[str] = []
    seen: set[tuple[float, int, int]] = set()

    count_cap = max(1, min(requested_count, MAX_CANDIDATES_PER_ROUND))

    for i, proposal in enumerate(proposals):
        label = f"proposal #{i + 1}"
        outcome = _validate_one(proposal)

        if isinstance(outcome, str):
            rejected.append(f"{label}: {outcome}")
            continue

        layer_height, infill_percent, perimeter_count = outcome
        key = (layer_height, infill_percent, perimeter_count)

        if key in seen:
            rejected.append(
                f"{label}: duplicate of an already-accepted candidate "
                f"(layer {layer_height}mm / infill {infill_percent}% / {perimeter_count} perimeters)."
            )
            continue

        if len(accepted) >= count_cap:
            rejected.append(f"{label}: exceeds the allowed candidate count for this round ({count_cap}).")
            continue

        seen.add(key)
        accepted.append(
            CandidateConfiguration(
                run_id=run_id,
                orientation_x=0.0,
                orientation_y=0.0,
                orientation_z=0.0,
                layer_height=layer_height,
                infill_percent=infill_percent,
                supports_enabled=False,
                perimeter_count=perimeter_count,
            )
        )

    return ValidationOutcome(accepted=accepted, rejected=rejected)


def _validate_one(proposal: CandidateProposal) -> tuple[float, int, int] | str:
    """Returns the normalized (layer_height, infill_percent, perimeter_count)
    tuple, or a human-readable rejection reason string."""
    layer_height = proposal.layer_height
    infill_percent = proposal.infill_percent
    perimeter_count = proposal.perimeter_count

    # Pydantic's `float` type accepts NaN/Infinity by default — reject them
    # explicitly; a schema-valid type is not the same as a sane value.
    # (perimeter_count is typed as `int`, which can never be NaN/Infinity.)
    if not math.isfinite(layer_height):
        return f"layer_height is not a finite number ({layer_height!r})."
    if not math.isfinite(infill_percent):
        return f"infill_percent is not a finite number ({infill_percent!r})."

    if not (LAYER_HEIGHT_MIN_MM <= layer_height <= LAYER_HEIGHT_MAX_MM):
        return f"layer_height {layer_height} outside allowed range [{LAYER_HEIGHT_MIN_MM}, {LAYER_HEIGHT_MAX_MM}]mm."
    if not (INFILL_MIN_PERCENT <= infill_percent <= INFILL_MAX_PERCENT):
        return f"infill_percent {infill_percent} outside allowed range [{INFILL_MIN_PERCENT}, {INFILL_MAX_PERCENT}]%."
    if not (PERIMETER_MIN <= perimeter_count <= PERIMETER_MAX):
        return f"perimeter_count {perimeter_count} outside allowed range [{PERIMETER_MIN}, {PERIMETER_MAX}]."

    # Normalize: CandidateConfiguration requires an int infill_percent and
    # PrusaSlicer only meaningfully resolves layer height to ~0.01mm.
    return round(float(layer_height), 2), round(infill_percent), int(perimeter_count)


__all__ = ["ValidationOutcome", "validate_and_normalize_proposals", "MAX_CANDIDATES_PER_ROUND"]
