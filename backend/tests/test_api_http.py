from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Iterator

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from forge.config.settings import Settings, get_settings


@pytest.fixture()
def api_app(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Iterator[FastAPI]:
    monkeypatch.setenv("FORGE_ENV", "local")
    monkeypatch.setenv("FORGE_MODEL_PROVIDER", "TEST_STUB")
    monkeypatch.setenv("FORGE_STORE_BACKEND", "local")
    monkeypatch.setenv("FORGE_EVENT_BUS", "inprocess")
    monkeypatch.setenv("FORGE_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("FORGE_WEB_ORIGIN", "https://forge-web.example.run.app")

    get_settings.cache_clear()
    sys.modules.pop("forge.api.main", None)
    module = importlib.import_module("forge.api.main")
    try:
        yield module.app
    finally:
        sys.modules.pop("forge.api.main", None)
        get_settings.cache_clear()


def test_settings_adds_deployed_web_origin_to_cors() -> None:
    settings = Settings(FORGE_WEB_ORIGIN="https://forge-web.example.run.app/")
    assert "http://localhost:5173" in settings.cors_allow_origins
    assert "https://forge-web.example.run.app" in settings.cors_allow_origins


def test_health_response_is_json(api_app: FastAPI) -> None:
    response = TestClient(api_app).get("/health")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {"status": "ok"}


def test_ready_response_is_json(api_app: FastAPI) -> None:
    response = TestClient(api_app).get("/ready")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["status"] == "ready"


def test_cors_allows_configured_web_origin(api_app: FastAPI) -> None:
    origin = "https://forge-web.example.run.app"
    response = TestClient(api_app).options(
        "/api/admin/setup/status",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "x-admin-pin,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin


def test_cors_rejects_unconfigured_origin(api_app: FastAPI) -> None:
    response = TestClient(api_app).options(
        "/api/system/info",
        headers={
            "Origin": "https://example.invalid",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
