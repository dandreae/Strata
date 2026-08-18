# Strata

**Autonomous manufacturing optimization agent for 3D printing.**

Built for the All Things Agentic Hackathon. A user uploads an STL and states
manufacturing *outcomes* — "produce 500 of these parts, keep each under 3
hours and under 80g of PLA, minimize material" — and Strata proposes a
bounded set of manufacturing configurations, slices every one through a real
slicer, and picks a winner, with a visible decision ledger explaining what
it tried and why.

Full design rationale and the responsibility split between Gemini/ADK,
deterministic optimization code, PrusaSlicer, and Google Cloud lives in
[`docs/architecture.md`](docs/architecture.md).

## Current MVP scope

**It does not implement the fully adaptive (multi-round, feedback-driven)
agent loop yet.** What it does do: a real, working, end-to-end pipeline —

```
STL upload → StorageService
  → planner (deterministic fixed set, OR Gemini + Google ADK — first round only)
  → deterministic validation of every proposed candidate
  → real PrusaSlicer, once per candidate
  → parse real metrics → hard-constraint check → Pareto frontier
  → preference-based winner selection → decision ledger → API response
```

wired into `POST /api/v1/runs`, and shown in the browser. Concretely, what
exists today:

- A typed domain model: `OptimizationRun`, `CandidateConfiguration`,
  `HardConstraints`, `OptimizationPreferences`, `DecisionRecord`, `SliceResult`.
- A FastAPI backend with `/health` and `/api/v1/runs`: `POST` accepts a real
  STL upload + goal metadata, runs the full pipeline above synchronously,
  and returns the run with every candidate tried (real metrics, feasibility,
  Pareto-optimality, selection), an optimization summary, and the decision
  ledger; `GET` (list/by-id) returns the same.
- A real `PrusaSlicerService` adapter — command construction and G-code
  parsing were grounded in PrusaSlicer's own C++ source and then **confirmed
  against a real installed binary** (PrusaSlicer-2.9.6).
- Deterministic, unit-tested optimization utilities: hard-constraint
  checking, Pareto dominance/frontier, and preference-based winner selection
  — unchanged regardless of which planner proposed the candidates.
- **`AgentPlanner`, implemented two ways**: `DeterministicPlanner` (the
  original fixed 8-candidate set, default, offline/free) and
  `GeminiAgentPlanner` (real Gemini + Google ADK, proposes the *first*
  candidate round only). Selected via `STRATA_PLANNER_MODE`. Every
  Gemini-proposed candidate passes through a deterministic validation
  boundary (`app/agent/planner_validation.py`) — bounds, NaN/Infinity,
  duplicates, and a hard count cap — before it can ever reach PrusaSlicer.
  See `docs/architecture.md` §4.
- A React/Vite frontend showing the experiment plan, an optimization
  summary, the selected candidate, a full candidate comparison table, and
  the decision ledger — all backend-computed, nothing recalculated in TS.

**Not yet built:** adaptive second-round planning (Gemini never sees its
own proposals' measured results yet), Cloud deployment, Firestore/GCS-backed
implementations, a background job queue (the pipeline — including the
Gemini call — runs synchronously inside the HTTP request), and parallel
slicing.

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for diagrams, the full
Gemini vs. deterministic-code vs. PrusaSlicer vs. Google-Cloud breakdown,
and the Gemini/ADK validation boundary. Short version:

- **Gemini/ADK** proposes — which experiments (candidate configurations) are
  worth running, for the first round only. Never predicts print time or
  material, never chooses the winner.
- **Deterministic code** (`backend/app/optimization`,
  `backend/app/agent/planner_validation.py`) computes and validates —
  constraint checks, Pareto dominance, ranking, and every bound on what
  Gemini is allowed to propose. Always reproducible, never delegated to
  the LLM.
- **PrusaSlicer** is the only source of truth for print time and filament
  usage. Gemini never guesses these numbers.
- **Google Cloud** (Cloud Run, Firestore, Cloud Storage) handles execution
  and persistence, outside the reasoning loop — not deployed yet.

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
work — the default `STRATA_PLANNER_MODE=deterministic` needs no credentials
at all. To use the real Gemini planner instead:

```bash
export STRATA_PLANNER_MODE=gemini
export STRATA_GEMINI_API_KEY=<your Gemini API key>
```

The server refuses to start in `gemini` mode without a key configured — see
Limitations.

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

Passes fully offline — no PrusaSlicer binary, no network, no Gemini
credentials required. Covers the health/startup endpoints, the runs API,
constraint/Pareto/selection logic, the multi-candidate orchestrator
(including partial-failure and planner-abstraction behavior), the
PrusaSlicer command builder + G-code parsing, and the full Gemini/ADK
planner boundary — schema validation, bounds, duplicates, count caps, and
call-failure handling — with the ADK boundary mocked.

Two kinds of tests are excluded from the default run and auto-skip when
their prerequisite isn't available, so a green `pytest -q` never implies
either actually executed:

```bash
# Real PrusaSlicer binary required. Verified: real 8-candidate runs on
# sample_data/cube_20mm.stl produced genuine, hand-checked-correct
# Pareto/selection results (see docs/architecture.md history).
pytest -m integration -q

# Real Gemini API key required. See Limitations for current status.
pytest -m gemini_smoke -v -s
```

### Docker

```bash
cd backend
docker build -t strata-backend .
docker run -p 8080:8080 strata-backend
```

Then `curl http://localhost:8080/health`. PrusaSlicer is **not** installed
in this image yet (see `backend/Dockerfile` for why and the plan to add it).

## Current limitations

- **Adaptive planning isn't built yet.** Gemini proposes the first candidate
  round only; it never sees the measured results of its own proposals.
  `AgentPlanner.should_continue_searching` exists on the interface but both
  implementations return `False` unconditionally. This is the explicit next
  milestone (see `docs/architecture.md` §7).
- **The real Gemini smoke test currently fails on invalid credentials in
  this dev environment** — a `GEMINI_API_KEY` is present in the ambient
  environment but the Gemini API rejects it (`400 API_KEY_INVALID`). The
  integration code path is proven correct (mocked tests pass; the real call
  was attempted and failed *cleanly*, with the real error message surfaced
  via `PlannerError`, not silently swallowed — that failure-path discovery
  is itself real evidence the "fail clearly, no silent fallback" behavior
  works). To actually exercise a successful real call: obtain a valid key
  from https://aistudio.google.com/apikey and set `STRATA_GEMINI_API_KEY`.
- No printer/material *profiles* — slicing uses PrusaSlicer's built-in
  engine defaults for anything beyond the MVP variables (layer height,
  infill, perimeters).
- The pipeline (including the Gemini call, when active) runs synchronously
  inside the HTTP request; no background job queue yet.
- No parallel slicing — candidates are sliced sequentially.
- Persistence and storage are local/in-memory only; no Firestore or GCS.
- No Cloud Run deployment yet.

## Next milestone

Feed measured results back into the planner: pass the previous round's real
`CandidateConfiguration`s (with actual print time/filament usage) into
`AgentPlanner`, and use `should_continue_searching` to decide whether a
second, targeted round is worth proposing. See
`docs/architecture.md` §7 for the full rationale.
