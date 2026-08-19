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
    """The full structured response a planner must produce for the first round."""

    candidates: list[CandidateProposal]
    planning_summary: str = Field(
        description="One or two plain-language sentences describing the experiment "
        "strategy. Not chain-of-thought — a concise, audit-suitable summary."
    )


class RoundDecisionOutput(BaseModel):
    """The full structured response a planner must produce for round 2: a
    single call that both decides stop-vs-continue and (if continuing)
    proposes the next round — one call does both jobs, never two."""

    continue_optimization: bool = Field(description="True to propose new candidates; False to stop.")
    reasoning_summary: str = Field(
        description="One or two plain sentences explaining the decision. Not chain-of-thought."
    )
    # No default: always require Gemini to emit this field explicitly (as
    # `[]` when stopping) rather than relying on it being omitted — a real
    # run observed a truncated/malformed response for this schema (see
    # gemini_planner.py's module docstring); requiring every field is a
    # small, low-risk hardening in case an optional/defaulted field was a
    # contributing factor, unconfirmed without spending another real call.
    candidates: list[CandidateProposal] = Field(
        description="New candidates, each different from every previously-tested "
        "configuration. Empty list when continue_optimization is false."
    )


__all__ = ["CandidateProposal", "PlannerOutput", "RoundDecisionOutput"]
