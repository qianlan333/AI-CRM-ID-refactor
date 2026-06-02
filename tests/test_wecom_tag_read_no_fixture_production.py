from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def test_wecom_tag_read_returns_controlled_unavailable_without_production_projection(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-read-production-unavailable-test")

    client = TestClient(create_app(), raise_server_exceptions=False)
    for path in ["/api/admin/wecom/tags", "/api/admin/wecom/tag-groups"]:
        response = client.get(path)
        payload = response.json()

        assert response.status_code == 503
        assert payload["ok"] is False
        assert payload["degraded"] is True
        assert payload["error_code"] == "production_unavailable"
        assert payload["source_status"] == "production_unavailable"
        assert payload["read_model_status"] == "unavailable"
        assert payload["route_owner"] == "ai_crm_next"
        assert payload["fallback_used"] is False
        assert payload["real_external_call_executed"] is False
        assert payload["items"] == []
        assert "X-AICRM-Compatibility-Facade" not in response.headers
