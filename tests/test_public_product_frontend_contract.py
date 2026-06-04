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
    assert 'id="leadQrModal"' in pay.text
    assert 'id="showLeadQrButton"' in pay.text
    assert "leadQrFromOrder" in pay.text
    assert "showLeadQr(order" in pay.text
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


def test_public_h5_order_payload_adds_lead_qr_only_after_paid() -> None:
    from aicrm_next.public_product.h5_wechat_pay import _order_payload

    row = {
        "out_trade_no": "WXP_PAID",
        "product_code": "subscription_trial_month",
        "product_name": "黄小璨首月体验",
        "amount_total": 990,
        "currency": "CNY",
        "status": "paid",
        "trade_state": "SUCCESS",
    }

    payload = _order_payload(
        row,
        completion_redirect={
            "completion_redirect_enabled": False,
            "completion_redirect_url": "",
            "completion_redirect": {"enabled": False, "url": ""},
            "completion_action": {"type": "default", "redirect_url": ""},
        },
        lead_qr={"channel_id": 7, "channel_name": "首月体验", "qr_url": "https://example.com/lead.png", "status": "active"},
    )

    assert payload["completion_action"] == {"type": "lead_qr", "redirect_url": ""}
    assert payload["lead_qr"]["qr_url"] == "https://example.com/lead.png"


def test_public_h5_order_payload_hides_lead_qr_before_paid_or_when_redirecting() -> None:
    from aicrm_next.public_product.h5_wechat_pay import _order_payload

    base_row = {
        "out_trade_no": "WXP_UNPAID",
        "product_code": "subscription_trial_month",
        "product_name": "黄小璨首月体验",
        "amount_total": 990,
        "currency": "CNY",
        "status": "paying",
        "trade_state": "",
    }
    lead_qr = {"channel_id": 7, "channel_name": "首月体验", "qr_url": "https://example.com/lead.png", "status": "active"}

    unpaid = _order_payload(base_row, lead_qr=lead_qr)
    assert "lead_qr" not in unpaid

    redirecting = _order_payload(
        {**base_row, "status": "paid", "trade_state": "SUCCESS"},
        completion_redirect={
            "completion_redirect_enabled": True,
            "completion_redirect_url": "/welcome",
            "completion_redirect": {"enabled": True, "url": "/welcome"},
            "completion_action": {"type": "redirect", "redirect_url": "/welcome"},
        },
        lead_qr=lead_qr,
    )
    assert redirecting["completion_action"] == {"type": "redirect", "redirect_url": "/welcome"}
    assert "lead_qr" not in redirecting
