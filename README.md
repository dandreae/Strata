# Strata

**An agent that designs its own manufacturing experiments, runs them for real, and explains its decision.**

Built for the All Things Agentic Hackathon.

Upload a part (STL) and say what you care about — "minimize material, keep
each print under 3 hours, under 80g of PLA." Strata doesn't ask you to tune
slicer settings. Instead: **Gemini proposes a batch of manufacturing
configurations to test, a real slicer measures every one of them, Gemini
reads those measurements and decides whether a second, targeted round of
experiments is worth running, and a deterministic optimizer picks the
winner from every real result** — with a full decision ledger showing what
was tried, what was measured, and why the winner won.

## Why this is agentic, not a chatbot with a slicer bolted on

The distinction that matters: **Gemini never predicts a print time or a
gram of filament.** It can't — nothing can, short of actually slicing the
geometry. Its only job is deciding what's worth *trying*, then reading
real measurements back and deciding whether to try again. That loop —
propose → measure → adapt → propose again → converge — is what makes this
an agent rather than a single LLM call with a nice UI around it.

A real run, captured against the deployed Cloud Run service:

```
Round 1 — Gemini proposes 8 configurations spanning the layer-height /
          infill / perimeter search space
        → real PrusaSlicer slices all 8 → real measured print time & material
Round 2 — Gemini reads the 8 real results: "All Round 1 candidates easily
          met the constraints. To minimize material further, explore
          minimal infill and wall loops around 0.1mm layer height."
        → proposes 4 new, targeted configurations
        → real PrusaSlicer slices all 4
Selection — 12 real results, 6 Pareto-optimal, deterministic code picks
            the winner: 0.10mm / 5% infill / 2 perimeters
            → 22m 20s print time, 2.71g material (measured, not predicted)
```

Exactly **2 Gemini calls** for the entire run (hard-capped — see
Guardrails below), end-to-end in **35 seconds**, including 12 real
PrusaSlicer subprocess invocations inside the actual Cloud Run container.

## Proof this is real, not a mockup

- **Real Gemini 3.5 Flash + Google ADK** calls — not simulated, not cached responses in the live path.
- **Real PrusaSlicer 2.9.2**, apt-installed and version-pinned inside the deployed container (`prusa-slicer --help` runs as a Docker build-time sanity check) — every print time and gram figure in a run comes from an actual slice, never an LLM guess.
- **Deployed and proven on Google Cloud Run** (`us-east1`) — real container, real request, real response, verified end-to-end including the Gemini calls happening *inside* the Cloud Run request.
- **Every LLM proposal is deterministically validated** before it can reach the slicer — bounds-checked, NaN/Infinity-rejected, deduplicated, count-capped (`app/agent/planner_validation.py`). Gemini never touches a shell, a file path, or a subprocess argument.
- **A visible decision ledger** for every run — not chain-of-thought, a concise audit trail: what was proposed, what was measured, why the loop continued or stopped, why the winner won.

## Architecture

```
┌──────────────┐   STL + goals    ┌─────────────────────────────────────────┐
│ Frontend      │ ───────────────▶│ Backend (FastAPI, Cloud Run)             │
│ React + Vite  │                  │                                          │
│               │◀──────────────── │  POST /api/v1/runs — one blocking call: │
└──────────────┘  full result      │                                          │
                                   │  1. Gemini + ADK → Round 1 proposals     │
                                   │  2. deterministic validation             │
                                   │  3. real PrusaSlicer × N candidates      │
                                   │  4. Gemini reads Round 1 results →       │
                                   │     continue or stop                     │
                                   │  5. (if continuing) validate + slice     │
                                   │     Round 2 the same way                 │
                                   │  6. deterministic Pareto frontier +      │
                                   │     preference-based winner selection    │
                                   │  7. decision ledger                      │
                                   └─────────────────────────────────────────┘
```

Full responsibility split (who's allowed to decide what, and why) is in
[`docs/architecture.md`](docs/architecture.md). Short version:

| Concern | Owner |
|---|---|
| Which configurations are worth testing, and whether to run a second round | **Gemini + Google ADK** |
| Bounds-checking every LLM proposal, constraint checks, Pareto dominance, winner selection | **Deterministic code** (`app/optimization`, `app/agent/planner_validation.py`) |
| Actual print time / material usage | **PrusaSlicer** — the only source of truth |
| Hosting, secrets | **Google Cloud** (Cloud Run, Artifact Registry, Secret Manager) |

## Guardrails (the agent is bounded on purpose)

- Max **2 rounds**, max **8 candidates/round**, max **1 Gemini call/round** — hard caps, not soft guidance.
- No candidate reaches PrusaSlicer without passing deterministic validation first.
- No silent fallback: if Gemini mode is explicitly requested and the call fails, the run fails clearly with the real error in the decision ledger — it never silently substitutes a different planner.
- No API keys in the container image — the Gemini key is injected at deploy time from Google Secret Manager.

## Google technologies used

Gemini 3.5 Flash · Google ADK (`LlmAgent`, structured `output_schema`) · Google Cloud Run · Artifact Registry · Secret Manager.

## Try it yourself

**Zero setup — fixture mode** (real captured API responses, no network calls):
```bash
cd frontend && npm install && npm run dev
```
Open the printed URL — the "Demo data" toggle is on by default and includes the real 2-round run described above.

**Real local backend** (deterministic mode — free, no Gemini calls):
```bash
cd backend && python -m venv .venv && .venv/Scripts/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```
Toggle "Demo data" off in the frontend to hit it. To use the real Gemini
planner instead of the deterministic fixed set, set `STRATA_PLANNER_MODE=gemini`
and `STRATA_GEMINI_API_KEY` in `backend/.env` (get a key at
https://aistudio.google.com/apikey).

**Tests** (offline, zero network calls, zero cost):
```bash
cd backend && pytest -q
```
137 tests. Two additional suites are excluded by default and auto-skip
without their prerequisite: `pytest -m integration` (real PrusaSlicer
binary) and `pytest -m gemini_smoke` (real, billable Gemini key).

## Repository map

```
backend/app/agent/        Gemini + ADK planner, deterministic validation boundary
backend/app/slicer/       Real PrusaSlicer CLI adapter (command build + G-code parsing)
backend/app/optimization/ Constraint checks, Pareto frontier, winner selection
backend/app/services/     Orchestrator (the 7-step pipeline above), storage, repository
backend/Dockerfile        Cloud Run image — Debian trixie + apt-installed PrusaSlicer
frontend/src/components/  Setup form, agent pipeline visualization, Pareto chart, decision ledger
frontend/src/lib/fixtures.ts  Real captured responses used in demo mode
docs/architecture.md      Full design rationale, validation boundary, decision ledger schema
```

## Current scope (deliberately bounded)

Built: real end-to-end pipeline above, deployed to Cloud Run, adaptive
2-round Gemini loop, Pareto visualization, full decision ledger.

Not built (out of scope by design, not oversight): Firestore/Cloud
Storage-backed persistence (local/in-memory only), parallel slicing
(candidates slice sequentially), printer/material profile loading
(PrusaSlicer's built-in defaults are used), a background job queue (the
pipeline runs synchronously inside the HTTP request), public/unauthenticated
Cloud Run access, accounts or login.

See [`docs/architecture.md`](docs/architecture.md) for the full rationale
behind every one of these boundaries.
