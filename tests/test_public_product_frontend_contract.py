from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.setenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("SECRET_KEY", "public-product-frontend-contract-test")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_public_product_frontend_contains_detail_images_only_and_wechat_pay_cta(monkeypatch) -> None:
    product = _client(monkeypatch).get("/p/test-product")
    pay = _client(monkeypatch).get("/pay/test-product")

    assert 'data-route-owner="ai_crm_next"' in product.text
    assert 'data-fallback-used="false"' in product.text
    assert 'class="sticky-buy"' in product.text
    assert "/pay/test-product" in product.text
    assert 'class="hero-panel"' not in product.text
    assert 'class="detail-card"' not in product.text
    assert "当前页面只展示商品信息" not in product.text

    assert 'data-route-owner="ai_crm_next"' in pay.text
    assert "确认报名信息" in pay.text
    assert "/api/h5/wechat-pay/jsapi/orders" in pay.text
    assert "WeixinJSBridge.invoke" in pay.text
    assert "支付暂不可用" not in pay.text
    assert "不会创建订单" not in pay.text


def test_public_product_frontend_restores_slice_image_layout() -> None:
    from aicrm_next.public_product.service import render_product_page

    html = render_product_page(
        {
            "product_code": "subscription_trial_month",
            "title": "黄小璨首月体验",
            "description": "首月体验商品",
            "price_cents": 990,
            "currency": "CNY",
            "enabled": True,
            "slices": [
                {
                    "image_library_id": 1,
                    "image_url": "data:image/png;base64,YWFhYWFh",
                    "sort_order": 1,
                }
            ],
            "detail_sections": [{"title": "服务说明", "body": "体验权益说明"}],
            "buy_button_text": "立即报名",
        }
    )

    assert 'class="detail-media"' in html
    assert 'class="slice-img"' in html
    assert "data:image/png;base64,YWFhYWFh" in html
    assert '<section class="hero-panel">' not in html
    assert 'class="detail-card"' not in html
    assert 'class="sticky-buy"' in html
    assert "立即报名" in html
