from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client(tmp_path, monkeypatch) -> TestClient:
    """A TestClient wired against an isolated temp storage dir per test."""
    monkeypatch.setenv("STRATA_LOCAL_STORAGE_DIR", str(tmp_path))
    from app.core.config import get_settings

    get_settings.cache_clear()

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client

    get_settings.cache_clear()
