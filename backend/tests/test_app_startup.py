from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import create_app


def test_app_starts_and_exposes_docs(client: TestClient) -> None:
    response = client.get("/openapi.json")
    assert response.status_code == 200


def test_create_app_is_idempotent() -> None:
    app1 = create_app()
    app2 = create_app()
    assert app1 is not app2  # each call builds a fresh app instance
    assert app1.title == app2.title
