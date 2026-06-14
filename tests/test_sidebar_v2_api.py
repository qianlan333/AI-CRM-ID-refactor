from __future__ import annotations

import inspect

from fastapi.testclient import TestClient

from aicrm_next.customer_read_model import sidebar_v2
from aicrm_next.customer_read_model.dto import CustomerContextRequest
from aicrm_next.customer_read_model.sidebar_v2 import SidebarCommerceReadModel
from aicrm_next.main import create_app


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False


def test_sidebar_v2_workbench_and_read_panels_are_next_owned(monkeypatch):
    client = _client(monkeypatch)

    workbench = client.get("/api/sidebar/v2/workbench?external_userid=wx_ext_001")
    questionnaires = client.get("/api/sidebar/v2/questionnaires?external_userid=wx_ext_001")
    products = client.get("/api/sidebar/v2/products?external_userid=wx_ext_001")
    orders = client.get("/api/sidebar/v2/orders?external_userid=wx_ext_001")

    for response in (workbench, questionnaires, products, orders):
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        payload = response.json()
        _assert_next(payload)
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        assert payload["source_status"] in {"next_read_model", "production_unavailable"}


def test_sidebar_v2_profile_context_and_binding_status_use_next_read_models(monkeypatch):
    client = _client(monkeypatch)

    context = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001").json()
    profile = client.get("/api/sidebar/profile?external_userid=wx_ext_001").json()
    binding = client.get("/api/sidebar/contact-binding-status?external_userid=wx_ext_001").json()

    for payload in (context, profile, binding):
        assert payload["ok"] is True
        _assert_next(payload)
    assert context["context"]["customer"]["external_userid"] == "wx_ext_001"
    assert profile["profile"]["external_userid"] == "wx_ext_001"
    assert binding["is_bound"] is True
    assert binding["mobile"] == "13800138000"


def test_sidebar_jssdk_config_is_fake_safe(monkeypatch):
    client = _client(monkeypatch)

    response = client.get("/api/sidebar/jssdk-config?url=https://example.com/sidebar/bind-mobile")
    payload = response.json()

    assert response.status_code == 200
    _assert_next(payload)
    assert payload["source_status"] == "next_jssdk_adapter"
    assert payload["real_external_call_executed"] is False
    assert "getCurExternalContact" in payload["jsApiList"]


def test_sidebar_bind_mobile_command_stays_local_only(monkeypatch):
    client = _client(monkeypatch)

    response = client.post(
        "/api/sidebar/bind-mobile",
        json={"external_userid": "wx_ext_001", "mobile": "13800138000", "owner_userid": "ZhaoYanFang"},
    )
    payload = response.json()

    assert response.status_code == 200
    _assert_next(payload)
    assert payload["real_external_call_executed"] is False
    assert payload["source_status"] == "next_command"


def test_sidebar_orders_expose_wechat_shop_channel_fields() -> None:
    class FakeContextQuery:
        def __call__(self, request: CustomerContextRequest) -> dict:
            return {
                "ok": True,
                "source_status": "fixture",
                "customer": {
                    "external_userid": request.external_userid,
                    "customer_name": "微信小店客户",
                    "owner_userid": "HuangYouCan",
                    "binding": {},
                },
            }

    class FakeRepo:
        def __init__(self) -> None:
            self.order_calls = []

        def get_contact_snapshot(self, external_userid: str) -> dict:
            return {"external_userid": external_userid, "customer_name": "微信小店客户"}

        def get_external_identity_snapshot(self, external_userid: str) -> dict:
            return {"external_userid": external_userid, "follow_user_userid": "HuangYouCan"}

        def get_profile_fields(self, external_userid: str) -> dict:
            return {}

        def get_contact_binding_status(self, external_userid: str) -> dict:
            return {"is_bound": False, "external_userid": external_userid}

        def get_bindable_wechat_pay_order_mobile(self, external_userid: str) -> dict:
            return {"mobile_snapshot": "18028720840", "order_count": 1}

        def get_workflow_title_for_customer(self, external_userid: str) -> str:
            return ""

        def list_customer_wechat_pay_orders(self, *, external_userid: str, mobile: str = "", limit: int = 20) -> list[dict]:
            self.order_calls.append({"external_userid": external_userid, "mobile": mobile, "limit": limit})
            return [
                {
                    "provider": "wechat_shop",
                    "channel": "wechat_shop",
                    "channel_label": "微信小店",
                    "id": "3737077448554214400",
                    "out_trade_no": "3737077448554214400",
                    "transaction_id": "4600000181202606148304750608",
                    "product_code": "subscription_trial_month",
                    "product_name": "黄小璨会员体验月",
                    "amount_total": 990,
                    "currency": "CNY",
                    "mobile_snapshot": "18028720840",
                    "status": "paid",
                    "trade_state": "SUCCESS",
                    "refunded_amount_total": 0,
                    "refund_status": "",
                    "paid_at": "2026-06-14 17:28:57+08:00",
                    "created_at": "2026-06-14 17:28:30+08:00",
                }
            ]

    repo = FakeRepo()
    payload = SidebarCommerceReadModel(repo=repo, context_query=FakeContextQuery()).orders(
        external_userid="wmbNXyCwAAdv14187FTFLDTKp9UUGrbw",
        owner_userid="HuangYouCan",
    )

    assert payload["ok"] is True
    assert repo.order_calls == [
        {
            "external_userid": "wmbNXyCwAAdv14187FTFLDTKp9UUGrbw",
            "mobile": "18028720840",
            "limit": 20,
        }
    ]
    item = payload["orders"][0]
    assert item["provider"] == "wechat_shop"
    assert item["channel"] == "wechat_shop"
    assert item["channel_label"] == "微信小店"
    assert item["detail_url"] == "/admin/wechat-shop/transactions/3737077448554214400"
    assert item["status_label"] == "已支付"


def test_sidebar_order_sql_includes_wechat_shop_identity_matching() -> None:
    source = inspect.getsource(sidebar_v2.SidebarV2SqlRepository.list_customer_wechat_pay_orders)

    assert "wechat_shop_orders" in source
    assert "wechat_shop_unionid_orders" in source
    assert "微信小店" in source
    assert "DISTINCT ON (provider, id)" in source
