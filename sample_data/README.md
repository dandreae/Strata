# sample_data

Small, real geometry files for manual testing and future fixtures — not
generated slicer output (Strata never fabricates slicer results, and
neither should this directory).

- `cube_20mm.stl` — a minimal valid ASCII STL cube (20mm per side), useful
  for exercising upload validation and, once wired up, an actual PrusaSlicer
  invocation end-to-end.

`output/` is gitignored and is where local manual test runs can write
generated G-code without polluting the repo.
