from __future__ import annotations

import inspect

from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlalchemy import create_engine, text

from aicrm_next.commerce.repo import PostgresCommerceRepository
from aicrm_next.customer_read_model import sidebar_v2
from aicrm_next.customer_read_model.dto import CustomerContextRequest
from aicrm_next.customer_read_model.sidebar_v2 import SidebarCommerceReadModel, SidebarV2SqlRepository
from aicrm_next.main import create_app
from aicrm_next.media_library.postgres_repo import PostgresMediaLibraryRepository
from aicrm_next.shared.signed_context import build_sidebar_owner_context_token


def _client(monkeypatch) -> TestClient:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENV", raising=False)
    return TestClient(create_app(), raise_server_exceptions=False)


def _assert_next(payload: dict) -> None:
    assert payload["route_owner"] == "ai_crm_next"
    assert payload["fallback_used"] is False


def test_sidebar_workflow_title_uses_preserved_channel_link_tables_after_retirement() -> None:
    engine = create_engine("sqlite:///:memory:", future=True)

    @event.listens_for(engine, "connect")
    def _sqlite_jsonb_exists(dbapi_connection, _connection_record):
        dbapi_connection.create_function("jsonb_exists", 2, lambda _payload, _value: 0)

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE crm_user_identity (
                    unionid TEXT PRIMARY KEY,
                    primary_external_userid TEXT NOT NULL,
                    external_userids_json TEXT NOT NULL DEFAULT '[]'
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_channel_contact (
                    id INTEGER PRIMARY KEY,
                    unionid TEXT NOT NULL,
                    channel_id INTEGER,
                    updated_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE automation_channel (
                    id INTEGER PRIMARY KEY,
                    channel_code TEXT,
                    channel_name TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE wecom_customer_acquisition_links (
                    id INTEGER PRIMARY KEY,
                    automation_channel_id INTEGER,
                    link_name TEXT,
                    initial_audience_code TEXT,
                    updated_at TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO crm_user_identity (unionid, primary_external_userid, external_userids_json)
                VALUES ('union_sidebar_retired', 'wx_ext_retired', '["wx_ext_retired"]')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_channel_contact (id, unionid, channel_id, updated_at)
                VALUES (1, 'union_sidebar_retired', 11, '2026-06-25 10:00:00')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO automation_channel (id, channel_code, channel_name)
                VALUES (11, 'channel-11', 'Fallback Channel')
                """
            )
        )
        conn.execute(
            text(
                """
                INSERT INTO wecom_customer_acquisition_links (
                    id, automation_channel_id, link_name, initial_audience_code, updated_at
                )
                VALUES (21, 11, 'Preserved Link Name', 'audience-21', '2026-06-25 10:01:00')
                """
            )
        )

    assert (
        SidebarV2SqlRepository(engine=engine).get_workflow_title_for_customer("wx_ext_retired")
        == "Preserved Link Name"
    )
    source = inspect.getsource(SidebarV2SqlRepository.get_workflow_title_for_customer)
    assert "automation_member" not in source
    assert "automation_channel_contact" in source
    assert "crm_user_identity" in source


def test_sidebar_user_visible_read_paths_do_not_join_retired_automation_tables() -> None:
    sidebar_source = inspect.getsource(SidebarV2SqlRepository.get_workflow_title_for_customer)
    commerce_source = inspect.getsource(PostgresCommerceRepository.list_lead_channels)

    assert "automation_workflow" not in sidebar_source
    assert "automation_program" not in sidebar_source
    assert "automation_program" not in commerce_source


def test_sidebar_v2_workbench_and_read_panels_are_next_owned(monkeypatch):
    client = _client(monkeypatch)

    owner_query = "external_userid=wx_ext_001&owner_userid=ZhaoYanFang"
    workbench = client.get(f"/api/sidebar/v2/workbench?{owner_query}")
    questionnaires = client.get(f"/api/sidebar/v2/questionnaires?{owner_query}")
    products = client.get(f"/api/sidebar/v2/products?{owner_query}")
    orders = client.get(f"/api/sidebar/v2/orders?{owner_query}")

    for response in (workbench, questionnaires, products, orders):
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        payload = response.json()
        _assert_next(payload)
        assert "X-AICRM-Compatibility-Facade" not in response.headers
        assert payload["source_status"] in {"next_read_model", "production_unavailable"}


def test_sidebar_v2_owner_token_takes_precedence_over_query_owner(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "sidebar-v2-owner-token")
    client = _client(monkeypatch)
    token = build_sidebar_owner_context_token(viewer_userid="ZhaoYanFang", corp_id="ww-test")

    response = client.get(
        "/api/sidebar/v2/products?external_userid=wx_ext_001&owner_userid=LiuXiao",
        headers={"X-AICRM-Sidebar-Owner-Token": token},
    )

    assert response.status_code == 200
    payload = response.json()
    _assert_next(payload)
    assert payload["products"]


def test_sidebar_v2_profile_context_and_binding_status_use_next_read_models(monkeypatch):
    client = _client(monkeypatch)

    context = client.get("/api/sidebar/customer-context?external_userid=wx_ext_001&owner_userid=ZhaoYanFang").json()
    profile = client.get("/api/sidebar/profile?external_userid=wx_ext_001&owner_userid=ZhaoYanFang").json()
    binding = client.get("/api/sidebar/contact-binding-status?external_userid=wx_ext_001&owner_userid=ZhaoYanFang").json()

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
                    "mobile": "18028720840",
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
    assert payload["diagnostics"]["orders_context"] == "single_context_no_workbench_overlay"
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


def test_sidebar_commerce_and_material_paths_avoid_heavy_list_queries() -> None:
    commerce_source = inspect.getsource(PostgresCommerceRepository.list_sidebar_active_products)
    material_source = inspect.getsource(PostgresMediaLibraryRepository._select_list)

    assert "SELECT p.*" not in commerce_source
    assert "WHERE p.enabled = TRUE AND p.status = 'active'" in commerce_source
    assert "SELECT * FROM {table}" not in material_source
    assert "self._list_columns(kind)" in material_source
