# Strata Architecture

## 1. Current local architecture (this pass)

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
                                              │                 repository    │
                                              │                 interfaces    │
                                              │  app/slicer   — PrusaSlicer   │
                                              │                 adapter       │
                                              │                 (skeleton)    │
                                              │  app/optimization — Pareto,   │
                                              │                 constraints,  │
                                              │                 selection     │
                                              │  app/agent    — planner       │
                                              │                 interface     │
                                              │                 (unimplemented)│
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
- **Slicing**: `PrusaSlicerService` is a real (skeleton) adapter that shells
  out to the `prusa-slicer` CLI. If the binary isn't installed/configured,
  it raises `SlicerUnavailableError` rather than fabricating a result.
- **Agent**: `AgentPlanner` is an interface only — `NotImplementedAgentPlanner`
  raises `NotImplementedError`. No Gemini/ADK calls happen anywhere yet.
- The `/api/v1/runs` endpoint persists run *metadata* only; it does not yet
  trigger slicing, optimization, or the agent loop.

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

The agent loop (parse goals → inspect model → generate candidates → slice →
parse metrics → check constraints → Pareto-compare → iterate → converge or
escalate → emit G-code + decision ledger) runs inside the backend, calling
out to Gemini/ADK for planning steps and to PrusaSlicer workers for ground
truth. Independent candidates can slice in parallel once slicing moves to
its own Cloud Run Job/service.

## 3. Responsibility boundaries

This is the most important architectural rule in the project — see also the
module-level docstrings in `app/agent/interfaces.py` and
`app/optimization/__init__.py`.

| Concern | Owner | Why |
|---|---|---|
| Interpreting user goals, planning next candidates, diagnosing failed slices, deciding whether to keep searching, explaining decisions, recognizing genuine tradeoffs | **Gemini / ADK** (`app/agent`) | Judgment calls that don't have a single correct numeric answer. |
| Hard-constraint validation, Pareto dominance/frontier, ranking, tie-breaking, parameter bounds, file validation | **Deterministic code** (`app/optimization`) | Must be reproducible, auditable, and never hallucinated. |
| Actual print time, filament usage, whether a slice succeeded | **PrusaSlicer** (`app/slicer`) | The only source of truth for manufacturing estimates. Gemini must never guess these numbers. |
| Job execution, artifact storage, run/candidate/decision persistence, parallel slicing | **Google Cloud** (Cloud Run, Firestore, Cloud Storage) | Scalable, durable, and outside the reasoning loop entirely. |

Concretely: Gemini can *decide to try* a steeper layer height or a different
orientation, and can *explain* why a candidate was rejected — but it cannot
tell the user a print will take "about 2 hours" without that number coming
from a `SliceResult`. It cannot decide a candidate is "the best" when the
tradeoff is genuine (see `app/optimization/selection.py`); at that point the
run's status becomes `needs_human_input` and Gemini's job is to phrase the
question for the user, not answer it itself.

## 4. Decision ledger

Each meaningful decision (accepting/rejecting a candidate, escalating to the
user, giving up as infeasible) is recorded as a `DecisionRecord`
(`app/models/decision.py`) — a concise audit entry, not a chain-of-thought
dump. `RunRepository.save_decision`/`list_decisions` persist and retrieve
these per run; the frontend can render them as a timeline once the agent
loop is producing real decisions.

## 5. What's deliberately not built yet

- No Gemini/ADK calls (interface only, see `app/agent/interfaces.py`).
- No agent loop wiring `/api/v1/runs` → candidate generation → slicing →
  optimization → decision ledger.
- No STL upload wired to `StorageService` from the API (accepted as
  metadata only for now).
- No `GcsStorageService` / `FirestoreRunRepository` (interfaces are ready
  for them — see `app/services/storage.py`, `app/services/repository.py`).
- No Cloud Run deployment, Cloud Build pipeline, or Terraform.
- PrusaSlicer CLI flags and G-code parsing in `app/slicer/prusaslicer.py`
  are marked `# TODO(verify)` — they follow commonly-documented conventions
  but have not been checked against a real installed PrusaSlicer binary.

## 6. Next milestone

Wire an end-to-end single-candidate path: upload STL → store via
`StorageService` → build one `CandidateConfiguration` from user-declared
defaults → slice via `PrusaSlicerService` (once flags are verified against a
real binary) → evaluate via `app/optimization` → write one `DecisionRecord`.
That proves the full vertical slice before adding multi-candidate search or
Gemini/ADK planning on top.
