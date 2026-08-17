# sample_data

Small, real geometry files for manual testing and future fixtures — not
generated slicer output (Strata never fabricates slicer results, and
neither should this directory).

- `cube_20mm.stl` — a minimal valid ASCII STL cube (20mm per side), useful
  for exercising upload validation and, once wired up, an actual PrusaSlicer
  invocation end-to-end.

`output/` is gitignored and is where local manual test runs can write
generated G-code without polluting the repo.

## Known limitation

A 20mm cube is geometrically trivial — every wall/infill/layer-height
combination produces a real but not very *interesting* print-time/material
tradeoff (thin walls dominate a shape this small). It's sufficient to prove
the multi-candidate pipeline is real and correct (see
`tests/test_integration_real_prusaslicer.py` and the multi-candidate
optimization milestone in docs/architecture.md), but a more representative
bracket/enclosure-style STL — with real overhangs, wall-thickness
sensitivity, and infill-driven mass — would make the Pareto tradeoffs more
visually convincing for a demo. None was added this pass (no random
internet downloads, to keep provenance clean); add one deliberately chosen
for the hackathon demo before that milestone.
