/**
 * Demo/dev fixture data — used only when demo mode is on (see demoMode.ts).
 *
 * Two of these are REAL: captured verbatim from actual, successful
 * end-to-end runs (real Gemini + Google ADK calls, real PrusaSlicer
 * execution) during this project's own verification passes — one against
 * the deployed Cloud Run service, one against the local Docker container.
 * Nothing in them is generated or edited; they're the literal JSON bodies
 * `POST /api/v1/runs` returned. `isReal: true` marks these two.
 *
 * The rest are SYNTHETIC: hand-authored, schema-accurate RunDetail objects
 * used only to exercise error/edge-case UI states (infeasible run, Round 2
 * unavailable, slicer failure, human-input-needed tradeoff) that aren't
 * captured from a real run in this project's history. `isReal: false`.
 * These must never be described anywhere as a real optimization result —
 * the UI always renders a visible "SYNTHETIC FIXTURE" tag for them, and a
 * (less alarming) "DEMO FIXTURE — captured real run" tag for the real ones.
 *
 * This file is dev/demo tooling only. It is never imported by anything on
 * the real-backend request path (see lib/api.ts, App.tsx).
 */

import type { RunDetail } from "./api";
import cloudRunAdaptiveSuccess from "../fixtures/cloud-run-adaptive-success.json";
import localDeterministicSuccess from "../fixtures/local-deterministic-success.json";

export interface FixtureScenario {
  key: string;
  label: string;
  description: string;
  isReal: boolean;
  data: RunDetail;
}

const ADAPTIVE_SUCCESS: FixtureScenario = {
  key: "adaptive-gemini-success",
  label: "Gemini adaptive success (2 rounds)",
  description:
    "Real response captured from the deployed Cloud Run service, 2026-08-19. " +
    "Gemini + ADK proposed 8 Round 1 candidates, evaluated the measured results, " +
    "and proposed 4 targeted Round 2 candidates. All 12 sliced by real PrusaSlicer.",
  isReal: true,
  data: cloudRunAdaptiveSuccess as RunDetail,
};

const DETERMINISTIC_SUCCESS: FixtureScenario = {
  key: "deterministic-single-round",
  label: "Deterministic planner success (1 round)",
  description:
    "Real response captured from the local Docker container, 2026-08-19, running the " +
    "fixed-set deterministic planner (no Gemini calls) — the offline/free code path.",
  isReal: true,
  data: localDeterministicSuccess as RunDetail,
};

const NOW = "2026-08-19T20:00:00Z";

function baseRun(overrides: Partial<RunDetail>): RunDetail {
  return {
    id: "fixture-synthetic-run",
    filename: "bracket.stl",
    model_reference: "runs/fixture-synthetic-run/uploads/bracket.stl",
    status: "completed",
    production_quantity: 250,
    printer_profile: "generic_pla",
    hard_constraints: { max_print_time_seconds: 10800, max_filament_grams: 80 },
    optimization_preferences: { objective: "minimize_material" },
    created_at: NOW,
    updated_at: NOW,
    candidates: [],
    decisions: [],
    optimization_summary: { candidates_tested: 0, succeeded: 0, feasible: 0, pareto_optimal: 0 },
    ...overrides,
  };
}

/** Round 1 succeeded normally; Round 2 planning itself failed (e.g. Gemini
 * call error) — the run still completes on Round 1's real results, exactly
 * as app/services/orchestrator.py::_round_two_unavailable_decision does. */
