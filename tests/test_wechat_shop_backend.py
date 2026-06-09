from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.commerce.repo import reset_commerce_fixture_state
from aicrm_next.commerce.wechat_shop_client import WeChatShopClient, WeChatShopClientError
from aicrm_next.commerce.wechat_shop_service import fixture_wechat_shop_order
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    reset_commerce_fixture_state()
    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("SECRET_KEY", "wechat-shop-backend")
    monkeypatch.setenv("WECHAT_SHOP_APPID", "wx_shop_test")
    monkeypatch.setenv("WECHAT_SHOP_APPSECRET", "shop-secret-value")
    monkeypatch.delenv("WECHAT_SHOP_CALLBACK_TOKEN", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _mock_order(
    monkeypatch,
    *,
    order_id: str,
    status: int = 20,
    pay_time: int = 1760000000,
    transaction_id: str = "shop_tx_001",
    finish_aftersale_sku_cnt: int = 0,
    deliver_method: int = 3,
) -> None:
    monkeypatch.setattr(WeChatShopClient, "get_stable_access_token", lambda self, force_refresh=False: {"access_token": "shop-access-token", "expires_in": 7200})

    def fake_get_order(self, requested_order_id: str, access_token: str) -> dict:
        assert requested_order_id == order_id
        return {
            "errcode": 0,
            "order": {
                "order_id": requested_order_id,
                "status": status,
                "update_time": 1760000300,
                "order_detail": {
                    "pay_info": {"pay_time": pay_time, "transaction_id": transaction_id, "pay_method": 1},
                    "price_info": {"order_price": 12900, "freight": 0},
                    "delivery_info": {
                        "deliver_method": deliver_method,
                        "recharge_info": {"account_no": "virtual-account-001", "account_type": "member_id"},
                    },
                    "product_infos": [
                        {
                            "title": "微信小店虚拟课程",
                            "sku_id": "sku_shop_001",
                            "sku_cnt": 1,
                            "finish_aftersale_sku_cnt": finish_aftersale_sku_cnt,
                        }
                    ],
                    "refund_info": {"refund_freight": 0},
                },
                "aftersale_detail": {"aftersale_order_list": []},
            },
        }

    monkeypatch.setattr(WeChatShopClient, "get_order", fake_get_order)


def test_wechat_shop_provider_is_accepted_by_unified_orders(monkeypatch) -> None:
    client = _client(monkeypatch)

    shop = client.get("/api/admin/orders?provider=wechat_shop").json()
    merged = client.get("/api/admin/orders?provider=all").json()

    assert shop["ok"] is True
    assert shop["providers"] == ["wechat_shop"]
    assert merged["ok"] is True
    assert merged["providers"] == ["wechat", "alipay", "wechat_shop"]


def test_wechat_shop_notify_records_large_order_id_as_string(monkeypatch) -> None:
    order_id = "370511505847120892812345678901"
    _mock_order(monkeypatch, order_id=order_id)
    client = _client(monkeypatch)

    response = client.post(
        "/api/wechat-shop/notify",
        json={
            "ToUserName": "gh_test",
            "FromUserName": "OPENID",
            "CreateTime": 1662480000,
            "MsgType": "event",
            "Event": "channels_ec_order_new",
            "order_info": {"order_id": int(order_id)},
        },
    )

    assert response.status_code == 200
    assert response.text == "success"
    events = client.get(f"/api/admin/wechat-shop/events?order_id={order_id}").json()
    assert events["events"][0]["order_id"] == order_id
    assert "e+" not in events["events"][0]["order_id"].lower()


def test_wechat_shop_paid_order_maps_to_unified_paid_status(monkeypatch) -> None:
    order_id = "3705115058471208928"
    _mock_order(monkeypatch, order_id=order_id, status=20, transaction_id="shop_tx_paid")
    client = _client(monkeypatch)

    sync = client.post(f"/api/admin/wechat-shop/orders/{order_id}/sync").json()
    detail = client.get(f"/api/admin/orders/{order_id}?provider=wechat_shop").json()

    assert sync["ok"] is True
    assert sync["provider"] == "wechat_shop"
    assert sync["provider_label"] == "微信小店"
    assert detail["order"]["status"] == "paid"
    assert detail["order"]["status_label"] in {"成交", "已支付"}
    assert detail["order"]["provider_label"] == "微信小店"
    assert detail["order"]["transaction_id"] == "shop_tx_paid"


def test_wechat_shop_returned_order_maps_to_refunded_without_refund_ability(monkeypatch) -> None:
    order_id = "3705115058471208999"
    _mock_order(monkeypatch, order_id=order_id, status=200, finish_aftersale_sku_cnt=1)
    client = _client(monkeypatch)

    client.post(f"/api/admin/wechat-shop/orders/{order_id}/sync")
    detail = client.get(f"/api/admin/orders/{order_id}?provider=wechat_shop").json()

    assert detail["order"]["returned_recorded"] is True
    assert detail["order"]["status"] in {"full_refunded", "partial_refunded"}
    assert detail["order"]["can_refund"] is False


def test_wechat_shop_virtual_delivery_is_recorded_without_delivery_api(monkeypatch) -> None:
    order_id = "3705115058471208777"
    _mock_order(monkeypatch, order_id=order_id, deliver_method=3)
    client = _client(monkeypatch)

    response = client.post(f"/api/admin/wechat-shop/orders/{order_id}/sync")
    saved = fixture_wechat_shop_order(order_id)

    assert response.status_code == 200
    assert saved is not None
    assert saved["is_virtual_delivery"] is True
    assert saved["virtual_account_no"] == "virtual-account-001"
    assert saved["virtual_account_type"] == "member_id"


def test_wechat_shop_manual_sync_error_is_structured_and_redacted(monkeypatch) -> None:
    order_id = "3705115058471208666"
    monkeypatch.setattr(WeChatShopClient, "get_stable_access_token", lambda self, force_refresh=False: {"access_token": "shop-access-token", "expires_in": 7200})

    def fail_get_order(self, requested_order_id: str, access_token: str) -> dict:
        raise WeChatShopClientError("bad access_token=shop-access-token shop-secret-value")

    monkeypatch.setattr(WeChatShopClient, "get_order", fail_get_order)
    client = _client(monkeypatch)

    response = client.post(f"/api/admin/wechat-shop/orders/{order_id}/sync")
    body = response.json()

    assert response.status_code == 400
    assert body["ok"] is False
    assert body["error_code"] == "wechat_shop_order_sync_failed"
    assert "shop-access-token" not in body["message"]
    assert "shop-secret-value" not in body["message"]


def test_wechat_shop_does_not_change_existing_refund_routes(monkeypatch) -> None:
    client = _client(monkeypatch)

    alipay_refund = client.post("/api/admin/refunds", json={"provider": "alipay", "order_no": "order_fake_0003"})
    wechat_shop_refund = client.post("/api/admin/refunds", json={"provider": "wechat_shop", "order_no": "3705115058471208928"})
    wechat_pay_refunds = client.get("/api/admin/wechat-pay/orders/1/refunds")

    assert alipay_refund.status_code == 400
    assert alipay_refund.json()["error_code"] == "provider_refund_not_supported"
    assert wechat_shop_refund.status_code == 400
    assert wechat_shop_refund.json()["error_code"] in {"invalid_refund_request", "provider_refund_not_supported"}
    assert wechat_pay_refunds.status_code == 410
    assert wechat_pay_refunds.json()["error_code"] == "admin_wechat_pay_path_removed"
