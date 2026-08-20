import { useState } from "react";
import "./App.css";
import { AgentPipeline } from "./components/AgentPipeline";
import { DemoModeToggle } from "./components/DemoModeToggle";
import { RunResult } from "./components/RunResult";
import { ApiError, createRun, type RunDetail } from "./lib/api";
import { getInitialDemoMode, setDemoMode as persistDemoMode } from "./lib/demoMode";
import { DEFAULT_FIXTURE_KEY, getFixture } from "./lib/fixtures";
import { SetupForm, type SetupValues } from "./components/SetupForm";

// Printer profile is fixed for this milestone — no profile selection UI yet,
// and the backend doesn't load a profile file either (see
// docs/architecture.md); it's accepted for future use.
const PRINTER_PROFILE = "generic_pla";

// How long the fixture path waits before "arriving", purely so the agent
// pipeline visualization has something to show in demo mode too. Shorter
// than a real run so local iteration stays fast — switch to the live
// backend (see DemoModeToggle) to see real pipeline timing.
const FIXTURE_DELAY_MS = 6000;

type Phase =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; run: RunDetail; fixture: { isReal: boolean; label: string } | null }
  | { kind: "error"; message: string; details: string[] };

function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [demoMode, setDemoModeState] = useState(getInitialDemoMode);
  const [scenarioKey, setScenarioKey] = useState(DEFAULT_FIXTURE_KEY);

  const isBusy = phase.kind === "loading";

  function toggleDemoMode(enabled: boolean) {
    setDemoModeState(enabled);
    persistDemoMode(enabled);
  }

  async function handleSubmit(values: SetupValues) {
    setPhase({ kind: "loading" });

    if (demoMode) {
      const fixture = getFixture(scenarioKey);
      await delay(FIXTURE_DELAY_MS);
      setPhase({
        kind: "success",
        run: fixture.data,
        fixture: { isReal: fixture.isReal, label: fixture.label },
      });
      return;
    }

    try {
      const run = await createRun({
        file: values.file,
        productionQuantity: values.quantity,
        printerProfile: PRINTER_PROFILE,
        maxPrintTimeSeconds: Math.round(values.maxPrintMinutes * 60),
        maxFilamentGrams: values.maxMaterialGrams,
        objective: values.objective,
      });
      setPhase({ kind: "success", run, fixture: null });
    } catch (err) {
      if (err instanceof ApiError) {
        setPhase({ kind: "error", message: err.message, details: err.details });
      } else {
        setPhase({ kind: "error", message: "Unexpected error contacting the backend.", details: [] });
      }
    }
  }

  function reset() {
    setPhase({ kind: "idle" });
  }

  return (
    <main className="page">
      <header className="page-header">
        <div>
          <h1>Strata</h1>
          <p className="tagline">Autonomous manufacturing optimization</p>
        </div>
        <DemoModeToggle
          demoMode={demoMode}
          onToggleDemoMode={toggleDemoMode}
          scenarioKey={scenarioKey}
          onScenarioChange={setScenarioKey}
          disabled={isBusy}
        />
      </header>

      <ol className="flow-steps">
        {/* Upload + constraints share one screen (SetupForm), so both read
            "current" together while idle, then "done" from loading on. */}
        <li className={phase.kind === "idle" ? "flow-step-current" : "flow-step-done"}>Upload part</li>
        <li className={phase.kind === "idle" ? "flow-step-current" : "flow-step-done"}>Define constraints</li>
        <li className={phase.kind === "loading" ? "flow-step-current" : phase.kind === "success" || phase.kind === "error" ? "flow-step-done" : ""}>
          Watch agent work
        </li>
        <li className={phase.kind === "success" || phase.kind === "error" ? "flow-step-current" : ""}>
          Review recommendation
        </li>
      </ol>

      {phase.kind === "idle" && <SetupForm disabled={false} onSubmit={handleSubmit} />}

      {phase.kind === "loading" && <AgentPipeline />}

      {phase.kind === "error" && (
        <div className="status status-error">
          <p>{phase.message}</p>
          {phase.details.length > 0 && (
            <ul>
              {phase.details.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          )}
          <button type="button" className="secondary-button" onClick={reset}>
            Try again
          </button>
        </div>
      )}

      {phase.kind === "success" && (
        <>
          {phase.fixture && (
            <div className={`fixture-banner ${phase.fixture.isReal ? "fixture-banner-real" : "fixture-banner-synthetic"}`}>
              {phase.fixture.isReal
                ? `DEMO FIXTURE — real captured run (${phase.fixture.label}), not a live optimization`
                : `SYNTHETIC FIXTURE — hand-authored for UI testing (${phase.fixture.label}), not a real run`}
            </div>
          )}
          <RunResult run={phase.run} />
          <button type="button" className="secondary-button reset-button" onClick={reset}>
            Start a new optimization
          </button>
        </>
      )}
    </main>
  );
}

export default App;
