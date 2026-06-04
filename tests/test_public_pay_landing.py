from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "public-pay-landing-test")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_public_pay_landing_renders_blocked_payment_state(monkeypatch) -> None:
    response = _client(monkeypatch).get("/pay/test-product")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert response.headers["X-AICRM-Fallback-Used"] == "false"
    assert response.headers["X-AICRM-Payment-Request-Executed"] == "false"
    assert response.headers["X-AICRM-Order-Create-Executed"] == "false"
    assert "测试商品" in response.text
    assert "支付/下单动作已受控阻断" in response.text
    assert "disabled" in response.text
    assert "/p/test-product" in response.text


def test_public_pay_landing_unknown_path_is_controlled_404(monkeypatch) -> None:
    response = _client(monkeypatch).get("/pay/unknown-path-for-smoke")

    assert response.status_code == 404
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "商品不存在" in response.text


def test_public_pay_landing_options_is_next_owned(monkeypatch) -> None:
    response = _client(monkeypatch).options("/pay/test-product")

    assert response.status_code == 200
    assert response.json()["route_owner"] == "ai_crm_next"
    assert response.json()["payment_request_executed"] is False
