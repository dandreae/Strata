"""The untrusted shape a planner's structured output must conform to.

This is deliberately separate from `CandidateConfiguration` (the trusted
domain model that reaches PrusaSlicer). A `CandidateProposal` is a raw,
unvalidated hypothesis — only `app.agent.planner_validation` may turn one
into a real `CandidateConfiguration`, and only after bounds/finite/
duplicate/count checks. No orientation, no supports, no arbitrary slicer
flags: Gemini (or any future planner) may only propose the three domain
variables this milestone allows.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CandidateProposal(BaseModel):
    """One raw candidate hypothesis proposed by a planner. Untrusted until
    it passes `app.agent.planner_validation.validate_and_normalize_proposals`.
    """

    layer_height: float = Field(description="Proposed layer height in millimeters.")
    infill_percent: float = Field(description="Proposed infill density, percent.")
    perimeter_count: int = Field(description="Proposed number of perimeter/wall loops.")


class PlannerOutput(BaseModel):
    """The full structured response a planner must produce for one round."""

    candidates: list[CandidateProposal]
    planning_summary: str = Field(
        description="One or two plain-language sentences describing the experiment "
        "strategy. Not chain-of-thought — a concise, audit-suitable summary."
    )


__all__ = ["CandidateProposal", "PlannerOutput"]
