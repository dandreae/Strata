from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.deps import get_slicer_service
from app.models.slicer import SliceResult
from tests.fakes import FakeSlicerService

VALID_STL = b"solid cube\n" + b"facet normal 0 0 0\n" * 5 + b"endsolid cube\n"


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


def _override_slicer(client: TestClient, result: SliceResult | None = None, raise_unavailable: bool = False) -> None:
    fake = FakeSlicerService(result=result, raise_unavailable=raise_unavailable)
    client.app.dependency_overrides[get_slicer_service] = lambda: fake


def test_create_run_slices_and_returns_real_metrics(client: TestClient) -> None:
    _override_slicer(
        client,
        result=SliceResult(success=True, print_time_seconds=8700, filament_grams=61.43, gcode_path=None),
    )

    response = client.post(
        "/api/v1/runs",
        data=_form_fields(),
        files={"file": ("bracket.stl", VALID_STL, "application/octet-stream")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "bracket.stl"
    assert body["status"] == "completed"
    assert body["model_reference"] is not None

    assert len(body["candidates"]) == 1
    candidate = body["candidates"][0]
    assert candidate["status"] == "succeeded"
    assert candidate["print_time_seconds"] == 8700
    assert candidate["filament_grams"] == 61.43
    assert candidate["layer_height"] == 0.20
    assert candidate["infill_percent"] == 20
    assert candidate["perimeter_count"] == 2
    assert candidate["supports_enabled"] is False

    assert len(body["decisions"]) == 1
    decision = body["decisions"][0]
    assert decision["selected_action"] == "accept_candidate"
    assert decision["requires_human"] is False


def test_create_run_rejects_candidate_that_violates_constraints(client: TestClient) -> None:
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
    assert body["status"] == "completed"
    assert body["decisions"][0]["selected_action"] == "reject_candidate"


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
    assert body["candidates"][0]["status"] == "failed"
    assert body["decisions"][0]["selected_action"] == "abort_run"


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
    assert len(body["candidates"]) == 1
    assert len(body["decisions"]) == 1


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
