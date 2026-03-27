from __future__ import annotations

from pathlib import Path

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


class FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http error: {self.status_code}")


def fake_wecom_get(url, params=None, timeout=None):
    if url.endswith("/cgi-bin/gettoken"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "access_token": "token-123", "expires_in": 7200})
    if url.endswith("/cgi-bin/externalcontact/get_follow_user_list"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "follow_user": ["sales_01"]})
    if url.endswith("/cgi-bin/externalcontact/list"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "external_userid": ["wm_ext_001"]})
    if url.endswith("/cgi-bin/externalcontact/get"):
        return FakeResponse(
            {
                "errcode": 0,
                "errmsg": "ok",
                "external_contact": {
                    "external_userid": "wm_ext_001",
                    "name": "周青",
                    "unionid": "union-001",
                    "type": 1,
                    "gender": 2,
                    "avatar": "https://example.com/001.png",
                },
                "follow_user": [{"userid": "sales_01", "remark": "老同学介绍", "description": "wm_ext_001"}],
            }
        )
    raise AssertionError(f"unexpected GET url: {url}")


def fake_wecom_post(url, params=None, json=None, timeout=None):
    if url.endswith("/cgi-bin/externalcontact/get_corp_tag_list"):
        return FakeResponse(
            {
                "errcode": 0,
                "errmsg": "ok",
                "tag_group": [
                    {
                        "group_id": "group-001",
                        "group_name": "客户分层",
                        "tag": [{"id": "et-tag-001", "name": "高意向"}],
                    }
                ],
            }
        )
    if url.endswith("/cgi-bin/externalcontact/mark_tag"):
        return FakeResponse({"errcode": 0, "errmsg": "ok"})
    if url.endswith("/cgi-bin/externalcontact/add_msg_template"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "msgid": "task-msg-001"})
    if url.endswith("/cgi-bin/externalcontact/add_moment_task"):
        return FakeResponse({"errcode": 0, "errmsg": "ok", "jobid": "moment-job-001"})
    raise AssertionError(f"unexpected POST url: {url}")


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "contract.sqlite3"
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
        db = get_db()
        db.execute(
            """
            INSERT INTO archived_messages
            (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                21,
                "contract-msg-001",
                "private",
                "wm_ext_001",
                "sales_01",
                "wm_ext_001",
                "sales_01",
                "text",
                "契约消息",
                "2026-03-20 12:12:00",
                '{"decrypted_message":{"from":"wm_ext_001","tolist":["sales_01"],"roomid":"","msgtype":"text"}}',
            ),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_001", "周青", "sales_01", "老同学介绍", "wm_ext_001"),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id)
            VALUES (?, ?)
            """,
            ("13800138000", "tp-001"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", ("13800138000",)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            ("wm_ext_001", person_id, "sales_01", "sales_01", "sales_01"),
        )
        db.execute(
            """
            INSERT INTO wecom_external_contact_identity_map (
                corp_id, external_userid, unionid, openid, follow_user_userid, name, status, raw_profile
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("ww-test", "wm_ext_001", "union-001", "", "sales_01", "周青", "active", "{}"),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot,
                owner_userid_snapshot, mobile_snapshot, set_by_userid, wecom_tag_sync_status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ("wm_ext_001", "signed_999", "已报名999", "周青", "sales_01", "13800138000", "sales_01", "success"),
        )
        db.commit()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_contract_health_and_ops(client):
    assert client.get("/health").status_code == 200
    ops_response = client.get("/api/ops/status")
    data = ops_response.get_json()
    assert ops_response.status_code == 200
    assert {"ok", "service_ok", "archived_messages_count", "contacts_count", "group_chats_count", "last_seq"} <= set(data.keys())


def test_contract_contacts_and_identity(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    contacts_response = client.get("/api/contacts/wm_ext_001")
    identity_response = client.get("/api/identity/resolve?external_userid=wm_ext_001")
    assert contacts_response.status_code == 200
    assert {"external_userid", "customer_name", "owner_userid", "remark", "description"} <= set(
        contacts_response.get_json()["contact"].keys()
    )
    assert identity_response.status_code == 200
    assert {"person_id", "mobile", "external_userid", "unionid", "signup_status"} <= set(identity_response.get_json().keys())


def test_contract_messages(client):
    messages_response = client.get("/api/messages/wm_ext_001")
    recent_response = client.get("/api/messages/wm_ext_001/recent?limit=1")
    search_response = client.get("/api/messages/search?external_userid=wm_ext_001&keyword=契约")
    assert messages_response.status_code == 200
    assert {"seq", "msgid", "chat_type", "external_userid", "content", "send_time"} <= set(
        messages_response.get_json()["messages"][0].keys()
    )
    assert recent_response.status_code == 200
    recent_payload = recent_response.get_json()
    assert "messages" in recent_payload
    assert len(recent_payload["messages"]) == 1
    assert {"msgid", "msgtype", "content", "send_time", "external_userid"} <= set(recent_payload["messages"][0].keys())
    assert search_response.status_code == 200
    assert len(search_response.get_json()["messages"]) == 1


def test_contract_customer_aggregation_reads(client):
    list_response = client.get("/api/customers")
    detail_response = client.get("/api/customers/wm_ext_001")
    timeline_response = client.get("/api/customers/wm_ext_001/timeline")

    assert list_response.status_code == 200
    list_payload = list_response.get_json()
    assert {"ok", "customers", "count", "items", "total", "limit", "offset", "filters"} <= set(list_payload.keys())
    assert list_payload["items"][0]["external_userid"] == "wm_ext_001"

    assert detail_response.status_code == 200
    detail_payload = detail_response.get_json()
    assert {"ok", "customer"} <= set(detail_payload.keys())
    assert {
        "external_userid",
        "customer_name",
        "owner_userid",
        "last_message_at",
        "last_touch_at",
        "tags",
        "class_user_status",
    } <= set(detail_payload["customer"].keys())
    assert detail_payload["customer"]["external_userid"] == "wm_ext_001"

    assert timeline_response.status_code == 200
    timeline_payload = timeline_response.get_json()
    assert {"ok", "timeline"} <= set(timeline_payload.keys())
    assert {"external_userid", "items", "count", "limit", "offset", "filters", "total"} <= set(
        timeline_payload["timeline"].keys()
    )
    assert timeline_payload["timeline"]["external_userid"] == "wm_ext_001"
    assert {"event_id", "event_type", "event_time", "title", "summary", "source_table", "source_id", "metadata"} <= set(
        timeline_payload["timeline"]["items"][0].keys()
    )


def test_contract_tags_and_tasks(client, monkeypatch):
    monkeypatch.setattr("requests.get", fake_wecom_get)
    monkeypatch.setattr("requests.post", fake_wecom_post)
    tags_response = client.get("/api/tags")
    mark_response = client.post(
        "/api/tags/mark",
        json={"userid": "sales_01", "external_userid": "wm_ext_001", "add_tag": ["et-tag-001"]},
    )
    task_response = client.post(
        "/api/tasks/private-message",
        json={"text": {"content": "今天统一跟进"}, "sender": ["sales_01"]},
    )
    assert tags_response.status_code == 200
    assert {"ok", "result"} <= set(tags_response.get_json().keys())
    assert mark_response.status_code == 200
    assert mark_response.get_json()["ok"] is True
    assert task_response.status_code == 200
    assert {"ok", "task_id", "wecom_result"} <= set(task_response.get_json().keys())


def test_contract_class_user_read(client):
    response = client.get("/api/sidebar/signup-tags/status?external_userid=wm_ext_001")
    data = response.get_json()
    assert response.status_code == 200
    assert {"ok", "definitions", "initialized", "current_signup_status", "current_tag"} <= set(data.keys())


def test_contract_identity_requires_locator(client):
    response = client.get("/api/identity/resolve")
    assert response.status_code == 400
    assert response.get_json()["ok"] is False
