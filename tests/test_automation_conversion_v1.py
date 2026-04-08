from __future__ import annotations

import base64
import json
import re
from io import BytesIO

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.automation_conversion.service import (
    get_member_detail,
    run_message_activity_sync,
    sync_member_activation,
)


def _test_png_bytes() -> bytes:
    return base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+b5f0AAAAASUVORK5CYII="
    )


def _build_stage_send_form_data(
    *,
    content: str = "",
    operator: str = "",
    images: list[tuple[str, bytes, str]] | None = None,
):
    payload = {"content": content, "operator": operator}
    if images:
        payload["images"] = [(BytesIO(file_bytes), file_name, mime_type) for file_name, file_bytes, mime_type in images]
    return payload


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


def _seed_settings_questionnaire(app, *, questionnaire_id: int = 501) -> dict[str, object]:
    choice_question_id = questionnaire_id * 100 + 1
    mobile_question_id = questionnaire_id * 100 + 2
    option_ids = [questionnaire_id * 1000 + 1, questionnaire_id * 1000 + 2]
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, '', 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"automation-settings-{questionnaire_id}",
                f"automation-settings-{questionnaire_id}",
                f"自动化设置问卷 {questionnaire_id}",
            ),
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'single_choice', '你当前更关注什么？', 1, 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (choice_question_id, questionnaire_id),
        )
        db.executemany(
            """
            INSERT INTO questionnaire_options (
                id, question_id, option_text, sort_order, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            [
                (option_ids[0], choice_question_id, "效率", 1),
                (option_ids[1], choice_question_id, "成交", 2),
            ],
        )
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '请填写手机号', 1, 2, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "choice_question_id": choice_question_id,
        "option_ids": option_ids,
        "mobile_question_id": mobile_question_id,
    }


def _configure_message_activity_db(app) -> None:
    app.config["MESSAGE_ACTIVITY_DB_HOST"] = "127.0.0.1"
    app.config["MESSAGE_ACTIVITY_DB_PORT"] = 3306
    app.config["MESSAGE_ACTIVITY_DB_NAME"] = "lobster"
    app.config["MESSAGE_ACTIVITY_DB_USER"] = "lobster_user"
    app.config["MESSAGE_ACTIVITY_DB_PASS"] = "lobster_pass"


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
            "automation_message_activity_sync_run",
            "automation_message_activity_sync_item",
            "automation_focus_send_batch",
            "automation_focus_send_batch_item",
        }.issubset(table_names)
        assert {
            "uq_automation_member_external_non_empty",
            "idx_automation_member_phone",
            "idx_automation_member_pool",
            "idx_automation_event_member_created",
            "idx_automation_ai_push_log_status",
            "idx_automation_message_activity_sync_run_finished",
            "idx_automation_message_activity_sync_item_run",
            "idx_automation_focus_send_batch_stage_status",
            "idx_automation_focus_send_batch_item_batch_position",
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
        "externalContactId",
        "currentPool",
        "currentStage",
        "currentTarget",
        "tags",
        "questionnaire",
        "recentChats",
    }
    assert captured["payload"]["externalContactId"] == "wm_ai_001"
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
        assert accepted_payload["externalContactId"] == "wm_ai_001"
        assert accepted_payload["currentPool"] == captured["payload"]["currentPool"]
        assert accepted_payload["currentStage"] == captured["payload"]["currentStage"]
        assert accepted_payload["currentTarget"] == captured["payload"]["currentTarget"]
        assert accepted_payload["questionnaire"]["answers"] == [{"question": "预算", "answer": "999"}]


def test_openclaw_push_does_not_recompute_active_focus_member_before_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_ai_keep_001", mobile="13800003011", owner_userid="sales_ai", customer_name="AI 稳定客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_ai_keep_001",
        phone="13800003011",
        owner_staff_id="sales_ai",
        in_pool=1,
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
        decision_source="system",
        source_type="message_activity_sync",
        joined_at="2026-04-06 10:00:00",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_ai_keep_001",
        phone="13800003011",
        owner_staff_id="sales_ai",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload",
        lambda *, external_userid: {"tags": [{"tag_name": "重点客户"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload",
        lambda *, external_userid="", mobile="": {"answers": [{"question": "预算", "answer": "999"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "messages": [{"sender": "wm_ai_keep_001", "send_time": "2026-04-06 10:01:00", "content": "我想看看方案"}],
        },
    )

    captured = {}

    def _fake_send_outbound_webhook(*, event_type, payload, source_key, source_id):
        captured["payload"] = payload
        return {"ok": True, "delivery": {"id": 702}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook",
        _fake_send_outbound_webhook,
    )

    response = client.post(
        "/api/admin/automation-conversion/member/push-openclaw",
        json={"external_contact_id": "wm_ai_keep_001", "operator": "tester-ai"},
    )
    payload = response.get_json()

    assert response.status_code == 202
    assert payload["status"] == "accepted"
    assert captured["payload"]["currentPool"] == "active_focus"
    assert captured["payload"]["currentStage"] == "active_focus_followup"
    assert captured["payload"]["currentTarget"] == "focus_followup"

    with app.app_context():
        row = get_db().execute(
            """
            SELECT activation_status, current_pool
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_ai_keep_001",),
        ).fetchone()

    assert row["activation_status"] == "active"
    assert row["current_pool"] == "active_focus"


