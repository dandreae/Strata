# Strata

**Autonomous manufacturing optimization agent for 3D printing.**

Built for the All Things Agentic Hackathon. A user uploads an STL and states
manufacturing *outcomes* — "produce 500 of these parts, keep each under 3
hours and under 80g of PLA, minimize material" — and Strata is meant to
autonomously search slicer configurations, run them through a real slicer,
and converge on a fabrication-ready result, with a visible decision ledger
explaining what it tried and why.

Full design rationale and the responsibility split between Gemini/ADK,
deterministic optimization code, PrusaSlicer, and Google Cloud lives in
[`docs/architecture.md`](docs/architecture.md).

## Current MVP scope

**It does not implement the autonomous (multi-candidate, Gemini/ADK-driven)
agent loop yet.** What it does do: a real, working, single-candidate,
end-to-end pipeline —

```
STL upload → StorageService → one default CandidateConfiguration
  → PrusaSlicerService → parse real metrics → hard-constraint check
  → DecisionRecord → API response
```

wired into `POST /api/v1/runs`. Concretely, what exists today:

- A typed domain model: `OptimizationRun`, `CandidateConfiguration`,
  `HardConstraints`, `OptimizationPreferences`, `DecisionRecord`, `SliceResult`.
- A FastAPI backend with `/health` and `/api/v1/runs`: `POST` accepts a real
  STL upload + goal metadata, runs the full pipeline above synchronously,
  and returns the run with its candidate(s) and decision ledger; `GET`
  (list/by-id) returns the same.
- Clean service interfaces — `StorageService` (local filesystem today, GCS
  later), `RunRepository` (in-memory today, Firestore later), `SlicerService`
  — plus a real `PrusaSlicerService` adapter that shells out to the
  PrusaSlicer CLI (command construction verified against PrusaSlicer's own
  C++ source; not yet run against a real binary — none is installed in this
  environment, see Limitations) and raises `SlicerUnavailableError` cleanly
  when it isn't.
- Deterministic, unit-tested optimization utilities: hard-constraint
  checking, Pareto dominance/frontier, and preference-based winner selection.
- A placeholder `AgentPlanner` interface (unimplemented) marking where
  Gemini/ADK will plug in; `app/agent/default_candidate.py` is the
  deterministic stand-in it will eventually replace.
- A minimal React/Vite frontend shell with the intake form (not yet updated
  to show real slicing results — see Limitations).

**Not yet built:** multi-candidate search, any Gemini/ADK calls, Firestore/GCS-
backed implementations, Cloud Run deployment, and a background job queue
(the pipeline above runs synchronously inside the HTTP request).

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for diagrams and the full
Gemini vs. deterministic-code vs. PrusaSlicer vs. Google-Cloud breakdown.
Short version:

- **Gemini/ADK** decides — planning, diagnosis, explanations, recognizing
  genuine tradeoffs.
- **Deterministic code** (`backend/app/optimization`) computes — constraint
  checks, Pareto dominance, ranking. Always reproducible, never delegated to
  the LLM.
- **PrusaSlicer** is the only source of truth for print time and filament
  usage. Gemini never guesses these numbers.
- **Google Cloud** (Cloud Run, Firestore, Cloud Storage) handles execution
  and persistence, outside the reasoning loop.

## Local setup

Requires Python 3.11+ and Node 20+.

### Backend

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate        # Windows; use `source .venv/bin/activate` on macOS/Linux
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Backend runs at `http://localhost:8000`. Check `http://localhost:8000/health`
and interactive docs at `http://localhost:8000/docs`.

Configuration is read from environment variables (see `.env.example` at the
repo root, prefixed `STRATA_`). No `.env` is required for local defaults to
work.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

Frontend runs at `http://localhost:5173` and expects the backend at
`http://localhost:8000` (override with `VITE_API_BASE_URL`, see
`frontend/.env.example`).

### Tests

```bash
cd backend
.venv/Scripts/activate
pytest -q
```

56 tests currently pass with the default `pytest -q` (mocked/unit tests
only), covering the health/startup endpoints, the runs API (including a
mocked full slice-to-decision run), constraint/Pareto/selection logic, the
storage service, the orchestrator, and the PrusaSlicer command builder +
G-code parsing helpers.

`tests/test_integration_real_prusaslicer.py` slices the real
`sample_data/cube_20mm.stl` through an actual `prusa-slicer` binary — it
auto-skips when none is found, so a green default run never implies real
slicing was exercised. It **has** been run for real (PrusaSlicer-2.9.6,
2026-08-16) and passed — see Limitations. To run it yourself: install
PrusaSlicer, put `prusa-slicer-console.exe` on PATH or set
`STRATA_PRUSASLICER_BINARY_PATH`, then run `pytest -m integration -q`.

### Docker

```bash
cd backend
docker build -t strata-backend .
docker run -p 8080:8080 strata-backend
```

Then `curl http://localhost:8080/health`. PrusaSlicer is **not** installed
in this image yet (see `backend/Dockerfile` for why and the plan to add it).

> Docker was not available in the environment this pass was built in, so
> the image above has not actually been built/run here — see Blockers below.

## Current limitations

- **Real PrusaSlicer execution is proven but environment-dependent.**
  PrusaSlicer isn't installed by default in fresh dev environments (it
  wasn't in this one until manually installed mid-project). Once installed
  (PrusaSlicer-2.9.6 was used here), `pytest -m integration -q` really slices
  `sample_data/cube_20mm.stl` and passed, e.g. `print_time_seconds=1028`,
  `filament_grams=3.95` — both real PrusaSlicer output, not fabricated. Two
  real bugs were only found this way and are now fixed: `--fill-density`
  needs a `%` suffix (caught by reading PrintConfig.cpp before running
  anything), and without `--filament-density` PrusaSlicer *correctly*
  reports 0g regardless of geometry (only caught by actually running the
  binary and reading its G-code — see comments in
  `backend/app/slicer/prusaslicer.py`). To reproduce: install PrusaSlicer
  (https://www.prusa3d.com/page/prusaslicer_424/), put
  `prusa-slicer-console.exe` on PATH or set
  `STRATA_PRUSASLICER_BINARY_PATH` to its full path, then run
  `pytest -m integration -q` from `backend/`.
- Single candidate only: `POST /api/v1/runs` always tries exactly one fixed,
  conservative configuration (0.2mm layers, 20% infill, 2 perimeters, no
  supports). No search, no multiple candidates, no Pareto comparison in the
  live path yet (the utilities exist and are tested in `app/optimization/`,
  just not wired into the API loop).
- No Gemini/ADK integration — `AgentPlanner` is an interface only.
- Printer/material *profiles* aren't wired up — slicing uses PrusaSlicer's
  built-in engine defaults for anything beyond the five MVP variables.
- The pipeline runs synchronously inside the HTTP request (can take up to
  `STRATA_PRUSASLICER_TIMEOUT_SECONDS`); no background job queue yet.
- The frontend form hasn't been updated to show slicing results — left
  alone this pass since real slicing can't be exercised without PrusaSlicer
  installed.
- Persistence and storage are local/in-memory only; no Firestore or GCS.
- No Cloud Run deployment yet.

## Next milestone

Update the frontend to show real slicing results (print time, filament,
constraint pass/fail, decision outcome) from `POST /api/v1/runs`, now that
the backend pipeline is proven against a real PrusaSlicer binary. Then move
on to multi-candidate search (the
`app/optimization` Pareto/selection utilities already exist for this) before
adding Gemini/ADK planning on top.
