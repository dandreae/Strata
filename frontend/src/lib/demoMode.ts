/**
 * Demo mode: whether the UI is driven by fixture data (lib/fixtures.ts) or
 * the real backend (lib/api.ts). Purely a frontend-development/demo
 * convenience — never touches the backend, never affects it.
 *
 * Default: always demo/replay mode (`true`) for a fresh visitor, in both
 * development and production builds — a publicly-hosted build (e.g. on
 * Vercel) must never default to attempting a real backend request. It's
 * still a runtime toggle (persisted in localStorage) so a saved preference
 * is respected once set; see components/DemoModeToggle.tsx for where the
 * "Live backend" option itself is additionally locked out of production
 * builds entirely.
 */

const STORAGE_KEY = "strata:demo-mode";

export function getInitialDemoMode(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "true") return true;
  if (stored === "false") return false;
  return true;
}

export function setDemoMode(enabled: boolean): void {
  localStorage.setItem(STORAGE_KEY, String(enabled));
}
