from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _production_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "next-sidebar-compat-test")
    return TestClient(create_app())


def test_next_forwards_sidebar_bind_mobile_page_to_legacy_facade(monkeypatch):
    client = _production_client(monkeypatch)

    response = client.get("/sidebar/bind-mobile")
    html = response.text

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert "Not Found" not in html
    assert "客户档案绑定" in html
    assert "/api/sidebar/contact-binding-status" in html
    assert "/api/sidebar/bind-mobile" in html
    assert "/api/admin/automation-conversion/member" in html


def test_next_forwards_sidebar_read_apis_without_404(monkeypatch):
    client = _production_client(monkeypatch)

    status_response = client.get("/api/sidebar/contact-binding-status")
    jssdk_response = client.get("/api/sidebar/jssdk-config")

    assert status_response.status_code == 400
    assert status_response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert status_response.json()["error"] == "external_userid is required"
    assert jssdk_response.status_code == 400
    assert jssdk_response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert jssdk_response.json()["error"] == "url is required"


def test_next_forwards_sidebar_detail_dependencies_without_404(monkeypatch):
    client = _production_client(monkeypatch)

    member_response = client.get("/api/admin/automation-conversion/member")
    tags_response = client.get("/api/admin/customers/profile/tags")

    assert member_response.status_code == 400
    assert member_response.headers["X-AICRM-Compatibility-Facade"] == "legacy_automation_facade"
    assert member_response.json()["error"] == "external_contact_id or phone is required"
    assert tags_response.status_code == 400
    assert tags_response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert tags_response.json()["error"] == "external_userid is required"