const ROUND_TWO_UNAVAILABLE: FixtureScenario = {
  key: "round-two-unavailable",
  label: "Round 2 unavailable (Round 1 still succeeded)",
  description:
    "SYNTHETIC — exercises the graceful-degradation path: Gemini's Round 1 proposals sliced " +
    "and evaluated normally, but the Round 2 planning call itself failed. The run still " +
    "completes and selects a winner from Round 1 alone, with the failure recorded plainly.",
  isReal: false,
  data: baseRun({
    id: "fixture-round-two-unavailable",
    candidates: [
      {
        id: "c1",
        round: 1,
        orientation_x: 0,
        orientation_y: 0,
        orientation_z: 0,
        layer_height: 0.2,
        infill_percent: 15,
        supports_enabled: false,
        perimeter_count: 3,
        status: "succeeded",
        print_time_seconds: 3120,
        filament_grams: 18.4,
        slicer_output_path: "runs/fixture-round-two-unavailable/candidates/c1.gcode",
        failure_reason: null,
        constraint_checks: [
          { key: "max_print_time_seconds", label: "Print time", passed: true, limit: 10800, actual: 3120, unit: "s" },
          { key: "max_filament_grams", label: "Material", passed: true, limit: 80, actual: 18.4, unit: "g" },
        ],
        is_feasible: true,
        is_pareto_optimal: true,
        is_selected: true,
      },
      {
        id: "c2",
        round: 1,
        orientation_x: 0,
        orientation_y: 0,
        orientation_z: 0,
        layer_height: 0.1,
        infill_percent: 30,
        supports_enabled: false,
        perimeter_count: 4,
        status: "succeeded",
        print_time_seconds: 5400,
        filament_grams: 24.9,
        slicer_output_path: "runs/fixture-round-two-unavailable/candidates/c2.gcode",
        failure_reason: null,
        constraint_checks: [
          { key: "max_print_time_seconds", label: "Print time", passed: true, limit: 10800, actual: 5400, unit: "s" },
          { key: "max_filament_grams", label: "Material", passed: true, limit: 80, actual: 24.9, unit: "g" },
        ],
        is_feasible: true,
        is_pareto_optimal: false,
        is_selected: false,
      },
    ],
    decisions: [
      {
        id: "d1",
        observation: "Planner 'gemini:gemini-3.5-flash' proposed 2 candidate(s) for the first experiment round.",
        alternatives: [],
        evidence: ["Spanning a moderate-to-dense infill range to map the material/time trade-off."],
        selected_action: "plan_initial_candidates",
        confidence: null,
        outcome: "Spanning a moderate-to-dense infill range to map the material/time trade-off.",
        requires_human: false,
        timestamp: NOW,
      },
      {
        id: "d2",
        observation: "Round 2 planning failed; proceeding with Round 1 results only.",
        alternatives: [],
        evidence: ["Gemini call failed: 503 UNAVAILABLE — model overloaded, retry later."],
        selected_action: "round_two_unavailable",
        confidence: null,
        outcome: "Gemini call failed: 503 UNAVAILABLE — model overloaded, retry later.",
        requires_human: false,
        timestamp: NOW,
      },
      {
        id: "d3",
        observation: "2 configurations were evaluated across 1 round(s). 2 sliced successfully. 2 satisfied all hard constraints. 1 lie on the Pareto frontier.",
        alternatives: [],
        evidence: [
          "Selected lowest filament usage (minimize_material), print time as tie-breaker.",
          "Selected candidate print time: 3120s",
          "Selected candidate filament usage: 18.4g",
        ],
        selected_action: "select_candidate",
        confidence: null,
        outcome: "Selected round 1 / layer 0.2mm / infill 15% / 3 perimeters (preference: minimize_material).",
        requires_human: false,
        timestamp: NOW,
      },
    ],
    optimization_summary: { candidates_tested: 2, succeeded: 2, feasible: 2, pareto_optimal: 1 },
  }),
};

