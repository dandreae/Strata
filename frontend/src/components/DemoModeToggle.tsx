import { FIXTURE_SCENARIOS } from "../lib/fixtures";

/**
 * Dev/demo-only control — switches between fixture data (no network calls,
 * no Gemini/Cloud Run cost) and the real backend. See lib/demoMode.ts and
 * lib/fixtures.ts. Never affects what the real backend does.
 *
 * In a production build (`import.meta.env.PROD` — e.g. a public Vercel
 * deployment), "Live backend" is locked out entirely: the checkbox is
 * disabled, so a visitor can never end up in a mode that tries to reach a
 * real backend that isn't there. Local dev (`npm run dev`) is unaffected —
 * the toggle stays fully interactive.
 */
export function DemoModeToggle({
  demoMode,
  onToggleDemoMode,
  scenarioKey,
  onScenarioChange,
  disabled,
}: {
  demoMode: boolean;
  onToggleDemoMode: (enabled: boolean) => void;
  scenarioKey: string;
  onScenarioChange: (key: string) => void;
  disabled: boolean;
}) {
  const liveBackendLocked = import.meta.env.PROD;

  return (
    <div className="demo-toggle">
      <label className="demo-toggle-switch">
        <input
          type="checkbox"
          checked={demoMode}
          disabled={disabled || liveBackendLocked}
          title={liveBackendLocked ? "Live backend mode is unavailable in this public demo." : undefined}
          onChange={(e) => onToggleDemoMode(e.target.checked)}
        />
        <span>{demoMode ? "Recorded run replay" : "Live backend"}</span>
      </label>

      {demoMode && (
        <select
          className="demo-scenario-select"
          value={scenarioKey}
          disabled={disabled}
          onChange={(e) => onScenarioChange(e.target.value)}
        >
          {FIXTURE_SCENARIOS.map((s) => (
            <option key={s.key} value={s.key}>
              {s.isReal ? "● " : "○ "}
              {s.label}
            </option>
          ))}
        </select>
      )}
    </div>
  );
}
