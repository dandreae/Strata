from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient wired against an isolated temp storage dir per test.

    Forces STRATA_PLANNER_MODE=deterministic regardless of the developer's
    local backend/.env — tests must never depend on (or be broken by) what
    planner mode/credentials happen to be configured outside the test
    process. A real, historical bug: before this override existed, a
    developer with STRATA_PLANNER_MODE=gemini set locally would cause
    `pytest -q` to make real, unintended, billable Gemini API calls on
    every run of the full suite. Tests that specifically want the real
    Gemini boundary use their own explicit mocks (test_gemini_planner.py)
    or the separately-marked, explicitly-invoked test_gemini_smoke.py.
    """
    monkeypatch.setenv("STRATA_LOCAL_STORAGE_DIR", str(tmp_path))
    monkeypatch.setenv("STRATA_PLANNER_MODE", "deterministic")
    from app.core.config import get_settings

    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
