from __future__ import annotations

from fastapi.testclient import TestClient

from app.agent.default_candidate import generate_candidate_set
from app.api.deps import get_slicer_service
from app.models.slicer import SliceResult
from tests.fakes import FakeSlicerService

VALID_STL = b"solid cube\n" + b"facet normal 0 0 0\n" * 5 + b"endsolid cube\n"

NUM_CANDIDATES = len(generate_candidate_set("probe"))


def _form_fields(**overrides) -> dict:
    defaults = dict(
        production_quantity="500",
        printer_profile="generic_pla",
        max_print_time_seconds="10800",
        max_filament_grams="80",
        objective="minimize_material",
    )
    defaults.update(overrides)
    return defaults


def _override_slicer(
    client: TestClient,
    result: SliceResult | None = None,
    results: list[SliceResult] | None = None,
    raise_unavailable: bool = False,
) -> None:
    fake = FakeSlicerService(result=result, results=results, raise_unavailable=raise_unavailable)
    client.app.dependency_overrides[get_slicer_service] = lambda: fake


def _varied_results(grams: list[float], times: list[int]) -> list[SliceResult]:
    return [
        SliceResult(success=True, print_time_seconds=t, filament_grams=g, gcode_path=None)
        for t, g in zip(times, grams)
    ]


_TERMINAL_ACTIONS = {"select_candidate", "no_feasible_candidate", "escalate_tradeoff", "abort_run"}


def _plan_decision(body: dict) -> dict:
    return next(d for d in body["decisions"] if d["selected_action"] == "plan_initial_candidates")


def _round_two_decision(body: dict) -> dict:
    return next(d for d in body["decisions"] if d["selected_action"] in ("stop_optimization", "continue_optimization"))


def _final_decision(body: dict) -> dict:
    return next(d for d in body["decisions"] if d["selected_action"] in _TERMINAL_ACTIONS)


def test_create_run_slices_candidate_set_and_selects_winner(client: TestClient) -> None:
    grams = [61.43, 55.0, 50.0, 70.0, 45.0, 79.9, 75.0, 62.0]
    times = [8700, 8000, 7500, 9000, 8200, 7000, 6800, 7200]
    _override_slicer(client, results=_varied_results(grams, times))

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(objective="minimize_material"),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "bracket.stl"
    assert body["status"] == "completed"
    assert body["model_reference"] is not None

    assert len(body["candidates"]) == NUM_CANDIDATES
    assert body["optimization_summary"]["candidates_tested"] == NUM_CANDIDATES
    assert body["optimization_summary"]["succeeded"] == NUM_CANDIDATES
    assert body["optimization_summary"]["feasible"] == NUM_CANDIDATES  # all within 10800s/80g
    assert body["optimization_summary"]["pareto_optimal"] >= 1
    # Deterministic mode never adapts, so every candidate is Round 1.
    assert all(c["round"] == 1 for c in body["candidates"])

    selected = [c for c in body["candidates"] if c["is_selected"]]
    assert len(selected) == 1
    assert selected[0]["filament_grams"] == 45.0  # the lowest, per minimize_material
    assert selected[0]["is_pareto_optimal"] is True
    assert selected[0]["is_feasible"] is True

    # 3 decisions: Round 1 plan, Round 2 stop (deterministic never adapts), final selection.
    assert len(body["decisions"]) == 3
    plan = _plan_decision(body)
    assert "deterministic" in plan["observation"]
    assert plan["requires_human"] is False

    round_two = _round_two_decision(body)
    assert round_two["selected_action"] == "stop_optimization"
    assert round_two["requires_human"] is False

    decision = _final_decision(body)
    assert decision["selected_action"] == "select_candidate"
    assert decision["requires_human"] is False
    assert "45.0g" in " ".join(decision["evidence"])


def test_create_run_reports_infeasible_when_no_candidate_satisfies_constraints(client: TestClient) -> None:
    # Every candidate gets the same result, which violates the tight material limit.
    _override_slicer(
        client,
        result=SliceResult(success=True, print_time_seconds=8700, filament_grams=61.43, gcode_path=None),
    )

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(max_filament_grams="10"),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "infeasible"
    assert body["optimization_summary"]["feasible"] == 0
    assert body["optimization_summary"]["pareto_optimal"] == 0
    assert not any(c["is_selected"] for c in body["candidates"])

    decision = _final_decision(body)
    assert decision["selected_action"] == "no_feasible_candidate"
    assert decision["requires_human"] is False

    checks = {c["key"]: c for c in body["candidates"][0]["constraint_checks"]}
    assert checks["max_filament_grams"]["passed"] is False
    assert checks["max_filament_grams"]["limit"] == 10.0


def test_create_run_handles_slicer_unavailable_without_500(client: TestClient) -> None:
    _override_slicer(client, raise_unavailable=True)

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["status"] == "failed"
    assert all(c["status"] == "failed" for c in body["candidates"])
    assert _final_decision(body)["selected_action"] == "abort_run"


def test_create_run_rejects_non_stl_file(client: TestClient) -> None:
    _override_slicer(client, result=SliceResult(success=True))

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(),
        files={"file": ("bracket.txt", b"not an stl", "text/plain")},
    )

    assert response.status_code == 422
    assert "errors" in response.json()["details"]


def test_create_run_rejects_empty_file(client: TestClient) -> None:
    _override_slicer(client, result=SliceResult(success=True))

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(),
        files={"file": ("bracket.stl", b"", "application/octet-stream")},
    )

    assert response.status_code == 422


def test_get_run_roundtrips_with_candidates_and_decisions(client: TestClient) -> None:
    _override_slicer(
        client,
        result=SliceResult(success=True, print_time_seconds=8700, filament_grams=61.43, gcode_path=None),
    )

    created = client.post(
        "/api/v1/runs",
        data=_form_fields(),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    ).json()

    response = client.get(f"/api/v1/runs/{created['id']}")
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == created["id"]
    assert len(body["candidates"]) == NUM_CANDIDATES
    assert len(body["decisions"]) == 3
    assert body["optimization_summary"]["candidates_tested"] == NUM_CANDIDATES


def test_get_missing_run_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/runs/does-not-exist")
    assert response.status_code == 404


def test_list_runs_includes_created(client: TestClient) -> None:
    _override_slicer(client, result=SliceResult(success=True, print_time_seconds=100, filament_grams=10))

    created = client.post(
        "/api/v1/runs",
        data=_form_fields(),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    ).json()

    response = client.get("/api/v1/runs")
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["runs"]]
    assert created["id"] in ids


def test_create_run_rejects_invalid_quantity(client: TestClient) -> None:
    _override_slicer(client, result=SliceResult(success=True))

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(production_quantity="0"),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    )
    assert response.status_code == 422
