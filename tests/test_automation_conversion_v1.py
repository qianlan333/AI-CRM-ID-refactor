from __future__ import annotations

import json

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "automation-conversion-v1.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "RELEASE_SHA": "release-test-sha",
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
            "MCP_BEARER_TOKEN": "mcp-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _sqlite_object_names(db, object_type: str) -> set[str]:
    rows = db.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = ?
        """,
        (object_type,),
    ).fetchall()
    return {str(row["name"]) for row in rows}


def _seed_contact(app, *, external_userid: str, mobile: str = "", owner_userid: str = "sales_01", customer_name: str = "") -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name or external_userid, owner_userid),
        )
        if mobile:
            person_id = db.execute("SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM people").fetchone()["next_id"]
            db.execute(
                """
                INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (person_id, mobile, f"tp-{person_id}"),
            )
            db.execute(
                """
                INSERT INTO external_contact_bindings (
                    external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (external_userid, person_id, owner_userid, owner_userid, owner_userid),
            )
        db.commit()


def _seed_automation_member(
    app,
    *,
    external_contact_id: str,
    phone: str = "",
    owner_staff_id: str = "sales_01",
    in_pool: int = 1,
    current_pool: str = "active_normal",
    follow_type: str = "normal",
    activation_status: str = "active",
    questionnaire_status: str = "submitted",
    questionnaire_result: str = "normal",
    decision_source: str = "manual",
    source_type: str = "manual",
    last_active_pool: str = "",
    joined_at: str = "2026-04-06 10:00:00",
) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                activation_status, questionnaire_status, questionnaire_result, decision_source,
                source_type, last_active_pool, joined_at, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                external_contact_id,
                phone,
                owner_staff_id,
                in_pool,
                current_pool,
                follow_type,
                activation_status,
                questionnaire_status,
                questionnaire_result,
                decision_source,
                source_type,
                last_active_pool,
                joined_at,
            ),
        )
        db.commit()


def _patch_live_context(
    monkeypatch,
    *,
    external_contact_id: str,
    phone: str,
    owner_staff_id: str = "sales_01",
    activation_status: str = "active",
    questionnaire_status: str = "submitted",
    questionnaire_result: str = "normal",
):
    def _fake_build_live_context(request_external_contact_id: str = "", request_phone: str = "") -> dict:
        resolved_external_contact_id = external_contact_id or request_external_contact_id
        resolved_phone = phone or request_phone
        return {
            "lookup": {
                "external_contact_id": resolved_external_contact_id,
                "phone": resolved_phone,
                "master_customer_id": None,
                "external_contact_ids": [resolved_external_contact_id] if resolved_external_contact_id else [],
            },
            "profile": {
                "external_contact_id": resolved_external_contact_id,
                "phone": resolved_phone,
                "customer_name": resolved_external_contact_id or resolved_phone or "测试客户",
                "owner_staff_id": owner_staff_id,
                "owner_display_name": owner_staff_id,
                "unionid": "",
            },
            "activation": {
                "activation_status": activation_status,
                "last_activation_at": "2026-04-06 09:30:00" if activation_status == "active" else "",
            },
            "questionnaire": {
                "questionnaire_status": questionnaire_status,
                "questionnaire_result": questionnaire_result,
                "hit_count": 1 if questionnaire_result == "focus" else 0,
                "matched_question_ids": [1] if questionnaire_result == "focus" else [],
                "matched_questions": ["关键题"] if questionnaire_result == "focus" else [],
                "answers": [],
                "submitted_at": "2026-04-06 09:00:00" if questionnaire_status == "submitted" else "",
                "questionnaire_id": 1 if questionnaire_status == "submitted" else None,
            },
        }

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service._build_live_context",
        _fake_build_live_context,
    )


def test_init_db_creates_automation_conversion_tables_and_indexes(app):
    with app.app_context():
        db = get_db()
        table_names = _sqlite_object_names(db, "table")
        index_names = _sqlite_object_names(db, "index")

        assert {
            "automation_channel",
            "automation_member",
            "automation_event",
            "automation_ai_push_log",
        }.issubset(table_names)
        assert {
            "uq_automation_member_external_non_empty",
            "idx_automation_member_phone",
            "idx_automation_member_pool",
            "idx_automation_event_member_created",
            "idx_automation_ai_push_log_status",
        }.issubset(index_names)


def test_automation_overview_counts_only_from_automation_member(app, client):
    with app.app_context():
        db = get_db()
        rows = [
            ("wm_overview_001", "13800001001", "sales_01", 1, "new_user", "", "unknown", "pending", "unknown", "2026-04-06 09:00:00"),
            ("wm_overview_002", "13800001002", "sales_01", 1, "inactive_normal", "normal", "inactive", "submitted", "normal", "2026-04-06 09:10:00"),
            ("wm_overview_003", "13800001003", "sales_01", 1, "inactive_focus", "focus", "inactive", "submitted", "focus", "2026-04-05 09:20:00"),
            ("wm_overview_004", "13800001004", "sales_01", 1, "silent", "normal", "inactive", "submitted", "normal", "2026-04-05 09:30:00"),
            ("wm_overview_005", "13800001005", "sales_01", 0, "won", "focus", "active", "submitted", "focus", "2026-04-06 09:40:00"),
        ]
        for item in rows:
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                    activation_status, questionnaire_status, questionnaire_result, decision_source,
                    source_type, joined_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'system', 'system', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                item,
            )
        db.commit()

    response = client.get("/api/admin/automation-conversion/overview")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    counts = payload["overview"]["counts"]
    assert counts["in_pool_total"] == 4
    assert counts["questionnaire_pending"] == 1
    assert counts["normal_followup"] == 1
    assert counts["focus_followup"] == 1
    assert counts["silent_total"] == 1
    assert counts["won_total"] == 1


def test_automation_member_actions_write_events(app, client):
    _seed_contact(app, external_userid="wm_action_001", mobile="13800002001", owner_userid="sales_11", customer_name="动作客户")

    put_response = client.post(
        "/api/admin/automation-conversion/member/put-in-pool",
        json={"external_contact_id": "wm_action_001", "operator": "tester"},
    )
    set_focus_response = client.post(
        "/api/admin/automation-conversion/member/set-focus",
        json={"external_contact_id": "wm_action_001", "operator": "tester"},
    )
    mark_won_response = client.post(
        "/api/admin/automation-conversion/member/mark-won",
        json={"external_contact_id": "wm_action_001", "operator": "tester"},
    )

    assert put_response.status_code == 200
    assert set_focus_response.status_code == 200
    assert mark_won_response.status_code == 200

    with app.app_context():
        db = get_db()
        member = db.execute(
            "SELECT * FROM automation_member WHERE external_contact_id = ?",
            ("wm_action_001",),
        ).fetchone()
        assert member is not None
        assert member["in_pool"] == 0
        assert member["current_pool"] == "won"
        assert member["source_type"] == "manual"
        events = db.execute(
            """
            SELECT action, operator_type, operator_id
            FROM automation_event
            WHERE member_id = ?
            ORDER BY id ASC
            """,
            (member["id"],),
        ).fetchall()
        assert [row["action"] for row in events] == ["put_in_pool", "set_focus", "mark_won"]
        assert {row["operator_type"] for row in events} == {"user"}
        assert {row["operator_id"] for row in events} == {"tester"}


def test_openclaw_push_accepts_and_enforces_cooldown(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_ai_001", mobile="13800003001", owner_userid="sales_ai", customer_name="AI 客户")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                activation_status, questionnaire_status, questionnaire_result, decision_source,
                source_type, joined_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 1, 'active_focus', 'focus', 'active', 'submitted', 'focus', 'manual', 'manual', '2026-04-06 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_ai_001", "13800003001", "sales_ai"),
        )
        db.commit()

    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload",
        lambda *, external_userid: {"tags": [{"tag_name": "高潜客户"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload",
        lambda *, external_userid="", mobile="": {
            "answers": [{"question": "预算", "answer": "999"}],
        },
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "messages": [
                {"sender": "wm_ai_001", "send_time": "2026-04-06 10:01:00", "content": "我想看看方案"},
                {"sender": "sales_ai", "send_time": "2026-04-06 10:02:00", "content": "可以，先看这个版本"},
            ],
        },
    )

    captured = {}

    def _fake_send_outbound_webhook(*, event_type, payload, source_key, source_id):
        captured["event_type"] = event_type
        captured["payload"] = payload
        captured["source_key"] = source_key
        captured["source_id"] = source_id
        return {"ok": True, "delivery": {"id": 701}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook",
        _fake_send_outbound_webhook,
    )

    first = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wm_ai_001", "operator": "tester-ai"},
    )
    second = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wm_ai_001", "operator": "tester-ai"},
    )

    assert first.status_code == 202
    assert first.get_json()["status"] == "accepted"
    assert second.status_code == 429
    assert second.get_json()["status"] == "cooldown_blocked"
    assert captured["source_key"] == "automation_member"
    assert captured["source_id"].isdigit()
    assert captured["event_type"] == "openclaw_focus_message"
    assert set(captured["payload"].keys()) == {
        "currentPool",
        "currentStage",
        "currentTarget",
        "tags",
        "questionnaire",
        "recentChats",
    }
    assert captured["payload"]["tags"] == ["高潜客户"]
    assert captured["payload"]["questionnaire"]["answers"] == [{"question": "预算", "answer": "999"}]
    assert len(captured["payload"]["recentChats"]) == 2

    with app.app_context():
        db = get_db()
        member = db.execute(
            "SELECT last_ai_push_at, ai_cooldown_until FROM automation_member WHERE external_contact_id = ?",
            ("wm_ai_001",),
        ).fetchone()
        assert member["last_ai_push_at"]
        assert member["ai_cooldown_until"]
        logs = db.execute(
            "SELECT status, request_payload FROM automation_ai_push_log ORDER BY id ASC"
        ).fetchall()
        assert [row["status"] for row in logs] == ["accepted", "cooldown_blocked"]
        accepted_payload = json.loads(logs[0]["request_payload"])
        assert accepted_payload["currentPool"] == captured["payload"]["currentPool"]
        assert accepted_payload["currentStage"] == captured["payload"]["currentStage"]
        assert accepted_payload["currentTarget"] == captured["payload"]["currentTarget"]
        assert accepted_payload["questionnaire"]["answers"] == [{"question": "预算", "answer": "999"}]


def test_mark_won_and_unmark_restore_active_normal(app, client, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_restore_normal_001",
        phone="13800005001",
        owner_staff_id="sales_restore",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_restore_normal_001",
        phone="13800005001",
        owner_staff_id="sales_restore",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )

    marked = client.post(
        "/api/admin/automation-conversion/member/mark-won",
        json={"external_contact_id": "wm_restore_normal_001", "operator": "tester"},
    )
    restored = client.post(
        "/api/admin/automation-conversion/member/unmark-won",
        json={"external_contact_id": "wm_restore_normal_001", "operator": "tester"},
    )

    assert marked.status_code == 200
    assert marked.get_json()["member"]["current_pool"] == "won"
    assert marked.get_json()["member"]["last_active_pool"] == "active_normal"
    assert restored.status_code == 200
    assert restored.get_json()["member"]["current_pool"] == "active_normal"
    assert restored.get_json()["member"]["last_active_pool"] == "active_normal"

    with app.app_context():
        member = get_db().execute(
            "SELECT current_pool, in_pool, last_active_pool FROM automation_member WHERE external_contact_id = ?",
            ("wm_restore_normal_001",),
        ).fetchone()
        assert dict(member) == {
            "current_pool": "active_normal",
            "in_pool": 1,
            "last_active_pool": "active_normal",
        }


def test_mark_won_and_unmark_restore_active_focus(app, client, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_restore_focus_001",
        phone="13800005002",
        owner_staff_id="sales_restore",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_restore_focus_001",
        phone="13800005002",
        owner_staff_id="sales_restore",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )

    marked = client.post(
        "/api/admin/automation-conversion/member/mark-won",
        json={"external_contact_id": "wm_restore_focus_001", "operator": "tester"},
    )
    restored = client.post(
        "/api/admin/automation-conversion/member/unmark-won",
        json={"external_contact_id": "wm_restore_focus_001", "operator": "tester"},
    )

    assert marked.status_code == 200
    assert marked.get_json()["member"]["current_pool"] == "won"
    assert marked.get_json()["member"]["last_active_pool"] == "active_focus"
    assert restored.status_code == 200
    assert restored.get_json()["member"]["current_pool"] == "active_focus"
    assert restored.get_json()["member"]["last_active_pool"] == "active_focus"

    with app.app_context():
        member = get_db().execute(
            "SELECT current_pool, in_pool, last_active_pool FROM automation_member WHERE external_contact_id = ?",
            ("wm_restore_focus_001",),
        ).fetchone()
        assert dict(member) == {
            "current_pool": "active_focus",
            "in_pool": 1,
            "last_active_pool": "active_focus",
        }


def test_unmark_won_falls_back_when_last_active_pool_missing(app, client, monkeypatch):
    _seed_automation_member(
        app,
        external_contact_id="wm_restore_fallback_001",
        phone="13800005003",
        owner_staff_id="sales_restore",
        in_pool=0,
        current_pool="won",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        last_active_pool="",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_restore_fallback_001",
        phone="13800005003",
        owner_staff_id="sales_restore",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )

    restored = client.post(
        "/api/admin/automation-conversion/member/unmark-won",
        json={"external_contact_id": "wm_restore_fallback_001", "operator": "tester"},
    )

    assert restored.status_code == 200
    assert restored.get_json()["member"]["current_pool"] == "inactive_normal"
    assert restored.get_json()["member"]["last_active_pool"] == "inactive_normal"

    with app.app_context():
        member = get_db().execute(
            "SELECT current_pool, in_pool, last_active_pool FROM automation_member WHERE external_contact_id = ?",
            ("wm_restore_fallback_001",),
        ).fetchone()
        assert dict(member) == {
            "current_pool": "inactive_normal",
            "in_pool": 1,
            "last_active_pool": "inactive_normal",
        }


def test_generate_default_channel_generates_real_channel_via_wecom_provider(app, client, monkeypatch):
    captured = {}

    class _FakeRuntimeClient:
        def create_contact_way(self, payload: dict) -> dict:
            captured["payload"] = payload
            return {
                "config_id": "cfg-001",
                "qr_code": "https://wecom.example/qr/cfg-001",
            }

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.get_contact_runtime_client",
        lambda: _FakeRuntimeClient(),
    )

    response = client.post("/api/admin/automation-conversion/settings/default-channel/generate")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["generated"] is True
    assert payload["provider_available"] is True
    assert payload["channel"]["channel_code"] == "default_qrcode"
    assert payload["channel"]["owner_staff_id"] == "QianLan"
    assert payload["channel"]["qr_url"] == "https://wecom.example/qr/cfg-001"
    assert payload["channel"]["qr_ticket"] == "cfg-001"
    assert payload["channel"]["status"] == "active"
    assert payload["channel"]["scene_value"].startswith("aqr_")
    assert len(payload["channel"]["scene_value"]) <= 30
    assert captured["payload"]["type"] == 1
    assert captured["payload"]["scene"] == 2
    assert captured["payload"]["style"] == 1
    assert captured["payload"]["skip_verify"] is False
    assert captured["payload"]["user"] == ["QianLan"]
    assert captured["payload"]["state"] == payload["channel"]["scene_value"]
    assert len(str(captured["payload"]["state"])) <= 30
    assert "_" in str(captured["payload"]["state"])

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            SELECT channel_code, owner_staff_id, qr_url, qr_ticket, scene_value, status
            FROM automation_channel
            WHERE channel_code = 'default_qrcode'
            """
        ).fetchone()
        assert row is not None
        assert row["channel_code"] == "default_qrcode"
        assert row["owner_staff_id"] == "QianLan"
        assert row["qr_url"] == "https://wecom.example/qr/cfg-001"
        assert row["qr_ticket"] == "cfg-001"
        assert str(row["scene_value"]).startswith("aqr_")
        assert len(str(row["scene_value"])) <= 30
        assert row["status"] == "active"


