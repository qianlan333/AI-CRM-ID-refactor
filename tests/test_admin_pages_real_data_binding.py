from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app
from tools import check_admin_pages_real_data_binding as checker


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "admin-pages-real-data-binding-test")
    return TestClient(create_app())


def test_admin_pages_do_not_render_forbidden_state_markers(monkeypatch):
    client = _client(monkeypatch)

    for route in checker.ADMIN_PAGES:
        response = client.get(route, follow_redirects=False)
        assert response.status_code != 404, route
        assert checker._bad_marker_hits(route, response.text) == []


def test_key_admin_pages_render_server_side_rows_or_stats(monkeypatch):
    client = _client(monkeypatch)

    for route in [
        "/admin/cloud-orchestrator",
        "/admin/user-ops",
        "/admin/wechat-pay/products",
        "/admin/wechat-pay/transactions",
        "/admin/image-library",
        "/admin/miniprogram-library",
        "/admin/attachment-library",
        "/admin/jobs",
        "/admin/config",
        "/admin/api-docs",
    ]:
        response = client.get(route)
        has_real_data, row_count = checker._has_real_data(route, response.text)
        assert has_real_data, (route, row_count)


def test_customer_page_does_not_render_sample_fixture_names(monkeypatch):
    response = _client(monkeypatch).get("/admin/customers")

    assert response.status_code == 200
    for marker in checker.SAMPLE_CUSTOMERS:
        assert marker not in response.text


def test_customer_page_uses_production_facade_when_database_ready(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)

    def fake_list_customers(query):
        return {
            "customers": [
                {
                    "external_userid": "real_ext_001",
                    "customer_name": "真实客户甲",
                    "owner_display_name": "真实负责人",
                    "owner_userid": "owner_real",
                    "mobile": "138****0000",
                }
            ],
            "total": 23709,
        }

    monkeypatch.setattr(legacy_routes, "list_customers_via_legacy", fake_list_customers)

    response = _client(monkeypatch).get("/admin/customers")

    assert response.status_code == 200
    assert "共 23709 位客户" in response.text
    assert "真实客户甲" in response.text
    assert "张小蓝" not in response.text


def test_questionnaire_page_uses_production_facade_when_database_ready(monkeypatch):
    import aicrm_next.frontend_compat.legacy_routes as legacy_routes

    monkeypatch.setattr(legacy_routes, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        legacy_routes,
        "list_questionnaires_from_legacy",
        lambda limit, offset: {
            "ok": True,
            "questionnaires": [
                {
                    "id": 101,
                    "slug": "real-questionnaire",
                    "title": "真实生产问卷",
                    "name": "真实生产问卷",
                    "enabled": True,
                    "is_disabled": False,
                    "created_at": "2026-05-01T00:00:00Z",
                    "updated_at": "2026-05-22T00:00:00Z",
                    "submission_count": 1171,
                    "assessment_enabled": False,
                    "public_path": "/s/real-questionnaire",
                }
            ],
            "total": 7,
            "source_status": "production_postgres",
        },
    )

    response = _client(monkeypatch).get("/admin/questionnaires")

    assert response.status_code == 200
    assert "real-questionnaire" in response.text
    assert "1171" in response.text
    assert "hxc-activation-v1" not in response.text
    assert "disabled-demo" not in response.text


def test_real_data_binding_checker_returns_ok():
    result = checker.run_check()

    assert result["ok"] is True
    assert result["bad_marker_hits"] == []
    assert result["auth_failures"] == []
    assert result["placeholder_pages"] == []
    assert result["empty_data_pages"] == []
    assert result["data_blockers"] == []
    assert result["production_config_modified"] is False


def test_api_docs_page_lists_real_route_groups(monkeypatch):
    response = _client(monkeypatch).get("/admin/api-docs")

    assert response.status_code == 200
    assert "/api/admin/automation-conversion/jobs/run-due" in response.text
    assert "/api/h5/wechat-pay/notify" in response.text
    assert checker._row_count(response.text) >= 10


def test_jobs_page_mentions_scheduled_safe_mode_without_disabled_timer_copy(monkeypatch):
    response = _client(monkeypatch).get("/admin/jobs")

    assert response.status_code == 200
    assert "scheduled_safe_mode" in response.text
    assert "disabled timers" not in response.text.lower()
