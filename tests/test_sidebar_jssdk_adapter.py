from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.integration_gateway.wecom_jssdk_adapter import (
    build_sidebar_jssdk_config,
    list_sidebar_jssdk_attempts,
    normalize_jssdk_url,
    reset_sidebar_jssdk_attempts,
)
from aicrm_next.main import create_app


def test_fake_adapter_response_matches_frontend_contract(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("WECOM_CORP_ID", "ww-test")
    monkeypatch.setenv("WECOM_AGENT_ID", "1000002")
    reset_sidebar_jssdk_attempts()

    payload = build_sidebar_jssdk_config(url="http://127.0.0.1:5001/sidebar/bind-mobile", debug=True)

    assert payload["ok"] is True
    assert payload["corp_id"] == "ww-test"
    assert payload["appId"] == "ww-test"
    assert payload["agent_id"] == "1000002"
    assert payload["config"]["url"] == "http://127.0.0.1:5001/sidebar/bind-mobile"
    assert payload["config"]["nonceStr"]
    assert payload["config"]["signature"]
    assert payload["agent_config"]["signature"]
    assert payload["jsApiList"] == ["getContext", "getCurExternalContact", "sendChatMessage"]
    assert payload["source_status"] == "next_jssdk_adapter"
    assert payload["adapter_mode"] == "fake"
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False
    assert payload["real_external_call_executed"] is False
    assert list_sidebar_jssdk_attempts()[0]["event_type"] == "sidebar.jssdk.planned"


def test_production_default_is_real_blocked_without_real_call(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("AICRM_SIDEBAR_JSSDK_ADAPTER_MODE", raising=False)
    monkeypatch.delenv("AICRM_SIDEBAR_JSSDK_REAL_ENABLED", raising=False)
    reset_sidebar_jssdk_attempts()

    payload = build_sidebar_jssdk_config(url="/sidebar/bind-mobile")

    assert payload["adapter_mode"] == "real_blocked"
    assert payload["config"]["url"] == "http://localhost/sidebar/bind-mobile"
    assert payload["external_call_blocked"] is True
    assert payload["real_external_call_executed"] is False
    assert list_sidebar_jssdk_attempts()[0]["event_type"] == "sidebar.jssdk.blocked"


def test_jssdk_api_get_head_and_options_are_next_owned(monkeypatch) -> None:
    monkeypatch.setenv("SECRET_KEY", "sidebar-jssdk-api")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    client = TestClient(create_app(), raise_server_exceptions=False)

    get_response = client.get("/api/sidebar/jssdk-config", params={"url": "http://127.0.0.1:5001/sidebar/bind-mobile"})
    options_response = client.options("/api/sidebar/jssdk-config")
    head_response = client.head("/api/sidebar/jssdk-config", params={"url": "http://127.0.0.1:5001/sidebar/bind-mobile"})

    assert get_response.status_code == 200
    assert get_response.json()["source_status"] == "next_jssdk_adapter"
    assert get_response.json()["fallback_used"] is False
    assert "X-AICRM-Compatibility-Facade" not in get_response.headers
    assert options_response.status_code == 200
    assert options_response.json()["source_status"] == "next_jssdk_adapter"
    assert "X-AICRM-Compatibility-Facade" not in options_response.headers
    assert head_response.status_code == 204
    assert "X-AICRM-Compatibility-Facade" not in head_response.headers


def test_jssdk_url_validation_accepts_relative_and_rejects_non_http() -> None:
    assert normalize_jssdk_url("/sidebar/bind-mobile") == "http://localhost/sidebar/bind-mobile"

    try:
        normalize_jssdk_url("javascript:alert(1)")
    except ValueError as exc:
        assert "http(s)" in str(exc)
    else:
        raise AssertionError("expected invalid URL to fail")
