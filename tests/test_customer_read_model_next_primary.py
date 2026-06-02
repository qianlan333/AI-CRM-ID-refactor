from __future__ import annotations

from fastapi.testclient import TestClient

from aicrm_next.customer_read_model.dto import (
    CustomerDetailRequest,
    CustomerTimelineRequest,
    ListCustomersRequest,
    RecentMessagesRequest,
)


class FakeNextCustomerReadRepository:
    def __init__(self) -> None:
        self.list_calls = 0

    def list_customers(self, filters=None, *, limit=None, offset=0):
        self.list_calls += 1
        rows = [
            {
                "external_userid": "wx_ext_001",
                "person_id": "person_001",
                "customer_name": "客户一",
                "remark": "重点客户",
                "description": "客户描述",
                "owner_userid": "owner-a",
                "owner_display_name": "顾问甲",
                "mobile": "13800138000",
                "binding": {"is_bound": True, "binding_status": "bound", "mobile": "13800138000"},
                "tags": ["重点跟进"],
                "class_user_status": {"current_status": "lead"},
                "last_message_at": "2026-06-01T08:00:00+00:00",
                "last_touch_at": "2026-06-01T08:10:00+00:00",
                "updated_at": "2026-06-01T08:10:00+00:00",
                "created_at": "2026-06-01T08:00:00+00:00",
                "identity": {"person_id": "person_001", "external_userid": "wx_ext_001", "mobile": "13800138000"},
                "follow_users": [{"userid": "owner-a", "display_name": "顾问甲", "is_primary": True}],
                "marketing_summary": {"main_stage": "lead"},
                "marketing_profile": {"stage_key": "lead"},
                "contact": {"external_userid": "wx_ext_001", "name": "客户一"},
                "sidebar_context": {"can_open_sidebar": True},
            }
        ]
        mobile = str((filters or {}).get("mobile") or "").strip()
        if mobile:
            rows = [row for row in rows if row.get("mobile") == mobile]
        return rows[offset:] if limit is None else rows[offset : offset + limit]

    def get_customer(self, external_userid: str):
        return self.list_customers()[0] if external_userid == "wx_ext_001" else None

    get_customer_detail = get_customer

    def list_timeline(self, external_userid: str, filters=None, *, limit=None, offset=0):
        rows = [
            {
                "event_id": "evt-1",
                "event_type": "message",
                "event_time": "2026-06-01T08:00:00+00:00",
                "title": "客户消息",
                "summary": "客户问候",
                "source_table": "archived_messages",
                "source_id": "msg-1",
                "metadata": {"msgtype": "text"},
            }
        ]
        return rows[offset:] if limit is None else rows[offset : offset + limit]

    get_customer_timeline = list_timeline

    def list_recent_messages(self, external_userid: str, *, limit=None):
        rows = [
            {
                "msgid": "msg-1",
                "external_userid": external_userid,
                "msgtype": "text",
                "content": "你好",
                "send_time": "2026-06-01T08:00:00+00:00",
                "owner_userid": "owner-a",
                "chat_type": "single",
            }
        ]
        return rows if limit is None else rows[:limit]

    get_recent_messages = list_recent_messages

    def customer_exists(self, external_userid: str) -> bool:
        return external_userid == "wx_ext_001"


def _production_env(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://customer:customer@127.0.0.1:1/aicrm_customer")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("CUSTOMER_READ_MODEL_NEXT_PRIMARY", raising=False)


def _patch_next_repo(monkeypatch, repo):
    from aicrm_next.customer_read_model import application

    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: repo)


def test_next_primary_list_detail_timeline_and_recent_messages_do_not_call_legacy(monkeypatch):
    from aicrm_next.customer_read_model.application import (
        GetCustomerDetailQuery,
        GetCustomerTimelineQuery,
        ListCustomersQuery,
        ListRecentMessagesQuery,
    )

    _production_env(monkeypatch)
    repo = FakeNextCustomerReadRepository()
    _patch_next_repo(monkeypatch, repo)

    customers = ListCustomersQuery()(ListCustomersRequest(limit=10))
    detail = GetCustomerDetailQuery()(CustomerDetailRequest(external_userid="wx_ext_001"))
    timeline = GetCustomerTimelineQuery()(CustomerTimelineRequest(external_userid="wx_ext_001", limit=10))
    messages = ListRecentMessagesQuery()(RecentMessagesRequest(external_userid="wx_ext_001", limit=10))

    for payload in [customers, detail, timeline, messages]:
        assert payload["ok"] is True
        assert payload["source_status"] == "next_read_model"
        assert payload["read_model_status"] == "primary"
        assert payload["fallback_used"] is False
        assert payload["route_owner"] == "ai_crm_next"
    assert customers["customers"][0]["external_userid"] == "wx_ext_001"
    assert detail["customer"]["binding_status"] == "bound"
    assert timeline["timeline"]["items"][0]["event_id"] == "evt-1"
    assert messages["messages"][0]["msgid"] == "msg-1"


def test_next_repository_unavailable_does_not_fallback_to_legacy(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: (_ for _ in ()).throw(RuntimeError("next repo offline")))

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is False
    assert payload["source_status"] == "production_unavailable"
    assert payload["read_model_status"] == "unavailable"
    assert payload["fallback_used"] is False
    assert "legacy_production_facade" not in str(payload)


def test_next_repository_unavailable_without_rollback_returns_production_unavailable(monkeypatch):
    from aicrm_next.customer_read_model import application
    from aicrm_next.customer_read_model.application import ListCustomersQuery

    _production_env(monkeypatch)
    monkeypatch.setattr(application, "build_customer_read_model_repository", lambda: (_ for _ in ()).throw(RuntimeError("next repo offline")))

    payload = ListCustomersQuery()(ListCustomersRequest(limit=10))

    assert payload["ok"] is False
    assert payload["source_status"] == "production_unavailable"
    assert payload["read_model_status"] == "unavailable"
    assert payload["fallback_used"] is False
    assert "local_contract" not in str(payload)


def test_customer_api_and_admin_page_smoke_next_primary(monkeypatch):
    from aicrm_next.main import create_app

    _production_env(monkeypatch)
    _patch_next_repo(monkeypatch, FakeNextCustomerReadRepository())
    client = TestClient(create_app())

    list_response = client.get("/api/customers?limit=10")
    detail_response = client.get("/api/customers/wx_ext_001")
    timeline_response = client.get("/api/customers/wx_ext_001/timeline?limit=10")
    messages_response = client.get("/api/messages/wx_ext_001/recent?limit=10")
    admin_response = client.get("/admin/customers")

    assert list_response.status_code == 200
    assert list_response.json()["source_status"] == "next_read_model"
    assert detail_response.status_code == 200
    assert detail_response.json()["source_status"] == "next_read_model"
    assert timeline_response.status_code == 200
    assert timeline_response.json()["source_status"] == "next_read_model"
    assert messages_response.status_code == 200
    assert messages_response.json()["source_status"] == "next_read_model"
    assert admin_response.status_code == 200
    assert "客户列表" in admin_response.text
