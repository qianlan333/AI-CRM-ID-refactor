from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.frontend_compat.legacy_routes import ADMIN_NAV_GROUPS
from aicrm_next.main import create_app
from tools import check_next_admin_ui_data_parity as checker


def test_next_shell_context_returns_target_grouped_navigation(monkeypatch):
    client = _client(monkeypatch)

    payload = client.get("/api/admin/dashboard/shell-context").json()

    assert payload["ok"] is True
    assert [(group["title"], [item["label"] for item in group["items"]]) for group in payload["nav_groups"]] == checker.TARGET_NAV_GROUPS


def test_next_admin_base_shell_renders_grouped_sidebar_and_active_item(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/admin/automation-conversion")
    html = response.text

    assert response.status_code == 200
    for group_title, labels in checker.TARGET_NAV_GROUPS:
        assert group_title in html
        for label in labels:
            assert label in html
    assert 'class="admin-nav-link is-active"' in html
    assert ">自动化运营<" in html
    assert "User Ops" not in html
    assert "fixture adapter" not in html.lower()
    assert "partial adapter" not in html.lower()


def test_target_admin_pages_are_not_404(monkeypatch):
    client = _client(monkeypatch)

    for route in checker.ADMIN_PAGES:
        response = client.get(route, follow_redirects=False)
        assert response.status_code != 404, route


def test_navigation_definition_matches_screenshot_target():
    assert [(group["title"], [item["label"] for item in group["items"]]) for group in ADMIN_NAV_GROUPS] == checker.TARGET_NAV_GROUPS


def test_checker_returns_ok():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["nav_groups_ready"] is True
    assert result["admin_pages_ready"] is True
    assert result["production_data_ready"] is True
    assert result["fixture_markers"] == []
    assert result["route_404_blockers"] == []


def test_checker_does_not_require_reenabling_disabled_timers():
    result = checker.run_check()

    assert any("timers are intentionally not enabled" in warning for warning in result["warnings"])
    assert result["safe_to_continue_automation_job_recovery"] is True


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "next-admin-ui-data-parity-test")
    return TestClient(create_app())
