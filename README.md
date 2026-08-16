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

## Current MVP scope (this pass: infrastructure only)

This pass establishes the project skeleton — **it does not implement the
autonomous agent loop yet.** Concretely, what exists today:

- A typed domain model: `OptimizationRun`, `CandidateConfiguration`,
  `HardConstraints`, `OptimizationPreferences`, `DecisionRecord`, `SliceResult`.
- A FastAPI backend with `/health` and a working (metadata-only)
  `/api/v1/runs` create/list/get endpoint, backed by an in-memory repository.
- Clean service interfaces — `StorageService` (local filesystem today, GCS
  later), `RunRepository` (in-memory today, Firestore later), `SlicerService`
  — plus a `PrusaSlicerService` skeleton that shells out to the real
  PrusaSlicer CLI and raises `SlicerUnavailableError` if it isn't installed.
- Deterministic, unit-tested optimization utilities: hard-constraint
  checking, Pareto dominance/frontier, and preference-based winner selection.
- A placeholder `AgentPlanner` interface (unimplemented) marking where
  Gemini/ADK will plug in.
- A minimal React/Vite frontend shell with the intake form (STL upload,
  quantity, constraints, priority) minimally wired to `POST /api/v1/runs`.

**Not yet built:** the actual optimize loop (candidate generation → slice →
evaluate → iterate), any Gemini/ADK calls, STL-to-StorageService wiring on
the API, Firestore/GCS-backed implementations, and any Cloud Run deployment.

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

35 tests currently cover the health/startup endpoints, the runs API,
constraint/Pareto/selection logic, the storage service, and the PrusaSlicer
command builder + G-code parsing helpers.

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

- No agent loop: `/api/v1/runs` records a run but doesn't slice or optimize.
- No Gemini/ADK integration — `AgentPlanner` is an interface only.
- STL upload isn't wired to `StorageService` from the API yet; the frontend
  form collects a file but only sends metadata.
- `PrusaSlicerService`'s CLI flags and G-code parsing are based on commonly
  documented conventions, marked `# TODO(verify)`, and unverified against a
  real PrusaSlicer install (none is available in this environment).
- Persistence and storage are local/in-memory only; no Firestore or GCS.
- No Cloud Run deployment yet.

## Next milestone

Wire one true end-to-end vertical slice: STL upload → `StorageService` →
a single default `CandidateConfiguration` → `PrusaSlicerService` (after
verifying its CLI flags against a real installed PrusaSlicer binary) →
`app/optimization` constraint check → one `DecisionRecord` written and
returned to the frontend. That proves the whole pipe before adding
multi-candidate search or Gemini/ADK planning on top.
