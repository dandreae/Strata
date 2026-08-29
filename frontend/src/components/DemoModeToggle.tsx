import { FIXTURE_SCENARIOS } from "../lib/fixtures";

/**
 * Dev/demo-only control — switches between fixture data (no network calls,
 * no Gemini/Cloud Run cost) and the real backend. See lib/demoMode.ts and
 * lib/fixtures.ts. Never affects what the real backend does.
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
  return (
    <div className="demo-toggle">
      <label className="demo-toggle-switch">
        <input
          type="checkbox"
          checked={demoMode}
          disabled={disabled}
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
