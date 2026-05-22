from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_next_production_cutover_readiness as cutover_checker
from tools import check_next_production_runtime_gaps as gap_checker

ROOT = Path(__file__).resolve().parents[1]


def test_health_degrades_when_production_uses_fixture(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["runtime_owner"] == "ai_crm_next"
    assert payload["database_mode"] == "fixture"
    assert payload["fixture_mode"] is True
    assert payload["production_data_ready"] is False
    assert payload["ok"] is False
    assert payload["status"] == "degraded"


def test_health_reports_postgres_when_database_url_is_real(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["database_mode"] == "postgres"
    assert payload["fixture_mode"] is False
    assert payload["production_data_ready"] is True
    assert payload["runtime_owner"] == "ai_crm_next"


def test_next_production_facade_catches_legacy_routes_without_404(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    client = TestClient(create_app())

    for path in [
        "/admin/customers",
        "/api/customers",
        "/api/admin/questionnaires",
        "/api/h5/wechat-pay/jsapi/orders",
        "/wecom/external-contact/callback",
    ]:
        response = client.get(path) if path.startswith("/admin") or path == "/api/customers" or "questionnaires" in path else client.post(path, json={})
        assert response.status_code != 404
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_runtime_gap_checker_returns_ok():
    result = gap_checker.run_check()

    assert result["ok"] is True
    assert result["database_mode"] == "postgres"
    assert result["route_404_blockers"] == []
    assert result["callback_currently_has_5013_fallback"] is True


def test_cutover_checker_contract():
    result = cutover_checker.run_check()

    assert result["ok"] is True
    assert result["database_mode"] == "postgres"
    assert result["fixture_in_production"] is False
    assert result["route_404_blockers"] == []
    assert result["callback_ready"] is True
    assert result["timer_routes_ready"] is True
    assert result["payment_routes_ready"] is True
    assert result["oauth_routes_ready"] is True
    assert result["safe_to_enable_timers"] is True
    assert result["safe_to_remove_5013_callback_fallback"] is False


def test_required_docs_exist_and_avoid_forbidden_status_markers():
    docs = [
        ROOT / "docs/next_production_route_compatibility_matrix.md",
        ROOT / "docs/next_production_gap_closure_report.md",
        ROOT / "docs/next_production_cutover_runbook.md",
    ]
    for path in docs:
        assert path.exists()
    content = "\n".join(path.read_text() for path in docs)
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content


def test_production_config_not_modified():
    assert gap_checker.production_config_modified() is False
