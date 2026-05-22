from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_next_timer_route_readiness as checker

ROOT = Path(__file__).resolve().parents[1]


def test_timer_routes_are_next_owned_and_guarded(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    client = TestClient(create_app())

    for route in checker.TIMER_ROUTES:
        unauth = client.post(route, json={}, follow_redirects=False)
        auth = client.post(route, json={}, headers={"Authorization": "Bearer probe-token"}, follow_redirects=False)
        assert unauth.status_code == 401
        assert auth.status_code != 404
        assert unauth.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_timer_readiness_checker_returns_ok():
    result = checker.run_check()

    assert result["safe_to_enable_timers"] is False
    assert "automation_production_data_not_ready" in result["blockers"]


def test_timer_readiness_safe_only_after_automation_data_ready(monkeypatch):
    monkeypatch.setattr(
        checker,
        "timer_probe_env",
        lambda: _NoopContext(),
    )

    class FakeResponse:
        def __init__(self, status_code, payload=None):
            self.status_code = status_code
            self._payload = payload or {}

        def json(self):
            return dict(self._payload)

    class FakeClient:
        def post(self, route, json=None, headers=None, follow_redirects=False):
            if headers:
                return FakeResponse(200)
            return FakeResponse(401)

        def get(self, route, follow_redirects=False):
            return FakeResponse(
                200,
                {
                    "ok": True,
                    "generated_at": "2026-05-22T00:00:00Z",
                    "status": "live",
                    "source_status": "production_postgres",
                },
            )

    monkeypatch.setattr(checker, "_client", lambda: FakeClient())

    result = checker.run_check()

    assert result["ok"] is True
    assert result["safe_to_enable_timers"] is True
    assert result["automation_production_data_ready"] is True
    assert result["blockers"] == []


class _NoopContext:
    def __enter__(self):
        return None

    def __exit__(self, *args):
        return False


def test_timer_readiness_docs_do_not_use_forbidden_status_markers():
    docs = [
        ROOT / "docs/next_production_route_compatibility_matrix.md",
        ROOT / "docs/next_production_gap_closure_report.md",
        ROOT / "docs/next_production_cutover_runbook.md",
    ]
    content = "\n".join(path.read_text() for path in docs)
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content
