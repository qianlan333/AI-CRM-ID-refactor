from __future__ import annotations

import json

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "timeline.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")
    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "WECOM_CORP_ID": "ww-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def seed_timeline_fixture(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            ("wm_timeline_001", "时间线客户", "sales_01", "重点跟进", "用于 timeline 测试", "2026-03-24 10:00:00"),
        )
        db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                101,
                "timeline-msg-001",
                "private",
                "wm_timeline_001",
                "sales_01",
                "sales_01",
                "wm_timeline_001",
                "text",
                "第一条客户消息",
                "2026-03-20 10:00:00",
                json.dumps({"decrypted_message": {"from": "sales_01", "tolist": ["wm_timeline_001"]}}, ensure_ascii=False),
                "2026-03-20 10:00:01",
            ),
        )
        db.execute(
            """
            INSERT INTO class_user_status_history (
                external_userid, old_signup_status, new_signup_status, old_label_name, new_label_name,
                customer_name_snapshot, owner_userid_snapshot, mobile_snapshot, set_by_userid, set_at,
                wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "wm_timeline_001",
                "lead",
                "signed_999",
                "报名引流品",
                "已报名999",
                "时间线客户",
                "sales_01",
                "13800138000",
                "sales_01",
                "2026-03-23 11:00:00",
                "success",
                "",
                "{}",
                "2026-03-23 11:00:01",
            ),
        )
        db.commit()


def test_timeline_returns_ok_and_external_userid(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert "timeline" in payload
    assert payload["timeline"]["external_userid"] == "wm_timeline_001"


def test_timeline_includes_message_event(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline?event_type=message")
    items = response.get_json()["timeline"]["items"]

    assert len(items) == 1
    assert items[0]["event_type"] == "message"
    assert items[0]["source_table"] == "archived_messages"


def test_timeline_includes_status_change_event(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline?event_type=status_change")
    items = response.get_json()["timeline"]["items"]

    assert len(items) == 1
    assert items[0]["event_type"] == "status_change"
    assert items[0]["source_table"] == "class_user_status_history"


def test_timeline_orders_events_desc_by_event_time(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline")
    items = response.get_json()["timeline"]["items"]

    assert [item["event_type"] for item in items] == ["status_change", "message"]


def test_timeline_event_type_filter_and_paging(client, app):
    seed_timeline_fixture(app)

    response = client.get("/api/customers/wm_timeline_001/timeline?limit=1&offset=1")
    timeline = response.get_json()["timeline"]

    assert timeline["count"] == 1
    assert timeline["limit"] == 1
    assert timeline["offset"] == 1
    assert timeline["filters"] == {"event_type": "", "limit": "1", "offset": "1"}
    assert timeline["items"][0]["event_type"] == "message"


def test_timeline_returns_404_for_missing_customer(client):
    response = client.get("/api/customers/wm_timeline_missing/timeline")
    payload = response.get_json()

    assert response.status_code == 404
    assert payload["ok"] is False
