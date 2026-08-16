"""Result type returned by any SlicerService implementation."""

from __future__ import annotations

from pydantic import BaseModel, Field


class SliceResult(BaseModel):
    success: bool
    print_time_seconds: int | None = None
    filament_grams: float | None = None
    gcode_path: str | None = None
    warnings: list[str] = Field(default_factory=list)
    error: str | None = None