/** Every candidate sliced but none satisfied the user's hard constraints. */
const INFEASIBLE: FixtureScenario = {
  key: "infeasible",
  label: "No feasible candidate",
  description:
    "SYNTHETIC — every proposed configuration sliced successfully, but none satisfied the " +
    "user's hard constraints (constraints set too tight for this part).",
  isReal: false,
  data: baseRun({
    id: "fixture-infeasible",
    status: "infeasible",
    hard_constraints: { max_print_time_seconds: 600, max_filament_grams: 5 },
    candidates: [
      {
        id: "c1",
        round: 1,
        orientation_x: 0,
        orientation_y: 0,
        orientation_z: 0,
        layer_height: 0.2,
        infill_percent: 20,
        supports_enabled: false,
        perimeter_count: 3,
        status: "succeeded",
        print_time_seconds: 3120,
        filament_grams: 18.4,
        slicer_output_path: "runs/fixture-infeasible/candidates/c1.gcode",
        failure_reason: null,
        constraint_checks: [
          { key: "max_print_time_seconds", label: "Print time", passed: false, limit: 600, actual: 3120, unit: "s" },
          { key: "max_filament_grams", label: "Material", passed: false, limit: 5, actual: 18.4, unit: "g" },
        ],
        is_feasible: false,
        is_pareto_optimal: false,
        is_selected: false,
      },
    ],
    decisions: [
      {
        id: "d1",
        observation: "Planner 'deterministic' proposed 1 candidate(s) for the first experiment round.",
        alternatives: [],
        evidence: [],
        selected_action: "plan_initial_candidates",
        confidence: null,
        outcome: null,
        requires_human: false,
        timestamp: NOW,
      },
      {
        id: "d2",
        observation: "1 configurations were evaluated across 1 round(s). 1 sliced successfully. 0 satisfied all hard constraints.",
        alternatives: [],
        evidence: ["Candidate (round 1 / layer 0.2mm / infill 20% / 3 perimeters): print time 3120s > 600s limit; filament 18.4g > 5g limit"],
        selected_action: "no_feasible_candidate",
        confidence: null,
        outcome: "No candidate satisfied all hard constraints.",
        requires_human: false,
        timestamp: NOW,
      },
    ],
    optimization_summary: { candidates_tested: 1, succeeded: 1, feasible: 0, pareto_optimal: 0 },
  }),
};

/** PrusaSlicer itself was unavailable — every candidate failed technically. */
const SLICER_FAILURE: FixtureScenario = {
  key: "slicer-failure",
  label: "Backend/slicer failure",
  description: "SYNTHETIC — PrusaSlicer was unavailable in the runtime environment; the run aborts cleanly.",
  isReal: false,
  data: baseRun({
    id: "fixture-slicer-failure",
    status: "failed",
    candidates: [
      {
        id: "c1",
        round: 1,
        orientation_x: 0,
        orientation_y: 0,
        orientation_z: 0,
        layer_height: 0.2,
        infill_percent: 20,
        supports_enabled: false,
        perimeter_count: 3,
        status: "failed",
        print_time_seconds: null,
        filament_grams: null,
        slicer_output_path: null,
        failure_reason: "PrusaSlicer binary not found: 'prusa-slicer'. Install PrusaSlicer and/or set STRATA_PRUSASLICER_BINARY_PATH.",
        constraint_checks: [],
        is_feasible: false,
        is_pareto_optimal: false,
        is_selected: false,
      },
    ],
    decisions: [
      {
        id: "d1",
        observation: "Planner 'deterministic' proposed 1 candidate(s) for the first experiment round.",
        alternatives: [],
        evidence: [],
        selected_action: "plan_initial_candidates",
        confidence: null,
        outcome: null,
        requires_human: false,
        timestamp: NOW,
      },
      {
        id: "d2",
        observation: "PrusaSlicer is not available in this environment.",
        alternatives: [],
        evidence: ["PrusaSlicer binary not found: 'prusa-slicer'. Install PrusaSlicer and/or set STRATA_PRUSASLICER_BINARY_PATH."],
        selected_action: "abort_run",
        confidence: null,
        outcome: "PrusaSlicer binary not found: 'prusa-slicer'. Install PrusaSlicer and/or set STRATA_PRUSASLICER_BINARY_PATH.",
        requires_human: false,
        timestamp: NOW,
      },
    ],
    optimization_summary: { candidates_tested: 1, succeeded: 0, feasible: 0, pareto_optimal: 0 },
  }),
};

