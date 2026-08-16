import { useState, type FormEvent } from "react";
import "./App.css";

// Backend base URL. In production this should come from a build-time env
// var (see .env.example); hardcoded to local dev for this pass.
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

type Objective = "minimize_material" | "minimize_time" | "balanced";

type SubmitState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "success"; runId: string }
  | { kind: "error"; message: string };

function App() {
  const [file, setFile] = useState<File | null>(null);
  const [quantity, setQuantity] = useState(100);
  const [maxPrintHours, setMaxPrintHours] = useState(3);
  const [maxMaterialGrams, setMaxMaterialGrams] = useState(80);
  const [objective, setObjective] = useState<Objective>("balanced");
  const [submitState, setSubmitState] = useState<SubmitState>({ kind: "idle" });

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitState({ kind: "submitting" });

    // NOTE: this MVP pass only sends run *metadata*. Uploading the actual
    // STL bytes to StorageService is not wired up yet — see
    // docs/architecture.md. The filename is included so the shape of the
    // request matches what the backend will eventually expect.
    try {
      const response = await fetch(`${API_BASE_URL}/api/v1/runs`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          filename: file?.name ?? "unnamed.stl",
          production_quantity: quantity,
          printer_profile: "generic_pla",
          hard_constraints: {
            max_print_time_seconds: Math.round(maxPrintHours * 3600),
            max_filament_grams: maxMaterialGrams,
          },
          optimization_preferences: { objective },
        }),
      });

      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(body.message ?? `Request failed (${response.status})`);
      }

      const run = await response.json();
      setSubmitState({ kind: "success", runId: run.id });
    } catch (err) {
      setSubmitState({
        kind: "error",
        message: err instanceof Error ? err.message : "Could not reach the Strata backend.",
      });
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
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
        </label>

        <label>
          Production quantity
          <input
            type="number"
            min={1}
            value={quantity}
            onChange={(e) => setQuantity(Number(e.target.value))}
          />
        </label>

        <label>
          Max print time (hours, per part)
          <input
            type="number"
            min={0}
            step={0.25}
            value={maxPrintHours}
            onChange={(e) => setMaxPrintHours(Number(e.target.value))}
          />
        </label>

        <label>
          Max material (grams, per part)
          <input
            type="number"
            min={0}
            value={maxMaterialGrams}
            onChange={(e) => setMaxMaterialGrams(Number(e.target.value))}
          />
        </label>

        <label>
          Optimization priority
          <select value={objective} onChange={(e) => setObjective(e.target.value as Objective)}>
            <option value="balanced">Balanced</option>
            <option value="minimize_material">Minimize material</option>
            <option value="minimize_time">Minimize print time</option>
          </select>
        </label>

        <button type="submit" disabled={submitState.kind === "submitting"}>
          {submitState.kind === "submitting" ? "Starting…" : "Start Optimization"}
        </button>
      </form>

      {submitState.kind === "success" && (
        <p className="status status-success">Run created: {submitState.runId}</p>
      )}
      {submitState.kind === "error" && (
        <p className="status status-error">
          {submitState.message} (is the backend running at {API_BASE_URL}?)
        </p>
      )}
    </main>
  );
}

export default App;
