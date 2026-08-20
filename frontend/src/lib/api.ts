/**
 * Types and fetch wrapper for the Strata backend API.
 *
 * Mirrors backend/app/models/api.py exactly — this is the only place that
 * shape lives on the frontend. Every number below (print time, filament,
 * constraint pass/fail) originates from the backend; nothing here computes
 * or fabricates a manufacturing result.
 */

export const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export type Objective = "minimize_material" | "minimize_time" | "balanced";

export type RunStatus = "pending" | "running" | "completed" | "infeasible" | "needs_human_input" | "failed";

export type CandidateStatus = "pending" | "slicing" | "succeeded" | "failed";

export interface HardConstraints {
  max_print_time_seconds: number;
  max_filament_grams: number;
}

export interface ConstraintCheck {
  key: string;
  label: string;
  passed: boolean;
  limit: number;
  actual: number | null;
  unit: string;
}

export interface Candidate {
  id: string;
  round: number;
  orientation_x: number;
  orientation_y: number;
  orientation_z: number;
  layer_height: number;
  infill_percent: number;
  supports_enabled: boolean;
  perimeter_count: number;
  status: CandidateStatus;
  print_time_seconds: number | null;
  filament_grams: number | null;
  slicer_output_path: string | null;
  failure_reason: string | null;
  constraint_checks: ConstraintCheck[];
  is_feasible: boolean;
  is_pareto_optimal: boolean;
  is_selected: boolean;
}

export interface OptimizationSummary {
  candidates_tested: number;
  succeeded: number;
  feasible: number;
  pareto_optimal: number;
}

export interface Decision {
  id: string;
  observation: string;
  alternatives: string[];
  evidence: string[];
  selected_action: string;
  confidence: number | null;
  outcome: string | null;
  requires_human: boolean;
  timestamp: string;
}

export interface RunDetail {
  id: string;
  filename: string;
  model_reference: string | null;
  status: RunStatus;
  production_quantity: number;
  printer_profile: string;
  hard_constraints: HardConstraints;
  optimization_preferences: { objective: Objective };
  created_at: string;
  updated_at: string;
  candidates: Candidate[];
  decisions: Decision[];
  optimization_summary: OptimizationSummary;
}

export interface CreateRunParams {
  file: File;
  productionQuantity: number;
  printerProfile: string;
  maxPrintTimeSeconds: number;
  maxFilamentGrams: number;
  objective: Objective;
}

export class ApiError extends Error {
  details: string[];

  constructor(message: string, details: string[] = []) {
    super(message);
    this.details = details;
  }
}

/**
 * POST /api/v1/runs as real multipart/form-data — matches the backend's
 * FastAPI File()/Form() contract exactly. Do not switch this to JSON or
 * base64; the backend reads a genuine file upload.
 */
export async function createRun(params: CreateRunParams): Promise<RunDetail> {
  const body = new FormData();
  body.set("file", params.file, params.file.name);
  body.set("production_quantity", String(params.productionQuantity));
  body.set("printer_profile", params.printerProfile);
  body.set("max_print_time_seconds", String(params.maxPrintTimeSeconds));
  body.set("max_filament_grams", String(params.maxFilamentGrams));
  body.set("objective", params.objective);

  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}/api/v1/runs`, { method: "POST", body });
  } catch {
    throw new ApiError(`Could not reach the Strata backend at ${API_BASE_URL}.`);
  }

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    const message: string = payload?.message ?? `Request failed (HTTP ${response.status}).`;
    const details: string[] = payload?.details?.errors ?? [];
    throw new ApiError(message, details);
  }

  return (await response.json()) as RunDetail;
}
