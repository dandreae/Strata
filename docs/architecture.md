# Strata Architecture

## 1. Current local architecture

```
┌─────────────────┐        HTTP/JSON        ┌──────────────────────────────┐
│ frontend (Vite)  │ ───────────────────────▶│ backend (FastAPI)             │
│ React + TS       │                          │                               │
│ localhost:5173   │◀─────────────────────── │  /health                      │
└─────────────────┘                          │  /api/v1/runs                 │
                                              │                               │
                                              │  app/api      — HTTP routes   │
                                              │  app/models   — typed schemas │
                                              │  app/services — storage +     │
                                              │                 repository +  │
                                              │                 orchestrator  │
                                              │  app/slicer   — real          │
                                              │                 PrusaSlicer   │
                                              │                 adapter       │
                                              │  app/optimization — Pareto,   │
                                              │                 constraints,  │
                                              │                 selection     │
                                              │  app/agent    — planner       │
                                              │                 (Deterministic│
                                              │                 or Gemini+ADK)│
                                              └──────────────────────────────┘
                                                        │
                                                        ▼
                                              local filesystem (`./data`)
                                              in-process dict (runs/candidates)
```

- **Storage**: `LocalStorageService` writes uploaded STLs and generated
  G-code under `./data/runs/{run_id}/...` on the local filesystem.
- **Persistence**: `InMemoryRunRepository` holds runs/candidates/decisions in
  a process-local dict. Restarting the backend loses all data — expected for
  this pass.
- **Slicing**: `PrusaSlicerService` is a real adapter that shells out to the
  `prusa-slicer` CLI. Its command construction and G-code parsing are
  grounded in PrusaSlicer's own C++ source and **confirmed against a real
  installed binary** (PrusaSlicer-2.9.6). If the binary isn't
  installed/configured, it raises `SlicerUnavailableError` rather than
  fabricating a result.
- **Agent**: `AgentPlanner` (`app/agent/interfaces.py`) has two real
  implementations — `DeterministicPlanner` (wraps the original fixed
  candidate set) and `GeminiAgentPlanner` (Gemini + Google ADK) — selected
  by `STRATA_PLANNER_MODE`. See §4 for the validation boundary between them.
- `POST /api/v1/runs` wires the full pipeline synchronously: STL upload →
  `StorageService` → planner → `PrusaSlicerService` (once per candidate) →
  `app/optimization` constraint/Pareto/selection → two `DecisionRecord`s
  (planning, then final) → response.

## 2. Intended hackathon architecture

```
┌──────────┐   STL + goals    ┌────────────────────┐
│ Frontend │ ───────────────▶ │ Backend API         │
│ (Cloud   │                  │ (Cloud Run)          │
│  Run /   │ ◀─────────────── │                       │
│  static  │  run status,     │  Orchestrates the     │
│  hosting)│  decision ledger │  agent loop; persists  │
└──────────┘                  │  to Firestore/GCS      │
                               └─────────┬─────────────┘
                                         │
                        ┌────────────────┼─────────────────┐
                        ▼                ▼                  ▼
              ┌──────────────┐  ┌────────────────┐  ┌───────────────┐
              │ Gemini + ADK  │  │ Deterministic   │  │ PrusaSlicer    │
              │ (planning,    │  │ optimization    │  │ worker(s)      │
              │  diagnosis,   │  │ (constraints,   │  │ (Cloud Run     │
              │  explanation) │  │  Pareto, rank)  │  │  jobs, run in  │
              └──────────────┘  └────────────────┘  │  parallel per   │
                                                      │  candidate)     │
                                                      └───────────────┘
                        │                                    │
                        ▼                                    ▼
              ┌──────────────────────────────────────────────────┐
              │ Firestore: runs, candidates, decision ledger       │
              │ Cloud Storage: uploaded STLs, generated G-code     │
              └──────────────────────────────────────────────────┘
```

The full adaptive agent loop (parse goals → inspect model → generate
candidates → slice → parse metrics → check constraints → Pareto-compare →
**iterate on previous results** → converge or escalate → emit G-code +
decision ledger) runs inside the backend. Today only the *first* candidate
round is agent-generated (§4); the "iterate on previous results" step is
not built yet (§5). Independent candidates can slice in parallel once
slicing moves to its own Cloud Run Job/service.

## 3. Responsibility boundaries

This is the most important architectural rule in the project — see also the
module-level docstrings in `app/agent/interfaces.py`,
`app/agent/gemini_planner.py`, and `app/optimization/__init__.py`.

| Concern | Owner | Why |
|---|---|---|
| Proposing candidate configurations to try (first round only, today) | **Gemini / ADK** (`app/agent/gemini_planner.py`), or `DeterministicPlanner` in dev/test/offline mode | A judgment call about which experiments are worth running — no single correct answer. |
| Hard-constraint validation, Pareto dominance/frontier, ranking, tie-breaking, parameter bounds, file validation, **and validating every planner proposal before it can reach PrusaSlicer** | **Deterministic code** (`app/optimization`, `app/agent/planner_validation.py`) | Must be reproducible, auditable, and never hallucinated. |
| Actual print time, filament usage, whether a slice succeeded | **PrusaSlicer** (`app/slicer`) | The only source of truth for manufacturing estimates. Gemini must never guess these numbers. |
| Job execution, artifact storage, run/candidate/decision persistence, parallel slicing | **Google Cloud** (Cloud Run, Firestore, Cloud Storage) | Scalable, durable, and outside the reasoning loop entirely. |

Concretely: Gemini can *decide to try* a thinner layer height or a lower
infill percentage, and its `planning_summary` can *explain* the experiment
strategy — but it cannot tell the user a print will take "about 2 hours"
without that number coming from a `SliceResult`, and it cannot decide a
candidate is "the best" when the tradeoff is genuine (see
`app/optimization/selection.py`); at that point the run's status becomes
`needs_human_input`.

