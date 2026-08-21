# Static model assets

`enclosure_tray.stl` and `cube_20mm.stl` are byte-for-byte copies of the real
files in `../../../sample_data/` — not regenerated, not fabricated. They
exist here only because Vite's `public/` directory is the one place the
frontend (an independently deployable static build) can actually serve a
static binary asset from, in both dev and production. `sample_data/` is
outside the frontend project root and isn't reachable at runtime once this
is deployed on its own.

If `sample_data/enclosure_tray.stl` or `sample_data/cube_20mm.stl` ever
changes, re-copy it here — see `frontend/src/lib/fixtureModels.ts` for where
these are referenced.
