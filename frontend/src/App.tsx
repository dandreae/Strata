import { useState } from "react";
import "./App.css";
import { AgentPipeline } from "./components/AgentPipeline";
import { DemoModeToggle } from "./components/DemoModeToggle";
import { PartPreviewPanel } from "./components/PartPreviewPanel";
import { ReplayExperience } from "./components/ReplayExperience";
import { RunResult } from "./components/RunResult";
import type { StlSource } from "./components/StlViewer";
import { ApiError, createRun, type RunDetail } from "./lib/api";
import { getInitialDemoMode, setDemoMode as persistDemoMode } from "./lib/demoMode";
import { DEFAULT_FIXTURE_KEY, getFixture } from "./lib/fixtures";
import { getFixtureModelUrl } from "./lib/fixtureModels";
import { SetupForm, type SetupValues } from "./components/SetupForm";

// Printer profile is fixed for this milestone — no profile selection UI yet,
// and the backend doesn't load a profile file either (see
// docs/architecture.md); it's accepted for future use.
const PRINTER_PROFILE = "generic_pla";

type FixtureInfo = { isReal: boolean; label: string };

type Phase =
  | { kind: "idle" }
  | { kind: "loading"; model: StlSource } // live mode: waiting on the real backend, no result data known yet — but the real uploaded part is
  | { kind: "replaying"; run: RunDetail; fixture: FixtureInfo; model: StlSource | null } // demo mode: staging an already-known run
  | { kind: "success"; run: RunDetail; fixture: FixtureInfo | null; model: StlSource | null }
  | { kind: "error"; message: string; details: string[]; model: StlSource | null };

function FixtureBanner({ fixture }: { fixture: FixtureInfo }) {
  return (
    <div className={`fixture-banner ${fixture.isReal ? "fixture-banner-real" : "fixture-banner-synthetic"}`}>
      {fixture.isReal
        ? `Recorded real optimization run — replaying captured agent events (${fixture.label})`
        : `SYNTHETIC FIXTURE — hand-authored for UI testing (${fixture.label}), not a real run`}
    </div>
  );
}

/** The fixture's own real geometry (see lib/fixtureModels.ts) once we're past
 * setup — not whatever file happened to be sitting in the dropzone, since
 * demo mode never actually submits that file's contents. */
function fixtureModelSource(filename: string): StlSource | null {
  const url = getFixtureModelUrl(filename);
  return url ? { kind: "url", url } : null;
}

function App() {
  const [phase, setPhase] = useState<Phase>({ kind: "idle" });
  const [demoMode, setDemoModeState] = useState(getInitialDemoMode);
  const [scenarioKey, setScenarioKey] = useState(DEFAULT_FIXTURE_KEY);

  const isBusy = phase.kind === "loading" || phase.kind === "replaying";

  function toggleDemoMode(enabled: boolean) {
    setDemoModeState(enabled);
    persistDemoMode(enabled);
  }

  async function handleSubmit(values: SetupValues) {
    if (demoMode) {
      // The full result is already known (it's a fixture) — ReplayExperience
      // only controls how it's *revealed* over time. Nothing here waits on
      // a network call or invents data as it goes. The viewer shows the
      // fixture's own real model, not the (ignored) file dropped in the form.
      const fixture = getFixture(scenarioKey);
      setPhase({
        kind: "replaying",
        run: fixture.data,
        fixture: { isReal: fixture.isReal, label: fixture.label },
        model: fixtureModelSource(fixture.data.filename),
      });
      return;
    }

    const model: StlSource = { kind: "file", file: values.file };
    setPhase({ kind: "loading", model });
    try {
      const run = await createRun({
        file: values.file,
        productionQuantity: values.quantity,
        printerProfile: PRINTER_PROFILE,
        maxPrintTimeSeconds: Math.round(values.maxPrintMinutes * 60),
        maxFilamentGrams: values.maxMaterialGrams,
        objective: values.objective,
      });
      setPhase({ kind: "success", run, fixture: null, model });
    } catch (err) {
      // Keep showing the real uploaded part even on failure.
      if (err instanceof ApiError) {
        setPhase({ kind: "error", message: err.message, details: err.details, model });
      } else {
        setPhase({ kind: "error", message: "Unexpected error contacting the backend.", details: [], model });
      }
    }
  }

  function finishReplay() {
    if (phase.kind !== "replaying") return;
    setPhase({ kind: "success", run: phase.run, fixture: phase.fixture, model: phase.model });
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

      {import.meta.env.PROD && (
        <p className="demo-mode-notice">
          Interactive demo — uses precomputed optimization results. See the demo video for the live end-to-end run.
        </p>
      )}

      <ol className="flow-steps">
        {/* Upload + constraints share one screen (SetupForm), so both read
            "current" together while idle, then "done" from loading on. */}
        <li className={phase.kind === "idle" ? "flow-step-current" : "flow-step-done"}>Upload part</li>
        <li className={phase.kind === "idle" ? "flow-step-current" : "flow-step-done"}>Define constraints</li>
        <li
          className={
            phase.kind === "loading" || phase.kind === "replaying"
              ? "flow-step-current"
              : phase.kind === "success" || phase.kind === "error"
                ? "flow-step-done"
                : ""
          }
        >
          Watch agent work
        </li>
        <li className={phase.kind === "success" || phase.kind === "error" ? "flow-step-current" : ""}>
          Review recommendation
        </li>
      </ol>

      {phase.kind === "idle" && <SetupForm disabled={false} onSubmit={handleSubmit} />}

      {phase.kind === "loading" && (
        <div className="working-layout">
          <PartPreviewPanel source={phase.model} compact />
          <AgentPipeline />
        </div>
      )}

      {phase.kind === "replaying" && (
        <>
          <FixtureBanner fixture={phase.fixture} />
          <div className="working-layout">
            <PartPreviewPanel source={phase.model} compact />
            <ReplayExperience run={phase.run} onComplete={finishReplay} />
          </div>
        </>
      )}

      {phase.kind === "error" && (
        <>
          <PartPreviewPanel source={phase.model} compact />
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
        </>
      )}

      {phase.kind === "success" && (
        <>
          {phase.fixture && <FixtureBanner fixture={phase.fixture} />}
          <PartPreviewPanel source={phase.model} compact />
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
