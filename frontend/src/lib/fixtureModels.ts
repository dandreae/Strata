/**
 * Maps a fixture's real `filename` to its real, statically-served STL asset
 * (see frontend/public/models/README.md for why these are copied there).
 * Only fixtures with real, legitimate underlying geometry are listed —
 * synthetic fixtures (see lib/fixtures.ts) have no real STL behind their
 * placeholder filename, so they're deliberately absent here rather than
 * pointed at a fake model.
 */
const FIXTURE_MODEL_URLS: Record<string, string> = {
  "enclosure_tray.stl": "/models/enclosure_tray.stl",
  "cube_20mm.stl": "/models/cube_20mm.stl",
};

export function getFixtureModelUrl(filename: string): string | null {
  return FIXTURE_MODEL_URLS[filename] ?? null;
}
