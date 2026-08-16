"""Slicer integration layer.

`SlicerService` is the interface the rest of the app depends on.
`PrusaSlicerService` is the (skeleton) real implementation that shells out to
the PrusaSlicer CLI. PrusaSlicer, not Gemini, is the source of truth for
print time and filament usage — see docs/architecture.md.
"""
