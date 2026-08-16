from __future__ import annotations

from fastapi.testclient import TestClient


def _sample_payload() -> dict:
    return {
        "filename": "bracket.stl",
        "production_quantity": 500,
        "printer_profile": "prusa_mk4_pla",
        "hard_constraints": {
            "max_print_time_seconds": 10800,
            "max_filament_grams": 80,
        },
        "optimization_preferences": {"objective": "minimize_material"},
    }


def test_create_run_returns_persisted_run(client: TestClient) -> None:
    response = client.post("/api/v1/runs", json=_sample_payload())
    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "bracket.stl"
    assert body["status"] == "pending"
    assert body["hard_constraints"]["max_filament_grams"] == 80


def test_get_run_roundtrips(client: TestClient) -> None:
    created = client.post("/api/v1/runs", json=_sample_payload()).json()
    response = client.get(f"/api/v1/runs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_run_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/runs/does-not-exist")
    assert response.status_code == 404


def test_list_runs_includes_created(client: TestClient) -> None:
    created = client.post("/api/v1/runs", json=_sample_payload()).json()
    response = client.get("/api/v1/runs")
    assert response.status_code == 200
    ids = [r["id"] for r in response.json()["runs"]]
    assert created["id"] in ids


def test_create_run_rejects_invalid_quantity(client: TestClient) -> None:
    payload = _sample_payload()
    payload["production_quantity"] = 0
    response = client.post("/api/v1/runs", json=payload)
    assert response.status_code == 422