def test_generate_default_channel_reports_config_incomplete_when_wecom_config_missing(app, client, monkeypatch):
    from wecom_ability_service.wecom_client import WeComClientError

    class _BrokenRuntimeClient:
        def create_contact_way(self, payload: dict) -> dict:
            raise WeComClientError("WECOM_CORP_ID or WECOM_CONTACT_SECRET is not configured")

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.get_contact_runtime_client",
        lambda: _BrokenRuntimeClient(),
    )

    response = client.post("/api/admin/automation-conversion/settings/default-channel/generate")
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["provider_available"] is True
    assert payload["generated"] is False
    assert payload["channel"]["channel_code"] == "default_qrcode"
    assert payload["channel"]["owner_staff_id"] == "QianLan"
    assert payload["channel"]["status"] == "config_incomplete"
    assert payload["error_code"] == "config_incomplete"
    assert "WECOM_CORP_ID or WECOM_CONTACT_SECRET is not configured" in payload["error"]


def test_generate_default_channel_blocks_invalid_state_before_calling_wecom(app, client, monkeypatch):
    called = {"count": 0}

    class _FakeRuntimeClient:
        def create_contact_way(self, payload: dict) -> dict:
            called["count"] += 1
            return {
                "config_id": "cfg-002",
                "qr_code": "https://wecom.example/qr/cfg-002",
            }

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.get_contact_runtime_client",
        lambda: _FakeRuntimeClient(),
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.provider.build_default_channel_state_token",
        lambda *, now=None: "aqr_invalid_state_token_length_more_than_30",
    )

    response = client.post("/api/admin/automation-conversion/settings/default-channel/generate")
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["generated"] is False
    assert payload["error_code"] == "invalid_state"
    assert "state 长度不能超过 30 个字符" in payload["error"]
    assert called["count"] == 0


def test_qrcode_callback_creates_member_and_event(app):
    from wecom_ability_service.domains.automation_conversion.service import handle_qrcode_enter_from_callback

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-default', 'QianLan', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_001",
            phone="13800004001",
            payload_json={"state": "scene-default"},
            operator_id="callback-user",
        )

        assert result["handled"] is True
        member = db.execute(
            """
            SELECT external_contact_id, phone, owner_staff_id, in_pool, current_pool, source_type
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_qrcode_001",),
        ).fetchone()
        assert dict(member) == {
            "external_contact_id": "wm_qrcode_001",
            "phone": "13800004001",
            "owner_staff_id": "QianLan",
            "in_pool": 1,
            "current_pool": "new_user",
            "source_type": "qrcode",
        }
        event = db.execute(
            "SELECT action, operator_type, operator_id FROM automation_event ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(event) == {
            "action": "qrcode_enter",
            "operator_type": "system",
            "operator_id": "callback-user",
        }