## 4. The Gemini/ADK validation boundary

```
Gemini + Google ADK (LlmAgent, output_schema-constrained JSON)
        ↓
CandidateProposal — typed, but still UNTRUSTED (app/agent/planner_schema.py)
        ↓
VALIDATION BOUNDARY (app/agent/planner_validation.py, deterministic, no LLM)
  - bounds check (layer_height 0.10-0.30mm, infill 5-40%, perimeters 2-4)
  - reject NaN/Infinity
  - reject duplicates
  - hard cap on candidate count (MAX_CANDIDATES_PER_ROUND)
        ↓
CandidateConfiguration — trusted domain model
        ↓
PrusaSlicer command builder (app/slicer/prusaslicer.py)
        ↓
Measured truth (SliceResult: real print time, real filament grams)
        ↓
Deterministic optimization (constraints → Pareto → selection, unchanged
by which planner proposed the candidates)
```

**Why LLM output is treated as untrusted input.** Gemini's response is
schema-constrained (ADK's `output_schema`) but schema conformance is not
the same as a *safe* value — nothing stops a schema-valid response from
proposing `layer_height=5` or `infill_percent=-20`. Every proposal is
independently bounds-checked, finite-checked, deduplicated, and count-capped
by plain Python before it ever becomes a `CandidateConfiguration`. Gemini
never sees a shell, a subprocess argument, a file path, or a slicer flag —
it only ever emits three bounded numbers plus a short summary string.

**Why Gemini doesn't calculate manufacturing metrics.** It has no way to
know real print time or filament usage — only PrusaSlicer does, after
actually slicing the geometry. The planner's job is to propose *hypotheses*
worth testing, not to predict their outcomes; nothing Gemini returns is
ever written to a candidate's `print_time_seconds`/`filament_grams` fields
(those are populated only from a real `SliceResult`, in
`app/services/orchestrator.py::_slice_and_apply`, regardless of which
planner proposed the candidate).

**Why a deterministic fallback exists.** `DeterministicPlanner` (wrapping
the original fixed 8-candidate set) implements the exact same `AgentPlanner`
contract as `GeminiAgentPlanner`. It's the default (`STRATA_PLANNER_MODE=
deterministic`) so the whole test suite, CI, and offline development never
require network access or an API key. It is **not** a silent fallback
*during* a Gemini-mode run — if `STRATA_PLANNER_MODE=gemini` is explicitly
set and the Gemini call fails (bad key, network error, quota, malformed
output, or every proposal failing validation), the run fails clearly
(`PlannerError` → run status `failed`, with the real error message in the
decision ledger) rather than silently substituting the fixed set. Which
planner ran, and why it's the one that ran, is itself an operator choice
(the env var), never a runtime decision made silently on Gemini's behalf.

**Current limitation: only first-round planning is agent-generated.**
`plan_initial_candidates` is called exactly once per run. Gemini never sees
the results of its own proposals — `should_continue_searching` exists on
the interface for contract completeness but both planners return `False`
unconditionally. Strata is not adaptive yet; that's the next milestone (§6).

## 5. Decision ledger

Each meaningful decision is recorded as a `DecisionRecord`
(`app/models/decision.py`) — a concise audit entry, not a chain-of-thought
dump. A completed run now has (at least) two: one from planning
(`selected_action="plan_initial_candidates"`, evidence includes the
planner's `planning_summary`) and one final outcome
(`select_candidate` / `no_feasible_candidate` / `escalate_tradeoff` /
`abort_run`). `RunRepository.save_decision`/`list_decisions` persist and
retrieve these per run; the frontend renders both (see
`frontend/src/components/RunResult.tsx`).

## 6. What's built vs. what's deliberately not built yet

Built: `POST /api/v1/runs` wires a real STL upload → `StorageService` →
planner-proposed candidate set (deterministic or Gemini+ADK, per
`STRATA_PLANNER_MODE`) → `PrusaSlicerService` for every candidate → real
metric parsing → `app/optimization` constraint/Pareto/selection → decision
ledger, end to end, synchronously, inside the request
(`app/services/orchestrator.py`). Verified against a real installed
PrusaSlicer binary (`tests/test_integration_real_prusaslicer.py`, real
multi-candidate runs) and, when valid credentials are configured, against a
real Gemini call (`tests/test_gemini_smoke.py`) — both auto-skip and are
excluded from the default `pytest -q`, so a green default run never implies
either actually executed.

Still not built:

- No adaptive second round — Gemini never sees its own proposals' results;
  `should_continue_searching` is unconditionally `False` (§4).
- No printer/material *profile* loading (`--load`) — slicing uses
  PrusaSlicer's built-in defaults for anything beyond the MVP variables;
  `printer_profile` on a run is currently informational only.
- No background job queue — the pipeline (including the Gemini call) blocks
  the HTTP request for its duration.
- No `GcsStorageService` / `FirestoreRunRepository` (interfaces are ready
  for them — see `app/services/storage.py`, `app/services/repository.py`).
- No Cloud Run deployment, Cloud Build pipeline, or Terraform.
- No parallel slicing — candidates are sliced sequentially.

## 7. Next milestone

Feed measured results back into the planner: give `AgentPlanner` the
previous round's `CandidateConfiguration`s (with real metrics) and let it
decide, via `should_continue_searching`, whether to propose a second round
targeting the unexplored parts of the tradeoff surface. That's the
adaptive loop the interface was always shaped for (§1's original
`propose_candidates(run, previous_results)` concept) — this milestone only
proved the first, non-adaptive round works safely end to end.