def test_automation_member_detail_uses_sidebar_button_rules_for_won_members(app, client):
    _seed_contact(app, external_userid="wm_won_001", mobile="13800003099", owner_userid="sales_won", customer_name="已成交客户")
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_member (
                external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                activation_status, questionnaire_status, questionnaire_result, decision_source,
                source_type, last_active_pool, joined_at, created_at, updated_at
            )
            VALUES (?, ?, ?, 0, 'won', 'focus', 'active', 'submitted', 'focus', 'manual', 'manual', 'active_focus', '2026-04-06 10:00:00', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            ("wm_won_001", "13800003099", "sales_won"),
        )
        db.commit()

    response = client.get(
        "/api/admin/automation-conversion/member",
        query_string={"external_contact_id": "wm_won_001"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    detail = payload["detail"]
    assert detail["member"]["current_pool"] == "won"
    assert detail["actions"]["put_in_pool"]["enabled"] is False
    assert detail["actions"]["remove_from_pool"]["enabled"] is False
    assert detail["actions"]["set_focus"]["enabled"] is False
    assert detail["actions"]["set_normal"]["enabled"] is False
    assert detail["actions"]["mark_won"]["enabled"] is False
    assert detail["actions"]["unmark_won"]["enabled"] is True
    assert detail["actions"]["push_openclaw"]["enabled"] is True


def test_sync_member_activation_recomputes_pool_from_inactive_focus_to_active_focus(app, monkeypatch):
    _seed_contact(app, external_userid="wm_sync_active_001", mobile="13800003101", owner_userid="sales_sync", customer_name="激活刷新客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sync_active_001",
        phone="13800003101",
        owner_staff_id="sales_sync",
        in_pool=1,
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
        decision_source="questionnaire",
        source_type="manual",
        joined_at="2026-04-06 10:00:00",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_sync_active_001",
        phone="13800003101",
        owner_staff_id="sales_sync",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )

    with app.app_context():
        payload = sync_member_activation(
            external_contact_id="wm_sync_active_001",
            operator_id="activation_webhook",
        )
        row = get_db().execute(
            """
            SELECT activation_status, current_pool
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_sync_active_001",),
        ).fetchone()
        event = get_db().execute(
            """
            SELECT action, operator_type, operator_id, before_snapshot, after_snapshot
            FROM automation_event
            WHERE member_id = (
                SELECT id FROM automation_member WHERE external_contact_id = ?
            )
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_sync_active_001",),
        ).fetchone()

    assert payload["updated"] is True
    assert payload["member"]["activation_status"] == "active"
    assert payload["member"]["current_pool"] == "active_focus"
    assert row["activation_status"] == "active"
    assert row["current_pool"] == "active_focus"
    assert event["action"] == "activation_refresh"
    assert event["operator_type"] == "system"
    assert event["operator_id"] == "activation_webhook"
    assert json.loads(event["before_snapshot"])["current_pool"] == "inactive_focus"
    assert json.loads(event["after_snapshot"])["current_pool"] == "active_focus"


def test_get_member_detail_view_sync_updates_activation_status_and_pool(app, monkeypatch):
    _seed_contact(app, external_userid="wm_view_sync_001", mobile="13800003102", owner_userid="sales_view", customer_name="查看同步客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_view_sync_001",
        phone="13800003102",
        owner_staff_id="sales_view",
        in_pool=1,
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="questionnaire",
        source_type="manual",
        joined_at="2026-04-06 10:00:00",
    )
    _patch_live_context(
        monkeypatch,
        external_contact_id="wm_view_sync_001",
        phone="13800003102",
        owner_staff_id="sales_view",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )

    with app.app_context():
        detail = get_member_detail(external_contact_id="wm_view_sync_001")
        row = get_db().execute(
            """
            SELECT activation_status, current_pool
            FROM automation_member
            WHERE external_contact_id = ?
            """,
            ("wm_view_sync_001",),
        ).fetchone()

    assert detail["member"]["activation_status"] == "active"
    assert detail["member"]["current_pool"] == "active_normal"
    assert row["activation_status"] == "active"
    assert row["current_pool"] == "active_normal"
    assert detail["actions"]["ai_push"]["enabled"] is True


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
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=601)

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

    save_response = client.post(
        "/api/admin/automation-conversion/settings",
        json={
            "enabled": True,
            "questionnaire_id": questionnaire_seed["questionnaire_id"],
            "core_threshold": 1,
            "top_threshold": 1,
            "quiet_hour_start": 22,
            "timezone": "Asia/Shanghai",
            "welcome_message": "欢迎添加，稍后我会主动联系你。",
            "auto_accept_friend": True,
            "question_rules": [
                {
                    "questionnaire_question_id": questionnaire_seed["choice_question_id"],
                    "hit_option_ids_json": questionnaire_seed["option_ids"],
                    "sort_order": 1,
                }
            ],
            "silent_threshold_days_by_pool": {
                "new_user": 7,
                "inactive_normal": 7,
                "inactive_focus": 7,
                "active_normal": 7,
                "active_focus": 7,
            },
        },
    )
    assert save_response.status_code == 200

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
    assert payload["field_statuses"]["welcome_message"]["status"] == "applied"
    assert payload["field_statuses"]["auto_accept_friend"]["status"] == "applied"
    assert payload["channel"]["scene_value"].startswith("aqr_")
    assert len(payload["channel"]["scene_value"]) <= 30
    assert captured["payload"]["type"] == 1
    assert captured["payload"]["scene"] == 2
    assert captured["payload"]["style"] == 1
    assert captured["payload"]["skip_verify"] is True
    assert captured["payload"]["user"] == ["QianLan"]
    assert captured["payload"]["state"] == payload["channel"]["scene_value"]
    assert "conclusions" not in captured["payload"]
    assert len(str(captured["payload"]["state"])) <= 30
    assert "_" in str(captured["payload"]["state"])

    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            SELECT channel_code, owner_staff_id, qr_url, qr_ticket, scene_value, status, welcome_message, auto_accept_friend
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
        assert row["welcome_message"] == "欢迎添加，稍后我会主动联系你。"
        assert bool(row["auto_accept_friend"]) is True


def test_default_channel_settings_save_and_readback_welcome_and_auto_accept(app, client):
    questionnaire_seed = _seed_settings_questionnaire(app, questionnaire_id=602)
    response = client.post(
        "/api/admin/automation-conversion/settings",
        json={
            "enabled": True,
            "questionnaire_id": questionnaire_seed["questionnaire_id"],
            "core_threshold": 1,
            "top_threshold": 1,
            "quiet_hour_start": 22,
            "timezone": "Asia/Shanghai",
            "welcome_message": "这里是默认渠道欢迎语",
            "auto_accept_friend": True,
            "question_rules": [
                {
                    "questionnaire_question_id": questionnaire_seed["choice_question_id"],
                    "hit_option_ids_json": questionnaire_seed["option_ids"],
                    "sort_order": 1,
                }
            ],
            "silent_threshold_days_by_pool": {
                "new_user": 7,
                "inactive_normal": 7,
                "inactive_focus": 7,
                "active_normal": 7,
                "active_focus": 7,
            },
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["settings"]["default_channel"]["welcome_message"] == "这里是默认渠道欢迎语"
    assert payload["settings"]["default_channel"]["auto_accept_friend"] is True
    assert payload["settings"]["default_channel"]["field_statuses"]["welcome_message"]["status"] == "pending"
    assert payload["settings"]["default_channel"]["field_statuses"]["auto_accept_friend"]["status"] == "pending"

    settings_page = client.get("/admin/automation-conversion/settings")
    html = settings_page.get_data(as_text=True)
    assert settings_page.status_code == 200
    assert "这里是默认渠道欢迎语" in html
    assert "免验证直接添加好友" in html

    with app.app_context():
        row = get_db().execute(
            """
            SELECT welcome_message, auto_accept_friend, status
            FROM automation_channel
            WHERE channel_code = 'default_qrcode'
            """
        ).fetchone()
        assert row is not None
        assert row["welcome_message"] == "这里是默认渠道欢迎语"
        assert bool(row["auto_accept_friend"]) is True
        assert row["status"] == "configured"


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


def test_message_activity_sync_updates_activation_follow_type_and_pool(app, monkeypatch):
    _configure_message_activity_db(app)
    members = [
        ("wm_msg_sync_001", "13800001231", "inactive_normal"),
        ("wm_msg_sync_002", "13800001232", "inactive_normal"),
        ("wm_msg_sync_003", "13800001233", "active_focus"),
        ("wm_msg_sync_004", "13800001234", "active_normal"),
    ]
    for external_userid, mobile, current_pool in members:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_msg", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_msg",
            current_pool=current_pool,
            follow_type="normal",
            activation_status="inactive",
            questionnaire_status="submitted",
            questionnaire_result="normal",
            decision_source="questionnaire",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [
            {"phone_last4": "1231", "message_count": 15},
            {"phone_last4": "1232", "message_count": 10},
            {"phone_last4": "1233", "message_count": 1},
            {"phone_last4": "1234", "message_count": 0},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        rows = get_db().execute(
            """
            SELECT external_contact_id, activation_status, follow_type, decision_source, current_pool
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_msg_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()
        event_actions = get_db().execute(
            """
            SELECT action
            FROM automation_event
            WHERE action = 'message_activity_sync'
            ORDER BY id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["candidate_count"] == 4
    assert payload["run"]["matched_count"] == 4
    assert payload["run"]["updated_count"] == 4
    assert payload["run"]["focus_count"] == 1
    assert payload["run"]["normal_count"] == 3
    assert [dict(row) for row in rows] == [
        {
            "external_contact_id": "wm_msg_sync_001",
            "activation_status": "active",
            "follow_type": "focus",
            "decision_source": "system",
            "current_pool": "active_focus",
        },
        {
            "external_contact_id": "wm_msg_sync_002",
            "activation_status": "active",
            "follow_type": "normal",
            "decision_source": "system",
            "current_pool": "active_normal",
        },
        {
            "external_contact_id": "wm_msg_sync_003",
            "activation_status": "inactive",
            "follow_type": "normal",
            "decision_source": "system",
            "current_pool": "inactive_normal",
        },
        {
            "external_contact_id": "wm_msg_sync_004",
            "activation_status": "inactive",
            "follow_type": "normal",
            "decision_source": "system",
            "current_pool": "inactive_normal",
        },
    ]
    assert len(event_actions) == 4


def test_message_activity_sync_preserves_manual_follow_type(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_manual_sync_001", mobile="13800002221", owner_userid="sales_manual", customer_name="manual-1")
    _seed_contact(app, external_userid="wm_manual_sync_002", mobile="13800002222", owner_userid="sales_manual", customer_name="manual-2")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_sync_001",
        phone="13800002221",
        owner_staff_id="sales_manual",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
        decision_source="manual",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_sync_002",
        phone="13800002222",
        owner_staff_id="sales_manual",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="manual",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [
            {"phone_last4": "2221", "message_count": 20},
            {"phone_last4": "2222", "message_count": 0},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        rows = get_db().execute(
            """
            SELECT external_contact_id, activation_status, follow_type, decision_source, current_pool
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_manual_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["candidate_count"] == 2
    assert payload["run"]["matched_count"] == 2
    assert [dict(row) for row in rows] == [
        {
            "external_contact_id": "wm_manual_sync_001",
            "activation_status": "active",
            "follow_type": "focus",
            "decision_source": "system",
            "current_pool": "active_focus",
        },
        {
            "external_contact_id": "wm_manual_sync_002",
            "activation_status": "inactive",
            "follow_type": "focus",
            "decision_source": "manual",
            "current_pool": "inactive_focus",
        },
    ]


def test_message_activity_sync_uses_questionnaire_result_for_inactive_members(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_questionnaire_sync_001", mobile="13800002441", owner_userid="sales_questionnaire", customer_name="questionnaire-focus")
    _seed_contact(app, external_userid="wm_questionnaire_sync_002", mobile="13800002442", owner_userid="sales_questionnaire", customer_name="questionnaire-normal")
    _seed_automation_member(
        app,
        external_contact_id="wm_questionnaire_sync_001",
        phone="13800002441",
        owner_staff_id="sales_questionnaire",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
        decision_source="system",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_questionnaire_sync_002",
        phone="13800002442",
        owner_staff_id="sales_questionnaire",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="system",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [
            {"phone_last4": "2441", "message_count": 1},
            {"phone_last4": "2442", "message_count": 0},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        rows = get_db().execute(
            """
            SELECT external_contact_id, activation_status, follow_type, decision_source, current_pool
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_questionnaire_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert [dict(row) for row in rows] == [
        {
            "external_contact_id": "wm_questionnaire_sync_001",
            "activation_status": "inactive",
            "follow_type": "focus",
            "decision_source": "system",
            "current_pool": "inactive_focus",
        },
        {
            "external_contact_id": "wm_questionnaire_sync_002",
            "activation_status": "inactive",
            "follow_type": "normal",
            "decision_source": "system",
            "current_pool": "inactive_normal",
        },
    ]


def test_message_activity_sync_skips_ambiguous_and_unmatched_members(app, monkeypatch):
    _configure_message_activity_db(app)
    rows = [
        ("wm_skip_sync_001", "13800003331"),
        ("wm_skip_sync_002", "13900003331"),
        ("wm_skip_sync_003", "13800003332"),
        ("wm_skip_sync_004", "13800003339"),
    ]
    for external_userid, mobile in rows:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_skip", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_skip",
            current_pool="inactive_normal",
            follow_type="normal",
            activation_status="inactive",
            questionnaire_status="submitted",
            questionnaire_result="normal",
            decision_source="questionnaire",
        )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [
            {"phone_last4": "3331", "message_count": 9},
            {"phone_last4": "3332", "message_count": 3},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        items = get_db().execute(
            """
            SELECT external_contact_id, status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY id ASC
            """,
            (payload["run"]["id"],),
        ).fetchall()
        members = get_db().execute(
            """
            SELECT external_contact_id, activation_status, current_pool
            FROM automation_member
            WHERE external_contact_id LIKE 'wm_skip_sync_%'
            ORDER BY external_contact_id ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["candidate_count"] == 4
    assert payload["run"]["matched_count"] == 1
    assert payload["run"]["updated_count"] == 1
    assert payload["run"]["skipped_ambiguous_count"] == 2
    assert payload["run"]["skipped_unmatched_count"] == 1
    assert [dict(item) for item in items] == [
        {
            "external_contact_id": "wm_skip_sync_001",
            "status": "skipped_ambiguous",
            "detail": "phone_last4=3331 matched multiple automation members: wm_skip_sync_001,wm_skip_sync_002",
        },
        {
            "external_contact_id": "wm_skip_sync_002",
            "status": "skipped_ambiguous",
            "detail": "phone_last4=3331 matched multiple automation members: wm_skip_sync_001,wm_skip_sync_002",
        },
        {
            "external_contact_id": "wm_skip_sync_004",
            "status": "skipped_unmatched",
            "detail": "phone_last4=3339 not found in message activity source",
        },
        {
            "external_contact_id": "wm_skip_sync_003",
            "status": "updated",
            "detail": "rank=1/1; bucket=active_normal_threshold; effective_follow_type=normal; manual_preserved=no",
        },
    ]
    assert [dict(item) for item in members] == [
        {"external_contact_id": "wm_skip_sync_001", "activation_status": "inactive", "current_pool": "inactive_normal"},
        {"external_contact_id": "wm_skip_sync_002", "activation_status": "inactive", "current_pool": "inactive_normal"},
        {"external_contact_id": "wm_skip_sync_003", "activation_status": "active", "current_pool": "active_normal"},
        {"external_contact_id": "wm_skip_sync_004", "activation_status": "inactive", "current_pool": "inactive_normal"},
    ]


def test_message_activity_sync_api_requires_internal_token_and_returns_run(app, client, monkeypatch):
    _configure_message_activity_db(app)
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "sync-token"
    _seed_contact(app, external_userid="wm_sync_api_001", mobile="13800004441", owner_userid="sales_api", customer_name="sync-api")
    _seed_automation_member(
        app,
        external_contact_id="wm_sync_api_001",
        phone="13800004441",
        owner_staff_id="sales_api",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="questionnaire",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [{"phone_last4": "4441", "message_count": 5}],
    )

    unauthorized = client.post("/api/admin/automation-conversion/message-activity-sync/run", json={"trigger_source": "scheduled"})
    authorized = client.post(
        "/api/admin/automation-conversion/message-activity-sync/run",
        json={"trigger_source": "scheduled", "operator": "tester-sync-api"},
        headers={"Authorization": "Bearer sync-token"},
    )

    assert unauthorized.status_code == 401
    assert unauthorized.get_json()["error"] == "missing internal token"
    assert authorized.status_code == 200
    assert authorized.get_json()["ok"] is True
    assert authorized.get_json()["run"]["trigger_source"] == "scheduled"
    assert authorized.get_json()["run"]["matched_count"] == 1


def test_automation_conversion_settings_page_renders_message_activity_sync_section(app, client):
    response = client.get("/admin/automation-conversion/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "消息活跃同步" in html
    assert "立即刷新一次" in html


def test_automation_conversion_home_stage_cards_show_view_and_send_actions(app, client):
    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "消息活跃同步" in html
    assert "立即刷新一次" in html
    assert 'data-message-activity-sync-root' in html
    assert 'data-message-activity-sync-button' in html
    assert html.count("创建群发") == 7
    assert html.count("查看名单") == 7
    assert '<article class="admin-card admin-stat-card admin-stat-card--nested automation-stage-card">' in html


def test_automation_conversion_home_page_renders_message_activity_sync_summary(app, client, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_home_sync_001", mobile="13800009441", owner_userid="sales_home", customer_name="首页同步客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_home_sync_001",
        phone="13800009441",
        owner_staff_id="sales_home",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="questionnaire",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [{"phone_last4": "9441", "message_count": 6}],
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service._iso_now",
        lambda: "2026-04-08 10:30:00",
    )

    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="home-sync",
            operator_type="user",
            trigger_source="manual",
        )
        assert payload["ok"] is True

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert re.search(r'data-message-activity-sync-status>\s*成功\s*</dd>', html)
    assert re.search(r'data-message-activity-sync-finished-at>\s*2026-04-08 10:30:00\s*</dd>', html)
    assert re.search(r'data-message-activity-sync-updated-count>\s*1\s*</dd>', html)
    assert re.search(r'data-message-activity-sync-skipped-count>\s*0\s*</dd>', html)


def test_admin_automation_conversion_run_message_activity_sync_returns_json_for_homepage(app, client, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_home_run_001", mobile="13800009442", owner_userid="sales_home", customer_name="首页运行客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_home_run_001",
        phone="13800009442",
        owner_staff_id="sales_home",
        current_pool="inactive_normal",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="questionnaire",
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.query_message_activity_counts",
        lambda: [{"phone_last4": "9442", "message_count": 8}],
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service._iso_now",
        lambda: "2026-04-08 10:40:00",
    )

    response = client.post(
        "/admin/automation-conversion/message-activity-sync/run",
        data={"admin_action_token": "ok", "operator": "homepage-sync"},
        headers={"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["message"] == "消息活跃同步已完成"
    assert payload["run"]["updated_count"] == 1
    assert payload["message_activity_sync"]["last_run"]["status_label"] == "成功"
    assert payload["message_activity_sync"]["last_run"]["finished_at"] == "2026-04-08 10:40:00"
    assert payload["message_activity_sync"]["last_run"]["updated_count"] == 1
    assert payload["message_activity_sync"]["last_run"]["skipped_count"] == 0


def test_automation_conversion_stage_detail_keeps_only_total_and_today_new_metrics(app, client):
    _seed_contact(app, external_userid="wm_stage_new_user_001", mobile="13800009111", customer_name="阶段页客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_stage_new_user_001",
        phone="13800009111",
        current_pool="new_user",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
    )

    response = client.get("/admin/automation-conversion/stage/new-user")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "创建群发" in html
    assert '<div class="admin-card-label">总人数</div>' in html
    assert '<div class="admin-card-label">今日新增</div>' in html
    assert '<div class="admin-card-label">重点跟进</div>' not in html
    assert '<div class="admin-card-label">普通跟进</div>' not in html


def test_automation_conversion_stage_send_page_switches_between_manual_and_focus_modes(app, client):
    normal_response = client.get("/admin/automation-conversion/stage/new-user/send")
    focus_response = client.get("/admin/automation-conversion/stage/inactive-focus/send")

    normal_html = normal_response.get_data(as_text=True)
    focus_html = focus_response.get_data(as_text=True)

    assert normal_response.status_code == 200
    assert "官方群发" in normal_html
    assert "文本 + 图片" in normal_html
    assert 'id="stage-send-image-input"' in normal_html
    assert "添加图片" in normal_html
    assert "发送前预览" in normal_html
    assert "/manual-send/preview" in normal_html
    assert "/api/admin/automation-conversion/stage/new-user/manual-send" in normal_html
    assert "/api/admin/automation-conversion/stage/new-user/focus-send-batches" not in normal_html

    assert focus_response.status_code == 200
    assert "AI 批量处理" in focus_html
    assert "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches" in focus_html
    assert "/api/admin/automation-conversion/stage/inactive-focus/manual-send" not in focus_html
    assert "/api/admin/automation-conversion/focus-send-batches/" in focus_html


def test_automation_conversion_stage_send_api_surfaces_validation_and_placeholder_states(app, client):
    manual = client.post("/api/admin/automation-conversion/stage/new-user/manual-send", json={"operator": "tester"})
    focus = client.post("/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches")
    detail = client.get("/api/admin/automation-conversion/focus-send-batches/batch-001")

    assert manual.status_code == 400
    assert manual.get_json()["error"] == "content, images, or attachments is required"
    assert focus.status_code == 201
    assert focus.get_json()["ok"] is True
    assert focus.get_json()["batch"]["stage_key"] == "inactive-focus"
    assert detail.status_code == 400
    assert detail.get_json()["error"] == "invalid batch_id"


def test_focus_send_batch_can_be_created_for_inactive_focus_stage(app, client):
    _seed_contact(app, external_userid="wm_focus_batch_001", mobile="13800009301", owner_userid="sales_focus", customer_name="重点客户一")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_batch_001",
        phone="13800009301",
        owner_staff_id="sales_focus",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches",
        json={"operator": "tester"},
    )
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["status"] == "created"
    assert payload["batch"]["stage_key"] == "inactive-focus"
    assert payload["batch"]["total_count"] == 1
    assert payload["batch"]["remaining_count"] == 1
    assert payload["items"][0]["status"] == "pending"

    detail = client.get(f"/api/admin/automation-conversion/focus-send-batches/{payload['batch']['id']}")
    detail_payload = detail.get_json()
    assert detail.status_code == 200
    assert detail_payload["ok"] is True
    assert detail_payload["batch"]["stage_key"] == "inactive-focus"


def test_focus_send_batch_can_be_created_for_active_focus_stage(app, client):
    _seed_contact(app, external_userid="wm_focus_batch_002", mobile="13800009302", owner_userid="sales_focus", customer_name="重点客户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_batch_002",
        phone="13800009302",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    )
    payload = response.get_json()

    assert response.status_code == 201
    assert payload["ok"] is True
    assert payload["batch"]["stage_key"] == "active-focus"
    assert payload["batch"]["total_count"] == 1
    assert payload["items"][0]["status"] == "pending"


def test_focus_send_batch_runner_only_advances_due_items_and_updates_next_run_at(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "focus-token"
    _seed_contact(app, external_userid="wm_focus_run_001", mobile="13800009311", owner_userid="sales_focus", customer_name="重点客户一")
    _seed_contact(app, external_userid="wm_focus_run_002", mobile="13800009312", owner_userid="sales_focus", customer_name="重点客户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_run_001",
        phone="13800009311",
        owner_staff_id="sales_focus",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_run_002",
        phone="13800009312",
        owner_staff_id="sales_focus",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    times = iter(
        [
            "2026-04-07 10:00:00",
            "2026-04-07 10:00:00",
            "2026-04-07 10:00:10",
            "2026-04-07 10:00:20",
        ]
    )
    push_calls: list[str] = []
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: next(times))
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.push_openclaw",
        lambda **payload: (
            push_calls.append(str(payload.get("external_contact_id") or "")),
            {"accepted": True, "status": "accepted", "member": {"external_contact_id": payload.get("external_contact_id")}},
        )[1],
    )

    created = client.post(
        "/api/admin/automation-conversion/stage/inactive-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    batch_id = created["batch"]["id"]

    first = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    second = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    third = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()

    assert first["processed_count"] == 1
    assert first["batches"][0]["batch"]["sent_count"] == 1
    assert first["batches"][0]["batch"]["remaining_count"] == 1
    assert first["batches"][0]["batch"]["next_run_at"] == "2026-04-07 10:00:20"
    assert second["processed_count"] == 0
    assert third["processed_count"] == 1
    assert third["batches"][0]["batch"]["sent_count"] == 2
    assert third["batches"][0]["batch"]["remaining_count"] == 0
    assert third["batches"][0]["batch"]["status"] == "finished"
    assert sorted(push_calls) == ["wm_focus_run_001", "wm_focus_run_002"]

    detail = client.get(f"/api/admin/automation-conversion/focus-send-batches/{batch_id}").get_json()
    assert detail["batch"]["sent_count"] == 2
    assert [item["status"] for item in detail["items"]] == ["sent", "sent"]


def test_focus_send_batch_runner_item_failure_does_not_block_batch(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "focus-token"
    _seed_contact(app, external_userid="wm_focus_fail_001", mobile="13800009321", owner_userid="sales_focus", customer_name="重点客户一")
    _seed_contact(app, external_userid="wm_focus_fail_002", mobile="13800009322", owner_userid="sales_focus", customer_name="重点客户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_fail_001",
        phone="13800009321",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_fail_002",
        phone="13800009322",
        owner_staff_id="sales_focus",
        current_pool="active_focus",
        follow_type="focus",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    times = iter(
        [
            "2026-04-07 11:00:00",
            "2026-04-07 11:00:00",
            "2026-04-07 11:00:20",
        ]
    )
    call_index = {"value": 0}

    def fake_push_openclaw(**payload):
        call_index["value"] += 1
        if call_index["value"] == 1:
            return {"accepted": False, "status": "failed", "error": "openclaw webhook failed"}
        return {"accepted": True, "status": "accepted", "member": {"external_contact_id": payload.get("external_contact_id")}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: next(times))
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.push_openclaw", fake_push_openclaw)

    created = client.post(
        "/api/admin/automation-conversion/stage/active-focus/focus-send-batches",
        json={"operator": "tester"},
    ).get_json()
    batch_id = created["batch"]["id"]

    first = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()
    second = client.post(
        "/api/admin/automation-conversion/focus-send-batches/run-due",
        headers={"Authorization": "Bearer focus-token"},
    ).get_json()

    assert first["batches"][0]["batch"]["failed_count"] == 1
    assert first["batches"][0]["batch"]["remaining_count"] == 1
    assert second["batches"][0]["batch"]["sent_count"] == 1
    assert second["batches"][0]["batch"]["failed_count"] == 1
    assert second["batches"][0]["batch"]["remaining_count"] == 0
    assert second["batches"][0]["batch"]["status"] == "finished"

    detail = client.get(f"/api/admin/automation-conversion/focus-send-batches/{batch_id}").get_json()
    assert [item["status"] for item in detail["items"]] == ["failed", "sent"]



def test_manual_send_new_user_stage_uses_single_sender_without_owner_buckets(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_new_001", mobile="13800009201", owner_userid="sales_01", customer_name="新用户一")
    _seed_contact(app, external_userid="wm_manual_new_002", mobile="13800009202", owner_userid="sales_02", customer_name="新用户二")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_new_001",
        phone="13800009201",
        owner_staff_id="sales_01",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_new_002",
        phone="13800009202",
        owner_staff_id="sales_02",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
    )
    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append({"task_type": task_type, "fn_name": fn_name, "payload": dict(payload)})
        return {"task_id": 701, "wecom_result": {"msgid": "msg-701"}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "欢迎先看问卷", "image_media_ids": ["img-media-001", "img-media-002"], "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stage_key"] == "new-user"
    assert payload["total_target_count"] == 2
    assert payload["sent_count"] == 2
    assert payload["skipped_count"] == 0
    assert payload["task_ids"] == [701]
    assert len(dispatched_payloads) == 1
    assert dispatched_payloads[0]["task_type"] == "private_message"
    assert dispatched_payloads[0]["fn_name"] == "create_private_message_task"
    assert dispatched_payloads[0]["payload"]["sender"] == "QianLan"
    assert sorted(dispatched_payloads[0]["payload"]["external_userid"]) == ["wm_manual_new_001", "wm_manual_new_002"]
    assert dispatched_payloads[0]["payload"]["image_media_ids"] == ["img-media-001", "img-media-002"]
    assert "attachments" not in dispatched_payloads[0]["payload"]

    with app.app_context():
        row = get_db().execute(
            """
            SELECT filter_snapshot_json, sender_userids_json, selected_count, eligible_count, sent_count
            FROM user_ops_send_records
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        filter_snapshot = json.loads(row["filter_snapshot_json"])
        assert filter_snapshot["selection_mode"] == "automation_conversion_stage"
        assert filter_snapshot["stage_key"] == "new-user"
        assert filter_snapshot["pool_key"] == "new_user"
        assert "owner_userid" not in filter_snapshot
        assert json.loads(row["sender_userids_json"]) == ["QianLan"]
        assert row["selected_count"] == 2
        assert row["eligible_count"] == 2
        assert row["sent_count"] == 2


def test_manual_send_preview_supports_local_images_and_uses_qianlan_sender(app, client):
    _seed_contact(app, external_userid="wm_manual_preview_001", mobile="13800009291", owner_userid="WangWei", customer_name="预览客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_preview_001",
        phone="13800009291",
        owner_staff_id="WangWei",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send/preview",
        data=_build_stage_send_form_data(
            content="图片预览🙂",
            images=[("hello.png", _test_png_bytes(), "image/png")],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["content_preview"] == "图片预览🙂"
    assert payload["image_count"] == 1
    assert payload["eligible_count"] == 1
    assert payload["final_targets"][0]["owner_userid"] == "QianLan"
    assert payload["final_targets"][0]["owner_display_name"] == "QianLan"


def test_manual_send_preview_rejects_fourth_local_image(app, client):
    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send/preview",
        data=_build_stage_send_form_data(
            images=[(f"img-{index}.png", _test_png_bytes(), "image/png") for index in range(1, 5)],
        ),
        content_type="multipart/form-data",
    )
    payload = response.get_json()

    assert response.status_code == 400
    assert payload["error"] == "at most 3 images are allowed"


def test_manual_send_silent_stage_can_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_silent_001", mobile="13800009211", owner_userid="sales_silent", customer_name="沉默客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_silent_001",
        phone="13800009211",
        owner_staff_id="sales_silent",
        current_pool="silent",
        follow_type="normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 702, "wecom_result": {"msgid": "msg-702"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/silent/manual-send",
        json={"content": "沉默池唤醒触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stage_key"] == "silent"
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["task_ids"] == [702]


def test_manual_send_won_stage_can_send(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_won_001", mobile="13800009221", owner_userid="sales_won", customer_name="已成交客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_won_001",
        phone="13800009221",
        owner_staff_id="sales_won",
        in_pool=0,
        current_pool="won",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        last_active_pool="active_normal",
    )

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 703, "wecom_result": {"msgid": "msg-703"}},
    )

    response = client.post(
        "/api/admin/automation-conversion/stage/won/manual-send",
        json={"content": "已成交后续维护", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["stage_key"] == "won"
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 0
    assert payload["task_ids"] == [703]


def test_manual_send_skips_members_missing_external_userid(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_skip_001", mobile="13800009231", owner_userid="sales_skip", customer_name="可发送客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_skip_001",
        phone="13800009231",
        owner_staff_id="sales_skip",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )
    _seed_automation_member(
        app,
        external_contact_id="",
        phone="13800009232",
        owner_staff_id="sales_skip",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
    )
    dispatched_payloads: list[dict[str, object]] = []

    def fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        dispatched_payloads.append(dict(payload))
        return {"task_id": 704, "wecom_result": {"msgid": "msg-704"}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task", fake_dispatch)

    response = client.post(
        "/api/admin/automation-conversion/stage/active-normal/manual-send",
        json={"content": "激活普通池统一触达", "operator": "tester"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["total_target_count"] == 2
    assert payload["sent_count"] == 1
    assert payload["skipped_count"] == 1
    assert payload["skipped_reasons"] == {"missing_external_userid": 1}
    assert dispatched_payloads[0]["external_userid"] == ["wm_manual_skip_001"]


def test_admin_stage_send_page_shows_manual_send_summary(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_manual_page_001", mobile="13800009241", owner_userid="sales_page", customer_name="页面客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_manual_page_001",
        phone="13800009241",
        owner_staff_id="sales_page",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: captured_payloads.append(dict(payload)) or {"task_id": 705, "wecom_result": {"msgid": "msg-705"}},
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")
    captured_payloads: list[dict[str, object]] = []

    response = client.post(
        "/admin/automation-conversion/stage/new-user/send",
        data=_build_stage_send_form_data(
            content="页面触达",
            operator="tester",
            images=[("page.png", _test_png_bytes(), "image/png")],
        ),
        content_type="multipart/form-data",
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "官方群发已创建" in html
    assert "本次执行结果" in html
    assert "发送记录 ID" in html
    assert 'id="stage-send-image-input"' in html
    assert len(captured_payloads) == 1
    assert captured_payloads[0]["sender"] == "QianLan"
    assert "images" in captured_payloads[0]
    assert "image_media_ids" not in captured_payloads[0]


def test_admin_stage_send_page_shows_focus_batch_summary(app, client, monkeypatch):
    _seed_contact(app, external_userid="wm_focus_page_001", mobile="13800009331", owner_userid="sales_page", customer_name="重点页面客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_focus_page_001",
        phone="13800009331",
        owner_staff_id="sales_page",
        current_pool="inactive_focus",
        follow_type="focus",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="focus",
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")

    response = client.post(
        "/admin/automation-conversion/stage/inactive-focus/send",
        data={"operator": "tester"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 批任务已创建" in html
    assert "AI 批任务状态" in html
    assert "总数" in html
    assert "剩余" in html


def test_message_activity_sync_returns_not_configured_without_creating_run(app):
    with app.app_context():
        payload = run_message_activity_sync(
            operator_id="tester-message-sync",
            operator_type="user",
            trigger_source="manual",
        )
        run_count = get_db().execute("SELECT COUNT(*) AS count FROM automation_message_activity_sync_run").fetchone()["count"]

    assert payload["ok"] is False
    assert payload["status"] == "not_configured"
    assert payload["error"] == "message activity db is not configured"
    assert payload["missing_keys"] == [
        "MESSAGE_ACTIVITY_DB_HOST",
        "MESSAGE_ACTIVITY_DB_NAME",
        "MESSAGE_ACTIVITY_DB_USER",
        "MESSAGE_ACTIVITY_DB_PASS",
    ]
    assert payload["run"] == {}
    assert run_count == 0


def test_message_activity_sync_api_returns_400_when_db_not_configured(app, client):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "sync-token"

    response = client.post(
        "/api/admin/automation-conversion/message-activity-sync/run",
        json={"trigger_source": "scheduled", "operator": "tester-sync-api"},
        headers={"Authorization": "Bearer sync-token"},
    )

    assert response.status_code == 400
    body = response.get_json()
    assert body["ok"] is False
    assert body["status"] == "not_configured"
    assert body["missing_keys"] == [
        "MESSAGE_ACTIVITY_DB_HOST",
        "MESSAGE_ACTIVITY_DB_NAME",
        "MESSAGE_ACTIVITY_DB_USER",
        "MESSAGE_ACTIVITY_DB_PASS",
    ]


def test_automation_conversion_settings_page_shows_real_message_activity_env_names(app, client):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_message_activity_sync_run (
                trigger_source, operator_type, operator_id, status, candidate_count, matched_count, updated_count,
                skipped_ambiguous_count, skipped_unmatched_count, skipped_missing_phone_count, focus_count, normal_count,
                error_message, summary_json, started_at, finished_at
            )
            VALUES (?, ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, ?, '{}', ?, ?)
            """,
            (
                "manual",
                "user",
                "tester",
                "failed",
                "message activity db is not configured",
                "2026-04-07 19:16:56",
                "2026-04-07 19:16:56",
            ),
        )
        db.commit()

    response = client.get("/admin/automation-conversion/settings")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MESSAGE_ACTIVITY_DB_NAME" in html
    assert "MESSAGE_ACTIVITY_DB_PASS" in html
    assert "MESSAGE_ACTIVITY_DB_DATABASE" not in html
    assert "MESSAGE_ACTIVITY_DB_PASSWORD" not in html
    assert "最近一次状态" in html
    assert "未配置" in html
    assert "最近一次同步失败" not in html
    assert ">failed<" not in html


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


def test_qrcode_callback_sends_welcome_message_when_enabled(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion.service import handle_qrcode_enter_from_callback

    captured: dict[str, object] = {}

    def _fake_dispatch(task_type: str, fn_name: str, payload: dict[str, object]) -> dict[str, object]:
        captured["task_type"] = task_type
        captured["fn_name"] = fn_name
        captured["payload"] = dict(payload)
        return {"task_id": 77, "wecom_result": {"msgid": "welcome-msg-001"}}

    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        _fake_dispatch,
    )

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, status, welcome_message, auto_accept_friend, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-default', 'QianLan', 'active', '欢迎添加，稍后我来跟进你。', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_002",
            phone="13800004002",
            payload_json={"state": "scene-default"},
            operator_id="callback-user",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["welcome_message"]["sent"] is True
        assert result["welcome_message"]["task_id"] == 77
        assert captured["task_type"] == "private_message"
        assert captured["fn_name"] == "create_private_message_task"
        assert captured["payload"] == {
            "sender": "QianLan",
            "external_userid": ["wm_qrcode_002"],
            "text": {"content": "欢迎添加，稍后我来跟进你。"},
        }

        events = db.execute(
            "SELECT action, operator_id, remark FROM automation_event ORDER BY id ASC"
        ).fetchall()
        assert [dict(item) for item in events[-2:]] == [
            {
                "action": "qrcode_enter",
                "operator_id": "callback-user",
                "remark": "",
            },
            {
                "action": "qrcode_welcome_sent",
                "operator_id": "callback-user",
                "remark": "task_id=77",
            },
        ]
