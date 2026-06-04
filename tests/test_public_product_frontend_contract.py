from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "public-product-frontend-contract-test")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_public_product_frontend_contains_expected_display_and_blocked_cta(monkeypatch) -> None:
    product = _client(monkeypatch).get("/p/test-product")
    pay = _client(monkeypatch).get("/pay/test-product")

    assert 'data-route-owner="ai_crm_next"' in product.text
    assert 'data-fallback-used="false"' in product.text
    assert 'data-payment-request-executed="false"' in product.text
    assert 'data-order-create-executed="false"' in product.text
    assert "商品编码" in product.text
    assert "价格" in product.text
    assert "状态" in product.text
    assert "/pay/test-product" in product.text

    assert 'data-route-owner="ai_crm_next"' in pay.text
    assert "支付暂不可用" in pay.text
    assert "不会创建订单" in pay.text
    assert "不会调用微信支付或支付宝" in pay.text