/** Multiple feasible, mutually non-dominated candidates under a "balanced"
 * objective — a genuine tradeoff the backend correctly refuses to guess at. */
const NEEDS_HUMAN_INPUT: FixtureScenario = {
  key: "needs-human-input",
  label: "Tradeoff needs human input",
  description:
    "SYNTHETIC — several Pareto-optimal candidates are mutually non-dominated under a " +
    "'balanced' objective; the backend escalates rather than guessing.",
  isReal: false,
  data: baseRun({
    id: "fixture-needs-human-input",
    status: "needs_human_input",
    optimization_preferences: { objective: "balanced" },
    candidates: [
      {
        id: "c1",
        round: 1,
        orientation_x: 0,
        orientation_y: 0,
        orientation_z: 0,
        layer_height: 0.3,
        infill_percent: 10,
        supports_enabled: false,
        perimeter_count: 2,
        status: "succeeded",
        print_time_seconds: 1800,
        filament_grams: 12.1,
        slicer_output_path: "runs/fixture-needs-human-input/candidates/c1.gcode",
        failure_reason: null,
        constraint_checks: [
          { key: "max_print_time_seconds", label: "Print time", passed: true, limit: 10800, actual: 1800, unit: "s" },
          { key: "max_filament_grams", label: "Material", passed: true, limit: 80, actual: 12.1, unit: "g" },
        ],
        is_feasible: true,
        is_pareto_optimal: true,
        is_selected: false,
      },
      {
        id: "c2",
        round: 1,
        orientation_x: 0,
        orientation_y: 0,
        orientation_z: 0,
        layer_height: 0.1,
        infill_percent: 8,
        supports_enabled: false,
        perimeter_count: 2,
        status: "succeeded",
        print_time_seconds: 3600,
        filament_grams: 10.2,
        slicer_output_path: "runs/fixture-needs-human-input/candidates/c2.gcode",
        failure_reason: null,
        constraint_checks: [
          { key: "max_print_time_seconds", label: "Print time", passed: true, limit: 10800, actual: 3600, unit: "s" },
          { key: "max_filament_grams", label: "Material", passed: true, limit: 80, actual: 10.2, unit: "g" },
        ],
        is_feasible: true,
        is_pareto_optimal: true,
        is_selected: false,
      },
    ],
    decisions: [
      {
        id: "d1",
        observation: "Planner 'deterministic' proposed 2 candidate(s) for the first experiment round.",
        alternatives: [],
        evidence: [],
        selected_action: "plan_initial_candidates",
        confidence: null,
        outcome: null,
        requires_human: false,
        timestamp: NOW,
      },
      {
        id: "d2",
        observation: "2 configurations were evaluated across 1 round(s). 2 sliced successfully. 2 satisfied all hard constraints. 2 lie on the Pareto frontier.",
        alternatives: ["round 1 / layer 0.3mm / infill 10% / 2 perimeters", "round 1 / layer 0.1mm / infill 8% / 2 perimeters"],
        evidence: ["2 feasible candidates are mutually non-dominated and objective 'balanced' does not resolve the tradeoff."],
        selected_action: "escalate_tradeoff",
        confidence: null,
        outcome: "Multiple equally good options — human input required to choose between time and material priority.",
        requires_human: true,
        timestamp: NOW,
      },
    ],
    optimization_summary: { candidates_tested: 2, succeeded: 2, feasible: 2, pareto_optimal: 2 },
  }),
};

export const FIXTURE_SCENARIOS: FixtureScenario[] = [
  ADAPTIVE_SUCCESS,
  DETERMINISTIC_SUCCESS,
  ROUND_TWO_UNAVAILABLE,
  INFEASIBLE,
  NEEDS_HUMAN_INPUT,
  SLICER_FAILURE,
];

export const DEFAULT_FIXTURE_KEY = ADAPTIVE_SUCCESS.key;

export function getFixture(key: string): FixtureScenario {
  return FIXTURE_SCENARIOS.find((s) => s.key === key) ?? ADAPTIVE_SUCCESS;
}
