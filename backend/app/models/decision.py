"""DecisionRecord: one entry in a run's visible decision ledger.

This is a concise audit record of a meaningful decision the agent (or the
deterministic optimizer) made — not a chain-of-thought log. Every field
should be short enough to render directly in a UI timeline.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from pydantic import BaseModel, Field


class DecisionRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid4()))
    run_id: str
    observation: str = Field(description="What the agent noticed, in plain language.")
    alternatives: list[str] = Field(default_factory=list, description="Options that were considered.")
    evidence: list[str] = Field(default_factory=list, description="Concrete data points backing the decision.")
    selected_action: str = Field(description="What was decided/done.")
    confidence: float | None = Field(default=None, ge=0, le=1)
    outcome: str | None = Field(default=None, description="Result of the action, filled in once known.")
    requires_human: bool = False
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
