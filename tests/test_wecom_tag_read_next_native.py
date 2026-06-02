from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _clear_runtime_env(monkeypatch) -> None:
    for key in [
        "AICRM_NEXT_ENV",
        "ENVIRONMENT",
        "APP_ENV",
        "FLASK_ENV",
        "DATABASE_URL",
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE",
        "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE",
    ]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("SECRET_KEY", "wecom-tag-read-next-native-test")


def test_wecom_tag_read_routes_return_next_catalog_shape(monkeypatch) -> None:
    _clear_runtime_env(monkeypatch)

    client = TestClient(create_app())
    response = client.get("/api/admin/wecom/tags")
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert payload["source_status"] == "local_contract_probe"
    assert payload["read_model_status"] == "fixture"
    assert payload["count"] == len(payload["items"]) == len(payload["tags"])
    assert payload["total_tags"] == len(payload["tags"])
    assert payload["groups"][0]["tags"][0]["tag_id"] == "tag_fixture_active"


def test_wecom_tag_groups_route_returns_group_items_from_same_catalog(monkeypatch) -> None:
    _clear_runtime_env(monkeypatch)

    response = TestClient(create_app()).get("/api/admin/wecom/tag-groups")
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["items"] == payload["groups"]
    assert payload["count"] == len(payload["groups"])
    assert payload["groups"][0]["group_id"] == "group_fixture_lifecycle"
