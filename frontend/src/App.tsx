import { useState, type FormEvent } from "react";
import "./App.css";
import { RunResult } from "./components/RunResult";
import { ApiError, createRun, type Objective, type RunDetail } from "./lib/api";
import { validateForm } from "./lib/validate";

// Printer profile is fixed for this milestone — no profile selection UI yet,
// and the backend doesn't load a profile file either (see
// docs/architecture.md); it's accepted for future use.
const PRINTER_PROFILE = "generic_pla";

type RunState =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "success"; run: RunDetail }
  | { kind: "error"; message: string; details: string[] };

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [quantity, setQuantity] = useState(100);
  const [maxPrintMinutes, setMaxPrintMinutes] = useState(180);
  const [maxMaterialGrams, setMaxMaterialGrams] = useState(80);
  const [objective, setObjective] = useState<Objective>("balanced");
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [runState, setRunState] = useState<RunState>({ kind: "idle" });

  const isRunning = runState.kind === "loading";

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    const errors = validateForm({
      file,
      productionQuantity: quantity,
      maxPrintTimeMinutes: maxPrintMinutes,
      maxFilamentGrams: maxMaterialGrams,
    });
    setValidationErrors(errors);
    if (errors.length > 0 || !file) return;

    setRunState({ kind: "loading" });
    try {
      const run = await createRun({
        file,
        productionQuantity: quantity,
        printerProfile: PRINTER_PROFILE,
        maxPrintTimeSeconds: Math.round(maxPrintMinutes * 60),
        maxFilamentGrams: maxMaterialGrams,
        objective,
      });
      setRunState({ kind: "success", run });
    } catch (err) {
      if (err instanceof ApiError) {
        setRunState({ kind: "error", message: err.message, details: err.details });
      } else {
        setRunState({ kind: "error", message: "Unexpected error contacting the backend.", details: [] });
      }
    }
  }

  return (
    <main className="page">
      <header>
        <h1>Strata</h1>
        <p className="tagline">Autonomous manufacturing optimization</p>
      </header>

      <form className="run-form" onSubmit={handleSubmit}>
        <label>
          STL file
          <input
            type="file"
            accept=".stl"
            disabled={isRunning}
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <label>
          Production quantity
          <input
            type="number"
            min={1}
            value={quantity}
            disabled={isRunning}
            onChange={(e) => setQuantity(Number(e.target.value))}
          />
        </label>

        <label>
          Max print time (minutes, per part)
          <input
            type="number"
            min={0}
            step={1}
            value={maxPrintMinutes}
            disabled={isRunning}
            onChange={(e) => setMaxPrintMinutes(Number(e.target.value))}
          />
        </label>

        <label>
          Max material (grams, per part)
          <input
            type="number"
            min={0}
            step={0.1}
            value={maxMaterialGrams}
            disabled={isRunning}
            onChange={(e) => setMaxMaterialGrams(Number(e.target.value))}
          />
        </label>

        <label>
          Optimization priority
          <select
            value={objective}
            disabled={isRunning}
            onChange={(e) => setObjective(e.target.value as Objective)}
          >
            <option value="balanced">Balanced</option>
            <option value="minimize_material">Minimize material</option>
            <option value="minimize_time">Minimize print time</option>
          </select>
        </label>

        <button type="submit" disabled={isRunning}>
          {isRunning ? "Slicing…" : "Start Optimization"}
        </button>
      </form>

      {validationErrors.length > 0 && (
        <ul className="status status-error">
          {validationErrors.map((msg, i) => (
            <li key={i}>{msg}</li>
          ))}
        </ul>
      )}

      {runState.kind === "loading" && <p className="status status-loading">Analyzing and slicing model…</p>}

      {runState.kind === "error" && (
        <div className="status status-error">
          <p>{runState.message}</p>
          {runState.details.length > 0 && (
            <ul>
              {runState.details.map((msg, i) => (
                <li key={i}>{msg}</li>
              ))}
            </ul>
          )}
        </div>
      )}

      {runState.kind === "success" && <RunResult run={runState.run} />}
    </main>
  );
}

export default App;
