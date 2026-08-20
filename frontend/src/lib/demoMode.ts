/**
 * Demo mode: whether the UI is driven by fixture data (lib/fixtures.ts) or
 * the real backend (lib/api.ts). Purely a frontend-development/demo
 * convenience — never touches the backend, never affects it.
 *
 * Default: on in local dev (`import.meta.env.DEV`), off in a production
 * build (`npm run build`), so a deployed/shared build defaults to hitting
 * the real backend. Either way it's a runtime toggle (persisted in
 * localStorage) so it can be flipped without a rebuild — e.g. to switch to
 * the real Cloud Run backend right before recording the final demo.
 */

const STORAGE_KEY = "strata:demo-mode";

export function getInitialDemoMode(): boolean {
  const stored = localStorage.getItem(STORAGE_KEY);
  if (stored === "true") return true;
  if (stored === "false") return false;
  return import.meta.env.DEV;
}

export function setDemoMode(enabled: boolean): void {
  localStorage.setItem(STORAGE_KEY, String(enabled));
}
