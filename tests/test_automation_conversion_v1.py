from __future__ import annotations

import base64
import json
import re
from io import BytesIO

import pytest
import requests

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.automation_conversion.agents.llm_client import (
    DeepSeekClientError,
    call_deepseek_agent,
)
from wecom_ability_service.domains.automation_conversion.service import (
    ensure_sop_v1_defaults,
    get_member_detail,
    get_model_infra_payload,
    record_sop_pool_entry,
    run_due_reply_monitor,
    run_due_sop,
    run_message_activity_sync,
    run_reply_monitor_capture,
    save_model_infra_prompt,
    save_model_infra_settings,
    save_sop_v1_pool_config,
    save_reply_monitor_enabled,
    save_sop_v1_template,
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


class _FakeDeepSeekResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        json_data: dict[str, object] | None = None,
        text: str = "",
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status_code
        self._json_data = dict(json_data or {})
        self.text = text
        self.headers = dict(headers or {})

    def json(self) -> dict[str, object]:
        return dict(self._json_data)


def _configure_reply_monitor(
    app,
    *,
    enabled: bool,
    last_capture_cursor: int = 0,
    last_capture_at: str = "",
    last_capture_status: str = "",
    last_dispatch_at: str = "",
    last_dispatch_status: str = "",
    last_error: str = "",
    quiet_hours_start: str = "23:00",
    quiet_hours_end: str = "09:00",
    dispatch_interval_seconds: int = 30,
) -> None:
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM automation_reply_monitor_config")
        db.execute(
            """
            INSERT INTO automation_reply_monitor_config (
                config_key, enabled, last_capture_cursor, last_capture_at, last_capture_status,
                last_capture_summary_json, last_dispatch_at, last_dispatch_status, last_dispatch_summary_json,
                last_error, quiet_hours_start, quiet_hours_end, dispatch_interval_seconds, created_at, updated_at
            )
            VALUES ('default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                1 if enabled else 0,
                last_capture_cursor,
                last_capture_at,
                last_capture_status,
                json.dumps({}, ensure_ascii=False),
                last_dispatch_at,
                last_dispatch_status,
                json.dumps({}, ensure_ascii=False),
                last_error,
                quiet_hours_start,
                quiet_hours_end,
                dispatch_interval_seconds,
            ),
        )
        db.commit()


def _seed_archived_message(
    app,
    *,
    msgid: str,
    seq: int,
    external_userid: str,
    owner_userid: str,
    sender: str,
    receiver: str = "",
    chat_type: str = "private",
    msgtype: str = "text",
    content: str = "",
    send_time: str = "2026-04-09 10:00:00",
) -> int:
    with app.app_context():
        db = get_db()
        row = db.execute(
            """
            INSERT INTO archived_messages (
                seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                seq,
                msgid,
                chat_type,
                external_userid,
                owner_userid,
                sender,
                receiver,
                msgtype,
                content,
                send_time,
                "{}",
            ),
        ).fetchone()
        db.commit()
        return int(row["id"])


def _patch_reply_monitor_payload_context(monkeypatch, *, external_userid: str, owner_display_name: str = "销售一") -> None:
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload",
        lambda *, external_userid=external_userid: {"tags": [{"tag_name": "高潜客户"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload",
        lambda *, external_userid="", mobile="": {"answers": [{"question": "预算", "answer": "999"}]},
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload",
        lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {
            "messages": [
                {"sender": external_userid, "send_time": "2026-04-09 09:58:00", "content": "你好"},
                {"sender": "sales_01", "send_time": "2026-04-09 09:59:00", "content": "你好，我在"},
            ],
        },
    )


def _configure_sop_pool(
    app,
    *,
    pool_key: str,
    enabled: bool,
    send_time: str = "09:00",
) -> dict[str, object]:
    with app.app_context():
        return save_sop_v1_pool_config(
            pool_key=pool_key,
            enabled=enabled,
            send_time=send_time,
        )


def _configure_only_sop_pool(
    app,
    *,
    pool_key: str,
    send_time: str = "09:00",
) -> None:
    for candidate_pool in ("new_user", "inactive_normal", "active_normal"):
        _configure_sop_pool(
            app,
            pool_key=candidate_pool,
            enabled=candidate_pool == pool_key,
            send_time=send_time if candidate_pool == pool_key else "09:00",
        )


def _set_sop_pool_effective_start(app, *, pool_key: str, effective_start_at: str) -> None:
    with app.app_context():
        get_db().execute(
            """
            UPDATE automation_sop_pool_config
            SET effective_start_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE pool_key = ?
            """,
            (effective_start_at, pool_key),
        )
        get_db().commit()


def _test_png_data_url() -> str:
    encoded = base64.b64encode(_test_png_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _save_sop_template(
    app,
    *,
    pool_key: str,
    day_index: int,
    content: str = "",
    images_json: list[dict[str, object]] | None = None,
    enabled: bool = True,
) -> dict[str, object]:
    with app.app_context():
        return save_sop_v1_template(
            pool_key=pool_key,
            day_index=day_index,
            content=content,
            images_json=list(images_json or []),
            enabled=enabled,
        )


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
            "automation_reply_monitor_config",
            "automation_reply_monitor_queue",
            "automation_focus_send_batch",
            "automation_focus_send_batch_item",
            "automation_sop_pool_config",
            "automation_sop_template",
            "automation_sop_progress",
            "automation_sop_batch",
            "automation_sop_batch_item",
        }.issubset(table_names)
        assert {
            "uq_automation_member_external_non_empty",
            "idx_automation_member_phone",
            "idx_automation_member_pool",
            "idx_automation_event_member_created",
            "idx_automation_ai_push_log_status",
            "idx_automation_message_activity_sync_run_finished",
            "idx_automation_message_activity_sync_item_run",
            "idx_automation_message_activity_sync_item_match_key",
            "idx_automation_reply_monitor_config_updated",
            "idx_automation_reply_monitor_queue_status_due",
            "idx_automation_reply_monitor_queue_external_updated",
            "uq_automation_reply_monitor_queue_active_external",
            "idx_automation_focus_send_batch_stage_status",
            "idx_automation_focus_send_batch_item_batch_position",
            "idx_automation_sop_pool_config_updated",
            "uq_automation_sop_template_pool_day",
            "uq_automation_sop_progress_member_pool",
            "idx_automation_sop_batch_status_scheduled",
            "idx_automation_sop_batch_item_batch_created",
            "uq_automation_sop_batch_item_member_pool_day_success",
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

    settings_page = client.get("/admin/automation-conversion/settings", follow_redirects=True)
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
            {"phone_prefix3": "138", "phone_last4": "1231", "phone_match_key": "138_1231", "message_count": 15},
            {"phone_prefix3": "138", "phone_last4": "1232", "phone_match_key": "138_1232", "message_count": 10},
            {"phone_prefix3": "138", "phone_last4": "1233", "phone_match_key": "138_1233", "message_count": 1},
            {"phone_prefix3": "138", "phone_last4": "1234", "phone_match_key": "138_1234", "message_count": 0},
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
            {"phone_prefix3": "138", "phone_last4": "2221", "phone_match_key": "138_2221", "message_count": 20},
            {"phone_prefix3": "138", "phone_last4": "2222", "phone_match_key": "138_2222", "message_count": 0},
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
            {"phone_prefix3": "138", "phone_last4": "2441", "phone_match_key": "138_2441", "message_count": 1},
            {"phone_prefix3": "138", "phone_last4": "2442", "phone_match_key": "138_2442", "message_count": 0},
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
        ("wm_skip_sync_002", "13899993331"),
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
            {"phone_prefix3": "138", "phone_last4": "3331", "phone_match_key": "138_3331", "message_count": 9},
            {"phone_prefix3": "138", "phone_last4": "3332", "phone_match_key": "138_3332", "message_count": 3},
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
            "detail": "phone_match_key=138_3331 matched multiple automation members: wm_skip_sync_001,wm_skip_sync_002",
        },
        {
            "external_contact_id": "wm_skip_sync_002",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_3331 matched multiple automation members: wm_skip_sync_001,wm_skip_sync_002",
        },
        {
            "external_contact_id": "wm_skip_sync_004",
            "status": "skipped_unmatched",
            "detail": "phone_match_key=138_3339 not found in message activity source",
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


def test_message_activity_sync_requires_same_prefix3_and_last4(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_match_sync_001", mobile="13800005555", owner_userid="sales_match", customer_name="match")
    _seed_automation_member(
        app,
        external_contact_id="wm_match_sync_001",
        phone="13800005555",
        owner_staff_id="sales_match",
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
            {"phone_prefix3": "139", "phone_last4": "5555", "phone_match_key": "139_5555", "message_count": 20},
            {"phone_prefix3": "138", "phone_last4": "5555", "phone_match_key": "138_5555", "message_count": 20},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        row = get_db().execute(
            """
            SELECT activation_status, follow_type, current_pool
            FROM automation_member
            WHERE external_contact_id = 'wm_match_sync_001'
            """
        ).fetchone()

    assert payload["ok"] is True
    assert payload["run"]["matched_count"] == 1
    assert dict(row) == {
        "activation_status": "active",
        "follow_type": "focus",
        "current_pool": "active_focus",
    }


def test_message_activity_sync_same_last4_different_prefix_does_not_match(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_last4_sync_001", mobile="13800006666", owner_userid="sales_last4", customer_name="last4")
    _seed_automation_member(
        app,
        external_contact_id="wm_last4_sync_001",
        phone="13800006666",
        owner_staff_id="sales_last4",
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
            {"phone_prefix3": "139", "phone_last4": "6666", "phone_match_key": "139_6666", "message_count": 9},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        item = get_db().execute(
            """
            SELECT status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (payload["run"]["id"],),
        ).fetchone()

    assert payload["ok"] is True
    assert payload["run"]["matched_count"] == 0
    assert dict(item) == {
        "status": "skipped_unmatched",
        "detail": "phone_match_key=138_6666 not found in message activity source",
    }


def test_message_activity_sync_skips_same_phone_match_key_as_ambiguous(app, monkeypatch):
    _configure_message_activity_db(app)
    for external_userid, mobile in [
        ("wm_key_sync_001", "13800007777"),
        ("wm_key_sync_002", "13899997777"),
    ]:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_key", customer_name=external_userid)
        _seed_automation_member(
            app,
            external_contact_id=external_userid,
            phone=mobile,
            owner_staff_id="sales_key",
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
            {"phone_prefix3": "138", "phone_last4": "7777", "phone_match_key": "138_7777", "message_count": 6},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        items = get_db().execute(
            """
            SELECT external_contact_id, status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY external_contact_id ASC
            """,
            (payload["run"]["id"],),
        ).fetchall()

    assert payload["ok"] is True
    assert payload["run"]["skipped_ambiguous_count"] == 2
    assert [dict(item) for item in items] == [
        {
            "external_contact_id": "wm_key_sync_001",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_7777 matched multiple automation members: wm_key_sync_001,wm_key_sync_002",
        },
        {
            "external_contact_id": "wm_key_sync_002",
            "status": "skipped_ambiguous",
            "detail": "phone_match_key=138_7777 matched multiple automation members: wm_key_sync_001,wm_key_sync_002",
        },
    ]


def test_message_activity_sync_skips_invalid_short_phone(app, monkeypatch):
    _configure_message_activity_db(app)
    _seed_contact(app, external_userid="wm_short_sync_001", mobile="123456", owner_userid="sales_short", customer_name="short-phone")
    _seed_automation_member(
        app,
        external_contact_id="wm_short_sync_001",
        phone="123456",
        owner_staff_id="sales_short",
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
            {"phone_prefix3": "123", "phone_last4": "3456", "phone_match_key": "123_3456", "message_count": 20},
        ],
    )

    with app.app_context():
        payload = run_message_activity_sync(operator_id="tester-message-sync", operator_type="user", trigger_source="manual")
        item = get_db().execute(
            """
            SELECT status, detail
            FROM automation_message_activity_sync_item
            WHERE run_id = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (payload["run"]["id"],),
        ).fetchone()

    assert payload["ok"] is True
    assert payload["run"]["skipped_missing_phone_count"] == 1
    assert dict(item) == {
        "status": "skipped_missing_phone",
        "detail": "member phone is empty or shorter than 7 digits, cannot build phone_match_key",
    }


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
        lambda: [{"phone_prefix3": "138", "phone_last4": "4441", "phone_match_key": "138_4441", "message_count": 5}],
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


def test_automation_conversion_settings_page_focuses_on_flow_design_sections(app, client):
    response = client.get("/admin/automation-conversion/settings", follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "流程设计" in html
    assert "阶段模型" in html
    assert "入池与问卷规则" in html
    assert "SOP 剧本" in html
    assert "全局规则" in html
    assert "默认渠道入口" in html
    assert "发布管理" in html
    assert "立即刷新一次" not in html
    assert "消息活跃同步已迁到运行中心" in html
    assert "前往运行中心校验" in html


def test_legacy_admin_automation_conversion_routes_redirect_to_new_workspaces(app, client):
    settings = client.get("/admin/automation-conversion/settings", query_string={"saved": 1})
    assert settings.status_code == 302
    assert "/admin/automation-conversion/flow-design" in settings.headers["Location"]
    assert "section=questionnaire" in settings.headers["Location"]
    assert "saved=1" in settings.headers["Location"]

    sop = client.get("/admin/automation-conversion/sop", query_string={"pool": "inactive_normal", "day": 1})
    assert sop.status_code == 302
    assert "/admin/automation-conversion/flow-design" in sop.headers["Location"]
    assert "section=sop" in sop.headers["Location"]
    assert "pool=inactive_normal" in sop.headers["Location"]
    assert "day=1" in sop.headers["Location"]

    stage = client.get(
        "/admin/automation-conversion/stage/new-user",
        query_string={"keyword": "abc", "external_contact_id": "wm_legacy_stage_001"},
    )
    assert stage.status_code == 302
    assert "/admin/automation-conversion/member-ops" in stage.headers["Location"]
    assert "stage=new-user" in stage.headers["Location"]
    assert "panel=members" in stage.headers["Location"]
    assert "keyword=abc" in stage.headers["Location"]
    assert "external_contact_id=wm_legacy_stage_001" in stage.headers["Location"]

    stage_send = client.get(
        "/admin/automation-conversion/stage/active-focus/send",
        query_string={"phone": "13800001234"},
    )
    assert stage_send.status_code == 302
    assert "/admin/automation-conversion/member-ops" in stage_send.headers["Location"]
    assert "stage=active-focus" in stage_send.headers["Location"]
    assert "panel=send" in stage_send.headers["Location"]
    assert "phone=13800001234" in stage_send.headers["Location"]

    model_infra = client.get("/admin/automation-conversion/model-infra", query_string={"tested": 1})
    assert model_infra.status_code == 302
    assert "/admin/automation-conversion/run-center" in model_infra.headers["Location"]
    assert "tab=model-infra" in model_infra.headers["Location"]
    assert "tested=1" in model_infra.headers["Location"]

    debug = client.get("/admin/automation-conversion/debug", query_string={"external_contact_id": "wm_debug_001"})
    assert debug.status_code == 302
    assert "/admin/automation-conversion/run-center" in debug.headers["Location"]
    assert "tab=debug" in debug.headers["Location"]
    assert "external_contact_id=wm_debug_001" in debug.headers["Location"]


def test_admin_automation_conversion_save_settings_redirects_back_to_current_flow_design_section(app, client, monkeypatch):
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.save_settings", lambda payload: payload)
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={"section": "global-rules"},
    )

    assert response.status_code == 302
    assert "/admin/automation-conversion/flow-design" in response.headers["Location"]
    assert "section=global-rules" in response.headers["Location"]
    assert "saved=1" in response.headers["Location"]


def test_admin_automation_conversion_save_settings_error_keeps_current_flow_design_section(app, client, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.save_settings",
        lambda payload: (_ for _ in ()).throw(ValueError("保存失败")),
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={"section": "channel", "welcome_message": "保留输入"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "保存失败" in html
    assert "保留输入" in html
    assert 'href="/admin/automation-conversion/flow-design?section=channel#flow-channel">默认渠道入口</a>' in html
    assert 'ac-section-link is-active' in html


def test_admin_automation_conversion_save_settings_requires_action_token_and_keeps_section(app, client):
    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={"section": "channel", "welcome_message": "未提交成功"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "后台动作令牌无效，请刷新页面后重试" in html
    assert "未提交成功" in html
    assert 'href="/admin/automation-conversion/flow-design?section=channel#flow-channel">默认渠道入口</a>' in html


def test_admin_generate_default_channel_error_keeps_channel_section(app, client, monkeypatch):
    monkeypatch.setattr(
        "wecom_ability_service.http.automation_conversion.generate_default_channel_qr",
        lambda operator: {"generated": False, "error": "二维码生成失败"},
    )
    monkeypatch.setattr("wecom_ability_service.http.automation_conversion.validate_admin_console_action_token", lambda: "")

    response = client.post("/admin/automation-conversion/settings/default-channel/generate")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "二维码生成失败" in html
    assert 'href="/admin/automation-conversion/flow-design?section=channel#flow-channel">默认渠道入口</a>' in html
    assert 'ac-section-link is-active' in html


def test_admin_generate_default_channel_requires_action_token(app, client):
    response = client.post("/admin/automation-conversion/settings/default-channel/generate")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "后台动作令牌无效，请刷新页面后重试" in html
    assert 'href="/admin/automation-conversion/flow-design?section=channel#flow-channel">默认渠道入口</a>' in html


def test_model_infra_settings_save_and_mask_deepseek_api_key(app, client):
    response = client.post(
        "/api/admin/automation-conversion/model-infra/settings",
        json={
            "enabled": True,
            "api_key": "dsk-automation-secret-12345",
            "base_url": "https://api.deepseek.com",
            "router_model": "deepseek-router-x",
            "execution_model": "deepseek-execution-x",
            "timeout_seconds": 45,
        },
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["model_infra"]["deepseek"] == {
        "enabled": True,
        "api_key_configured": True,
        "api_key_masked": "dsk***45",
        "base_url": "https://api.deepseek.com",
        "router_model": "deepseek-router-x",
        "execution_model": "deepseek-execution-x",
        "timeout_seconds": 45,
        "updated_at": payload["model_infra"]["deepseek"]["updated_at"],
    }

    with app.app_context():
        stored_key = get_db().execute(
            "SELECT value FROM app_settings WHERE key = 'DEEPSEEK_API_KEY'"
        ).fetchone()["value"]
        assert stored_key == "dsk-automation-secret-12345"

    page = client.get("/admin/automation-conversion/model-infra", follow_redirects=True)
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    assert "DeepSeek 配置" in html
    assert "dsk-automation-secret-12345" not in html
    assert "dsk***45" in html


def test_model_infra_prompt_registry_seeds_and_saves_all_agent_prompts(app):
    expected_codes = [
        "central_router_agent",
        "welcome_agent",
        "pricing_agent",
        "proof_agent",
        "closing_agent",
    ]

    with app.app_context():
        initial_payload = get_model_infra_payload()
        assert [item["agent_code"] for item in initial_payload["prompts"]] == expected_codes

        saved_prompts = {}
        for agent_code in expected_codes:
            saved_prompts[agent_code] = save_model_infra_prompt(
                agent_code=agent_code,
                display_name=f"{agent_code}-display",
                prompt_text=f"{agent_code} prompt text v2",
                enabled=agent_code != "proof_agent",
            )

        payload = get_model_infra_payload()
        rows = get_db().execute(
            "SELECT agent_code, display_name, prompt_text, enabled, version FROM automation_agent_prompt_registry ORDER BY agent_code ASC"
        ).fetchall()

    prompt_map = {item["agent_code"]: item for item in payload["prompts"]}
    assert set(prompt_map.keys()) == set(expected_codes)
    assert len(rows) == 5
    for agent_code in expected_codes:
        assert saved_prompts[agent_code]["agent_code"] == agent_code
        assert saved_prompts[agent_code]["display_name"] == f"{agent_code}-display"
        assert saved_prompts[agent_code]["prompt_text"] == f"{agent_code} prompt text v2"
        assert saved_prompts[agent_code]["enabled"] is (agent_code != "proof_agent")
        assert saved_prompts[agent_code]["version"] == 2
        assert prompt_map[agent_code]["prompt_text"] == f"{agent_code} prompt text v2"


def test_deepseek_llm_client_success_logs_and_parses_json(app, monkeypatch):
    captured: dict[str, object] = {}

    def _fake_post(url, headers=None, json=None, timeout=None):
        captured.update(
            {
                "url": url,
                "headers": dict(headers or {}),
                "json": dict(json or {}),
                "timeout": timeout,
            }
        )
        return _FakeDeepSeekResponse(
            headers={"x-request-id": "deepseek-req-001"},
            json_data={
                "choices": [
                    {
                        "message": {
                            "content": json_module.dumps({"route": "welcome_agent", "confidence": 0.91})
                        }
                    }
                ]
            },
        )

    json_module = json
    monkeypatch.setattr("requests.post", _fake_post)

    with app.app_context():
        save_model_infra_settings(
            {
                "enabled": True,
                "api_key": "dsk-routing-key-556677",
                "base_url": "https://api.deepseek.com",
                "router_model": "deepseek-router-v1",
                "execution_model": "deepseek-execution-v1",
                "timeout_seconds": 21,
            }
        )
        result = call_deepseek_agent(
            agent_code="central_router_agent",
            system_prompt="router system prompt",
            user_input="客户刚回复了价格问题",
            json_output=True,
        )
        row = get_db().execute(
            """
            SELECT agent_code, model_name, request_id, status, latency_ms, error_message
            FROM automation_agent_llm_call_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert result["ok"] is True
    assert result["request_id"] == "deepseek-req-001"
    assert result["model_name"] == "deepseek-router-v1"
    assert result["parsed_output"] == {"route": "welcome_agent", "confidence": 0.91}
    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer dsk-routing-key-556677"
    assert captured["json"]["model"] == "deepseek-router-v1"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["timeout"] == 21
    assert dict(row)["status"] == "success"
    assert dict(row)["agent_code"] == "central_router_agent"
    assert dict(row)["model_name"] == "deepseek-router-v1"
    assert dict(row)["request_id"] == "deepseek-req-001"
    assert dict(row)["error_message"] == ""


def test_deepseek_llm_client_request_error_is_logged(app, monkeypatch):
    monkeypatch.setattr(
        "requests.post",
        lambda *args, **kwargs: (_ for _ in ()).throw(requests.RequestException("deepseek request timeout")),
    )

    with app.app_context():
        save_model_infra_settings(
            {
                "enabled": True,
                "api_key": "dsk-execution-key-778899",
                "base_url": "https://api.deepseek.com",
                "router_model": "deepseek-router-v2",
                "execution_model": "deepseek-execution-v2",
                "timeout_seconds": 18,
            }
        )
        with pytest.raises(DeepSeekClientError, match="deepseek request timeout"):
            call_deepseek_agent(
                agent_code="pricing_agent",
                system_prompt="pricing system prompt",
                user_input="给我价格说明",
                json_output=False,
            )
        row = get_db().execute(
            """
            SELECT agent_code, model_name, status, error_message
            FROM automation_agent_llm_call_log
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()

    assert dict(row) == {
        "agent_code": "pricing_agent",
        "model_name": "deepseek-execution-v2",
        "status": "request_error",
        "error_message": "deepseek request timeout",
    }


def test_model_infra_page_renders_and_homepage_keeps_existing_sections(app, client):
    model_infra_page = client.get("/admin/automation-conversion/model-infra", follow_redirects=True)
    model_infra_html = model_infra_page.get_data(as_text=True)

    assert model_infra_page.status_code == 200
    assert "DeepSeek 配置" in model_infra_html
    assert "Prompt Registry" in model_infra_html
    assert "中央路由 Agent" in model_infra_html
    assert "欢迎接待 Agent" in model_infra_html
    assert "最近模型调用日志" in model_infra_html
    assert "最近执行结果" not in model_infra_html

    home_page = client.get("/admin/automation-conversion")
    home_html = home_page.get_data(as_text=True)

    assert home_page.status_code == 200
    assert "模型基础设施" in home_html
    assert "消息活跃同步" in home_html
    assert "自动接话监控" in home_html


def test_automation_conversion_home_stage_cards_show_view_and_send_actions(app, client):
    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "消息活跃同步" in html
    assert "立即刷新一次" not in html
    assert 'data-message-activity-sync-root' not in html
    assert 'data-message-activity-sync-button' not in html
    assert "阶段漏斗" in html
    assert html.count("进入成员运营") == 7
    assert "创建群发" not in html


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
        lambda: [{"phone_prefix3": "138", "phone_last4": "9441", "phone_match_key": "138_9441", "message_count": 6}],
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
    assert "运行摘要" in html
    assert "消息活跃同步" in html
    assert "最近时间：2026-04-08 10:30:00" in html
    assert "异常：无" in html


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
        lambda: [{"phone_prefix3": "138", "phone_last4": "9442", "phone_match_key": "138_9442", "message_count": 8}],
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


def test_automation_conversion_home_page_renders_reply_monitor_section(app, client):
    _configure_reply_monitor(app, enabled=False)

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动接话监控" in html
    assert "已关闭" in html
    assert "开启监控" not in html
    assert "立即扫描一次" not in html
    assert "立即放行一条" not in html


def test_reply_monitor_capture_filters_private_inbound_messages_and_groups_by_user(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_001", mobile="13800009101", owner_userid="sales_01", customer_name="reply-1")
    _seed_contact(app, external_userid="wm_reply_002", mobile="13800009102", owner_userid="sales_01", customer_name="reply-2")
    _seed_contact(app, external_userid="wm_reply_003", mobile="13800009103", owner_userid="sales_01", customer_name="reply-3")
    _seed_automation_member(app, external_contact_id="wm_reply_001", phone="13800009101", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_result="focus", decision_source="questionnaire")
    _seed_automation_member(app, external_contact_id="wm_reply_002", phone="13800009102", owner_staff_id="sales_01", current_pool="active_normal", follow_type="normal", activation_status="active", questionnaire_result="normal", decision_source="questionnaire")

    _seed_archived_message(app, msgid="msg-rm-001", seq=1, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", content="你好 1", send_time="2026-04-09 10:00:01")
    _seed_archived_message(app, msgid="msg-rm-002", seq=2, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", content="你好 2", send_time="2026-04-09 10:00:02")
    _seed_archived_message(app, msgid="msg-rm-003", seq=3, external_userid="wm_reply_001", owner_userid="sales_01", sender="sales_01", receiver="wm_reply_001", content="客服回复", send_time="2026-04-09 10:00:03")
    _seed_archived_message(app, msgid="msg-rm-004", seq=4, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", chat_type="group", content="群聊消息", send_time="2026-04-09 10:00:04")
    _seed_archived_message(app, msgid="msg-rm-005", seq=5, external_userid="wm_reply_001", owner_userid="sales_01", sender="wm_reply_001", receiver="sales_01", msgtype="event", content="系统事件", send_time="2026-04-09 10:00:05")
    _seed_archived_message(app, msgid="msg-rm-006", seq=6, external_userid="wm_reply_002", owner_userid="sales_01", sender="wm_reply_002", receiver="sales_01", content="另一个客户", send_time="2026-04-09 10:00:06")
    _seed_archived_message(app, msgid="msg-rm-007", seq=7, external_userid="wm_reply_003", owner_userid="sales_01", sender="wm_reply_003", receiver="sales_01", content="非自动化用户", send_time="2026-04-09 10:00:07")

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:05:00")

    with app.app_context():
        payload = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        queue_rows = get_db().execute(
            """
            SELECT external_userid, owner_userid, status, message_count, message_ids_json
            FROM automation_reply_monitor_queue
            ORDER BY external_userid ASC
            """
        ).fetchall()

    assert payload["ok"] is True
    assert payload["summary"] == {
        "cursor_from": 0,
        "cursor_to": 7,
        "scanned_new_messages": 7,
        "candidate_messages": 4,
        "hit_users": 2,
        "created_queue_items": 2,
        "merged_queue_items": 0,
    }
    assert [dict(row) for row in queue_rows] == [
        {
            "external_userid": "wm_reply_001",
            "owner_userid": "sales_01",
            "status": "pending",
            "message_count": 2,
            "message_ids_json": json.dumps([1, 2]),
        },
        {
            "external_userid": "wm_reply_002",
            "owner_userid": "sales_01",
            "status": "pending",
            "message_count": 1,
            "message_ids_json": json.dumps([6]),
        },
    ]


def test_reply_monitor_capture_merges_new_messages_into_existing_pending_item(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_merge_001", mobile="13800009111", owner_userid="sales_01", customer_name="reply-merge")
    _seed_automation_member(app, external_contact_id="wm_reply_merge_001", phone="13800009111", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_result="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-merge-001", seq=1, external_userid="wm_reply_merge_001", owner_userid="sales_01", sender="wm_reply_merge_001", receiver="sales_01", content="第一条", send_time="2026-04-09 10:00:01")

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:01:00")
    with app.app_context():
        first = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
    assert first["summary"]["created_queue_items"] == 1

    _seed_archived_message(app, msgid="msg-rm-merge-002", seq=2, external_userid="wm_reply_merge_001", owner_userid="sales_01", sender="wm_reply_merge_001", receiver="sales_01", content="第二条", send_time="2026-04-09 10:02:01")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:03:00")

    with app.app_context():
        second = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        row = get_db().execute(
            """
            SELECT status, message_count, message_ids_json
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            ("wm_reply_merge_001",),
        ).fetchone()

    assert second["summary"]["created_queue_items"] == 0
    assert second["summary"]["merged_queue_items"] == 1
    assert dict(row) == {
        "status": "pending",
        "message_count": 2,
        "message_ids_json": json.dumps([1, 2]),
    }


def test_reply_monitor_capture_and_dispatch_respect_quiet_hours(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_quiet_001", mobile="13800009121", owner_userid="sales_01", customer_name="reply-quiet")
    _seed_automation_member(app, external_contact_id="wm_reply_quiet_001", phone="13800009121", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_result="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-quiet-001", seq=1, external_userid="wm_reply_quiet_001", owner_userid="sales_01", sender="wm_reply_quiet_001", receiver="sales_01", content="夜间消息", send_time="2026-04-09 23:14:00")

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 23:15:00")
    sent_payloads: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook",
        lambda **kwargs: sent_payloads.append(kwargs) or {"ok": True, "delivery": {"id": 9001}},
    )

    with app.app_context():
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        queue_row = get_db().execute(
            """
            SELECT status, not_before, message_count
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            """,
            ("wm_reply_quiet_001",),
        ).fetchone()
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="user")

    assert capture["ok"] is True
    assert dict(queue_row) == {
        "status": "deferred_quiet_hours",
        "not_before": "2026-04-10 09:00:00",
        "message_count": 1,
    }
    assert dispatch["ok"] is True
    assert dispatch["status"] == "quiet_hours"
    assert dispatch["summary"]["deferred_count"] == 0
    assert sent_payloads == []


def test_reply_monitor_dispatch_releases_due_items_one_by_one_with_30_second_gap(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0, dispatch_interval_seconds=30)
    for external_userid, mobile in [("wm_reply_due_001", "13800009131"), ("wm_reply_due_002", "13800009132")]:
        _seed_contact(app, external_userid=external_userid, mobile=mobile, owner_userid="sales_01", customer_name=external_userid)
        _seed_automation_member(app, external_contact_id=external_userid, phone=mobile, owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_result="focus", decision_source="manual")
    _seed_archived_message(app, msgid="msg-rm-due-001", seq=1, external_userid="wm_reply_due_001", owner_userid="sales_01", sender="wm_reply_due_001", receiver="sales_01", content="白天发送一", send_time="2026-04-09 23:29:01")
    _seed_archived_message(app, msgid="msg-rm-due-002", seq=2, external_userid="wm_reply_due_002", owner_userid="sales_01", sender="wm_reply_due_002", receiver="sales_01", content="白天发送二", send_time="2026-04-09 23:29:02")
    _patch_reply_monitor_payload_context(monkeypatch, external_userid="wm_reply_due_001")
    dispatched_payloads: list[dict[str, object]] = []

    def _fake_send_outbound_webhook(*, event_type, payload, source_key, source_id):
        dispatched_payloads.append({"event_type": event_type, "payload": payload, "source_id": source_id})
        return {"ok": True, "delivery": {"id": 9100 + len(dispatched_payloads)}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook", _fake_send_outbound_webhook)

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 23:30:00")
    with app.app_context():
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        queued = get_db().execute(
            """
            SELECT external_userid, status, not_before
            FROM automation_reply_monitor_queue
            ORDER BY id ASC
            """
        ).fetchall()
    assert capture["summary"]["created_queue_items"] == 2
    assert [dict(item) for item in queued] == [
        {"external_userid": "wm_reply_due_001", "status": "deferred_quiet_hours", "not_before": "2026-04-10 09:00:00"},
        {"external_userid": "wm_reply_due_002", "status": "deferred_quiet_hours", "not_before": "2026-04-10 09:00:30"},
    ]

    monkeypatch.setattr("wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_profile_tags_payload", lambda *, external_userid: {"tags": [{"tag_name": "高潜客户"}]})
    monkeypatch.setattr("wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_questionnaire_answers_payload", lambda *, external_userid="", mobile="": {"answers": [{"question": "预算", "answer": "999"}]})
    monkeypatch.setattr("wecom_ability_service.domains.admin_console.customer_profile_service.get_customer_messages_payload", lambda *, external_userid="", mobile="", limit=20, fetch_all=False: {"messages": []})

    with app.app_context():
        monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:00")
        first = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:10")
        throttled = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")
        monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:00:31")
        second = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")

    assert first["ok"] is True
    assert first["status"] == "success"
    assert throttled["ok"] is True
    assert throttled["status"] == "throttled"
    assert second["ok"] is True
    assert second["status"] == "success"
    assert len(dispatched_payloads) == 2


def test_reply_monitor_disabled_does_not_create_queue_items(app):
    _configure_reply_monitor(app, enabled=False, last_capture_cursor=0)
    _seed_archived_message(app, msgid="msg-rm-disabled-001", seq=1, external_userid="wm_reply_disabled_001", owner_userid="sales_01", sender="wm_reply_disabled_001", receiver="sales_01", content="消息仍然入库", send_time="2026-04-09 10:10:00")

    with app.app_context():
        payload = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        archived_count = get_db().execute("SELECT COUNT(*) AS count FROM archived_messages").fetchone()["count"]
        queue_count = get_db().execute("SELECT COUNT(*) AS count FROM automation_reply_monitor_queue").fetchone()["count"]

    assert payload["status"] == "disabled"
    assert archived_count == 1
    assert queue_count == 0


def test_reply_monitor_reenable_starts_from_current_cursor_without_history_replay(app, monkeypatch):
    _seed_archived_message(app, msgid="msg-rm-reenable-001", seq=1, external_userid="wm_reply_reenable_001", owner_userid="sales_01", sender="wm_reply_reenable_001", receiver="sales_01", content="旧消息", send_time="2026-04-09 09:00:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:00:00")

    with app.app_context():
        enabled_payload = save_reply_monitor_enabled(enabled=True, operator_id="tester-reply-monitor")
        assert enabled_payload["enabled"] is True
        first_capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")

    assert first_capture["summary"]["scanned_new_messages"] == 0

    _seed_contact(app, external_userid="wm_reply_reenable_001", mobile="13800009141", owner_userid="sales_01", customer_name="reenable")
    _seed_automation_member(app, external_contact_id="wm_reply_reenable_001", phone="13800009141", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_result="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-reenable-002", seq=2, external_userid="wm_reply_reenable_001", owner_userid="sales_01", sender="wm_reply_reenable_001", receiver="sales_01", content="新消息", send_time="2026-04-09 10:02:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:03:00")

    with app.app_context():
        second_capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")

    assert second_capture["summary"]["scanned_new_messages"] == 1
    assert second_capture["summary"]["created_queue_items"] == 1


def test_reply_monitor_capture_uses_storage_cursor_instead_of_send_time(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_cursor_001", mobile="13800009151", owner_userid="sales_01", customer_name="cursor")
    _seed_automation_member(app, external_contact_id="wm_reply_cursor_001", phone="13800009151", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_result="focus", decision_source="questionnaire")
    _seed_archived_message(app, msgid="msg-rm-cursor-001", seq=1, external_userid="wm_reply_cursor_001", owner_userid="sales_01", sender="wm_reply_cursor_001", receiver="sales_01", content="较新 send_time", send_time="2026-04-09 10:05:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:06:00")

    with app.app_context():
        first = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
    assert first["summary"]["created_queue_items"] == 1

    _seed_archived_message(app, msgid="msg-rm-cursor-002", seq=2, external_userid="wm_reply_cursor_001", owner_userid="sales_01", sender="wm_reply_cursor_001", receiver="sales_01", content="晚到但 send_time 更早", send_time="2026-04-09 10:01:00")
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:07:00")

    with app.app_context():
        second = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        row = get_db().execute(
            """
            SELECT message_count, message_ids_json
            FROM automation_reply_monitor_queue
            WHERE external_userid = ?
            """,
            ("wm_reply_cursor_001",),
        ).fetchone()

    assert second["summary"]["scanned_new_messages"] == 1
    assert second["summary"]["merged_queue_items"] == 1
    assert dict(row) == {
        "message_count": 2,
        "message_ids_json": json.dumps([1, 2]),
    }


def test_reply_monitor_dispatch_payload_contains_required_fields(app, monkeypatch):
    _configure_reply_monitor(app, enabled=True, last_capture_cursor=0)
    _seed_contact(app, external_userid="wm_reply_payload_001", mobile="13800009161", owner_userid="sales_01", customer_name="payload")
    _seed_automation_member(app, external_contact_id="wm_reply_payload_001", phone="13800009161", owner_staff_id="sales_01", current_pool="active_focus", follow_type="focus", activation_status="active", questionnaire_result="focus", decision_source="manual")
    _seed_archived_message(app, msgid="msg-rm-payload-001", seq=1, external_userid="wm_reply_payload_001", owner_userid="sales_01", sender="wm_reply_payload_001", receiver="sales_01", content="我要继续了解", send_time="2026-04-09 10:20:00")
    _patch_reply_monitor_payload_context(monkeypatch, external_userid="wm_reply_payload_001")
    captured: dict[str, object] = {}

    def _fake_send_outbound_webhook(*, event_type, payload, source_key, source_id):
        captured.update({
            "event_type": event_type,
            "payload": payload,
            "source_key": source_key,
            "source_id": source_id,
        })
        return {"ok": True, "delivery": {"id": 9201}}

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service.send_outbound_webhook", _fake_send_outbound_webhook)
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 10:21:00")

    with app.app_context():
        capture = run_reply_monitor_capture(operator_id="tester-reply-monitor", operator_type="user")
        dispatch = run_due_reply_monitor(operator_id="tester-reply-monitor", operator_type="system")

    assert capture["ok"] is True
    assert dispatch["ok"] is True
    assert captured["event_type"] == "openclaw_focus_message"
    assert captured["source_key"] == "automation_reply_monitor_queue"
    assert set(captured["payload"].keys()) >= {
        "externalContactId",
        "external_userid",
        "owner_userid",
        "owner_display_name",
        "currentPool",
        "currentStage",
        "currentTarget",
        "newMessages",
        "aggregation_window",
        "trigger_type",
        "queueId",
        "dedupeKey",
    }
    assert captured["payload"]["external_userid"] == "wm_reply_payload_001"
    assert captured["payload"]["owner_userid"] == "sales_01"
    assert captured["payload"]["trigger_type"] == "reply_monitor"
    assert captured["payload"]["newMessages"] == [
        {
            "storage_id": 1,
            "msgid": "msg-rm-payload-001",
            "msgtype": "text",
            "content": "我要继续了解",
            "send_time": "2026-04-09 10:20:00",
            "sender": "wm_reply_payload_001",
            "receiver": "sales_01",
        }
    ]


def test_process_inbound_messages_for_openclaw_skips_automation_scope_users(app, monkeypatch):
    from wecom_ability_service.domains.marketing_automation.service import process_inbound_messages_for_openclaw

    _seed_contact(app, external_userid="wm_reply_scope_001", mobile="13800009171", owner_userid="sales_01", customer_name="scope-1")
    _seed_contact(app, external_userid="wm_reply_scope_002", mobile="13800009172", owner_userid="sales_01", customer_name="scope-2")
    _seed_automation_member(app, external_contact_id="wm_reply_scope_001", phone="13800009171", owner_staff_id="sales_01", current_pool="inactive_focus", follow_type="focus", activation_status="inactive", questionnaire_result="focus", decision_source="questionnaire")

    triggered: list[str] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.marketing_automation.service.trigger_openclaw_focus_message_webhook",
        lambda *, external_userid: triggered.append(external_userid) or {"sent": True, "external_userid": external_userid},
    )

    with app.app_context():
        result = process_inbound_messages_for_openclaw(
            [
                {
                    "external_userid": "wm_reply_scope_001",
                    "chat_type": "private",
                    "sender": "wm_reply_scope_001",
                    "send_time": "2026-04-09 10:30:00",
                },
                {
                    "external_userid": "wm_reply_scope_002",
                    "chat_type": "private",
                    "sender": "wm_reply_scope_002",
                    "send_time": "2026-04-09 10:31:00",
                },
            ]
        )

    assert triggered == ["wm_reply_scope_002"]
    assert result["processed_count"] == 1
    assert result["skipped_automation_scope_count"] == 1


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

    response = client.get("/admin/automation-conversion/stage/new-user", follow_redirects=True)
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "创建群发" in html
    assert '<div class="admin-card-label">总人数</div>' in html
    assert '<div class="admin-card-label">今日新增</div>' in html
    assert '<div class="admin-card-label">重点跟进</div>' not in html
    assert '<div class="admin-card-label">普通跟进</div>' not in html


def test_member_ops_page_renders_business_detail_sidebar_with_member_query(app, client):
    _seed_contact(app, external_userid="wm_member_ops_001", mobile="13800009131", owner_userid="sales_member", customer_name="成员运营客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_member_ops_001",
        phone="13800009131",
        owner_staff_id="sales_member",
        current_pool="active_normal",
        follow_type="normal",
        activation_status="active",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="system",
    )

    client.post(
        "/api/admin/automation-conversion/member/set-focus",
        json={"external_contact_id": "wm_member_ops_001", "operator": "tester-member-ops"},
    )

    response = client.get(
        "/admin/automation-conversion/member-ops",
        query_string={"stage": "active-focus", "panel": "members", "member": "wm_member_ops_001"},
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "成员列表工作区" in html
    assert "问卷与规则信息" in html
    assert "最近业务事件" in html
    assert "单客动作" in html
    assert "当前分层原因 / 说明" in html
    assert "set_focus" in html
    assert "member=wm_member_ops_001" in html


def test_automation_conversion_stage_send_page_switches_between_manual_and_focus_modes(app, client):
    normal_response = client.get("/admin/automation-conversion/stage/new-user/send", follow_redirects=True)
    focus_response = client.get("/admin/automation-conversion/stage/inactive-focus/send", follow_redirects=True)

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


def test_member_ops_send_panel_contains_batch_placeholder_actions_for_both_modes(app, client):
    normal_response = client.get("/admin/automation-conversion/member-ops", query_string={"stage": "new-user", "panel": "send"})
    focus_response = client.get("/admin/automation-conversion/member-ops", query_string={"stage": "inactive-focus", "panel": "send"})

    normal_html = normal_response.get_data(as_text=True)
    focus_html = focus_response.get_data(as_text=True)

    assert normal_response.status_code == 200
    assert "批量状态动作" in normal_html
    assert "官方群发" in normal_html
    assert "AI 批量处理" not in normal_html

    assert focus_response.status_code == 200
    assert "批量状态动作" in focus_html
    assert "AI 批量处理" in focus_html


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

    redirect_response = client.post(
        "/admin/automation-conversion/stage/new-user/send",
        data=_build_stage_send_form_data(
            content="页面触达",
            operator="tester",
            images=[("page.png", _test_png_bytes(), "image/png")],
        ),
        content_type="multipart/form-data",
    )
    assert redirect_response.status_code == 302
    assert "/admin/automation-conversion/member-ops" in redirect_response.headers["Location"]
    assert "stage=new-user" in redirect_response.headers["Location"]
    assert "panel=send" in redirect_response.headers["Location"]
    assert "manual_send_notice=sent" in redirect_response.headers["Location"]

    response = client.get(redirect_response.headers["Location"])
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

    redirect_response = client.post(
        "/admin/automation-conversion/stage/inactive-focus/send",
        data={"operator": "tester"},
    )
    assert redirect_response.status_code == 302
    assert "/admin/automation-conversion/member-ops" in redirect_response.headers["Location"]
    assert "stage=inactive-focus" in redirect_response.headers["Location"]
    assert "panel=send" in redirect_response.headers["Location"]
    assert "focus_batch_notice=created" in redirect_response.headers["Location"]
    assert "focus_batch_id=" in redirect_response.headers["Location"]

    response = client.get(redirect_response.headers["Location"])
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


def test_automation_conversion_run_center_sync_tab_shows_real_message_activity_env_names(app, client):
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

    response = client.get("/admin/automation-conversion/run-center", query_string={"tab": "sync"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "MESSAGE_ACTIVITY_DB_NAME" in html
    assert "MESSAGE_ACTIVITY_DB_PASS" in html
    assert "MESSAGE_ACTIVITY_DB_DATABASE" not in html
    assert "MESSAGE_ACTIVITY_DB_PASSWORD" not in html
    assert "数据同步" in html
    assert "立即刷新一次" in html
    assert "未配置" in html
    assert "最近一次同步失败" not in html
    assert ">failed<" not in html


def test_automation_conversion_run_center_logs_tab_uses_canonical_query(app, client):
    response = client.get("/admin/automation-conversion/run-center", query_string={"tab": "logs"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "执行日志 / 审计" in html
    assert "当前占位边界" in html
    assert "最近 SOP 执行摘要" in html
    assert "最近 AI 批任务摘要" in html
    assert "最近同步任务摘要" in html
    assert "最近失败任务提示" in html
    assert "/admin/automation-conversion/run-center?tab=logs" in html


def test_automation_conversion_run_center_overview_tab_avoids_heavy_operation_forms(app, client):
    response = client.get("/admin/automation-conversion/run-center", query_string={"tab": "overview"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "运行概况" in html
    assert "数据同步" in html
    assert "自动接话监控" in html
    assert "立即刷新一次" not in html
    assert "保存 DeepSeek 配置" not in html


def test_sop_v1_defaults_seed_three_pool_configs_and_day1_only(app):
    with app.app_context():
        payload = ensure_sop_v1_defaults()
        configs = {item["pool_key"]: item for item in payload["configs"]}

    assert set(configs.keys()) == {"new_user", "inactive_normal", "active_normal"}
    assert all(config["enabled"] is True for config in configs.values())
    assert all(config["send_time"] == "09:00" for config in configs.values())
    assert all(config["max_day_count"] == 1 for config in configs.values())
    assert all(len(payload["templates"][pool_key]) == 1 for pool_key in configs)
    assert all(payload["templates"][pool_key][0]["day_index"] == 1 for pool_key in configs)

    with app.app_context():
        timezones = [
            row["timezone"]
            for row in get_db().execute(
                "SELECT timezone FROM automation_sop_pool_config ORDER BY pool_key ASC"
            ).fetchall()
        ]
    assert timezones == ["Asia/Shanghai", "Asia/Shanghai", "Asia/Shanghai"]


def test_admin_automation_conversion_sop_page_uses_pool_cards_and_day_tabs_without_legacy_rules(app, client):
    with app.app_context():
        ensure_sop_v1_defaults()
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_sop_batch (
                pool_key, day_index, template_id, scheduled_for, status,
                total_count, success_count, skipped_count, failed_count, summary_json,
                created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "inactive_normal",
                1,
                "2026-04-08 09:00:00",
                "finished",
                8,
                5,
                2,
                1,
                json.dumps({"source": "test"}, ensure_ascii=False),
            ),
        )
        db.commit()

    response = client.get(
        "/admin/automation-conversion/sop",
        query_string={"pool": "inactive_normal", "day": 1},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "流程设计" in html
    assert "SOP 剧本" in html
    assert "新用户池" in html
    assert "未激活普通池" in html
    assert "激活普通池" in html
    assert "池子 / 阶段选择" in html
    assert "当前 Day 编辑器" in html
    assert "新增一天" in html
    assert "day1" in html
    assert "保存池子配置" in html
    assert "发布管理" in html
    assert "成功 5 / 跳过 2 / 失败 1" in html
    assert "暂无执行记录" in html
    assert "重复进同池不重来" not in html
    assert "离池期间错过的 SOP 不补发" not in html
    assert "最近 SOP 执行批次" not in html
    assert "最大 day 数" not in html
    assert 'name="timezone"' in html


def test_api_admin_automation_conversion_sop_config_no_timezone_required(app, client):
    response = client.put(
        "/api/admin/automation-conversion/sop/config/new_user",
        json={"enabled": False, "send_time": "08:30"},
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["config"]["pool_key"] == "new_user"
    assert payload["config"]["enabled"] is False
    assert payload["config"]["send_time"] == "08:30"
    assert payload["template_count"] == 1

    listing = client.get("/api/admin/automation-conversion/sop/config")
    listing_payload = listing.get_json()
    config_by_pool = {item["pool_key"]: item for item in listing_payload["configs"]}
    assert config_by_pool["new_user"]["send_time"] == "08:30"

    with app.app_context():
        row = get_db().execute(
            "SELECT timezone FROM automation_sop_pool_config WHERE pool_key = ?",
            ("new_user",),
        ).fetchone()
    assert row["timezone"] == "Asia/Shanghai"


def test_api_admin_automation_conversion_sop_template_save_reads_back_structured_local_images(app, client):
    local_image = {
        "file_name": "welcome.png",
        "content_type": "image/png",
        "data_url": _test_png_data_url(),
    }
    response = client.put(
        "/api/admin/automation-conversion/sop/templates/new_user/1",
        json={
            "content": "day1 欢迎文案",
            "enabled": True,
            "images_json": [local_image],
        },
    )

    payload = response.get_json()
    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["template"]["content"] == "day1 欢迎文案"
    assert payload["template"]["image_count"] == 1
    assert payload["template"]["images_json"][0]["file_name"] == "welcome.png"
    assert payload["template"]["images_json"][0]["data_url"] == local_image["data_url"]
    assert payload["template"]["images_json"][0]["preview_url"] == local_image["data_url"]

    templates_response = client.get("/api/admin/automation-conversion/sop/templates/new_user", query_string={"day": 1})
    templates_payload = templates_response.get_json()
    assert templates_response.status_code == 200
    assert templates_payload["selected_template"]["images_json"][0]["file_name"] == "welcome.png"

    with app.app_context():
        raw_row = get_db().execute(
            "SELECT images_json FROM automation_sop_template WHERE pool_key = ? AND day_index = ?",
            ("new_user", 1),
        ).fetchone()
    assert json.loads(raw_row["images_json"]) == [local_image]


def test_api_admin_automation_conversion_sop_delete_day_reorders_following_templates(app, client):
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2")
    _save_sop_template(app, pool_key="new_user", day_index=3, content="day3")
    _save_sop_template(app, pool_key="new_user", day_index=4, content="day4")

    response = client.delete("/api/admin/automation-conversion/sop/templates/new_user/2")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["template_count"] == 3
    assert payload["selected_day_index"] == 2
    assert payload["selected_template"]["content"] == "day3"

    with app.app_context():
        rows = get_db().execute(
            "SELECT day_index, content FROM automation_sop_template WHERE pool_key = ? ORDER BY day_index ASC",
            ("new_user",),
        ).fetchall()

    assert [(row["day_index"], row["content"]) for row in rows] == [
        (1, "day1"),
        (2, "day3"),
        (3, "day4"),
    ]


def test_sop_run_due_uses_natural_calendar_day_two_after_entry(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2 跟进")
    _seed_contact(app, external_userid="wm_sop_day2_001", mobile="13800009511", owner_userid="sales_sop", customer_name="SOP Day2 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_day2_001",
        phone="13800009511",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:30:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 801, "wecom_result": {"msgid": "msg-801"}},
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch = get_db().execute("SELECT day_index FROM automation_sop_batch ORDER BY id DESC LIMIT 1").fetchone()
        progress = get_db().execute(
            "SELECT sop_anchor_date, last_sent_day, last_sent_at FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert result["ok"] is True
    assert result["created_batch_count"] == 1
    assert result["total_success_count"] == 1
    assert dispatched[0]["text"]["content"] == "day2 跟进"
    assert batch["day_index"] == 2
    assert progress["sop_anchor_date"] == "2026-04-08"
    assert progress["last_sent_day"] == 2
    assert progress["last_sent_at"] == "2026-04-09 09:05:00"


def test_sop_run_due_entry_after_send_time_starts_day1_next_day(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_day1_late", mobile="13800009512", owner_userid="sales_sop", customer_name="SOP Day1 晚入池")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_day1_late",
        phone="13800009512",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 09:00:00",
    )
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 802, "wecom_result": {"msgid": "msg-802"}},
    )

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    with app.app_context():
        first = run_due_sop(operator_id="sop-runner", operator_type="system")

    assert first["created_batch_count"] == 0
    assert first["total_success_count"] == 0
    assert dispatched == []

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 09:05:00")
    with app.app_context():
        second = run_due_sop(operator_id="sop-runner", operator_type="system")
        progress = get_db().execute(
            "SELECT sop_anchor_date, last_sent_day FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert second["total_success_count"] == 1
    assert len(dispatched) == 1
    assert progress["sop_anchor_date"] == "2026-04-09"
    assert progress["last_sent_day"] == 1


def test_sop_run_due_groups_same_day_candidates_into_one_dispatch(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_group_001", mobile="13800009513", owner_userid="sales_sop", customer_name="SOP 分组客户1")
    _seed_contact(app, external_userid="wm_sop_group_002", mobile="13800009514", owner_userid="sales_sop", customer_name="SOP 分组客户2")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_group_001",
        phone="13800009513",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_group_002",
        phone="13800009514",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:10:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 810, "wecom_result": {"msgid": "msg-810", "fail_list": []}},
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch = get_db().execute(
            "SELECT total_count, success_count, failed_count FROM automation_sop_batch ORDER BY id DESC LIMIT 1"
        ).fetchone()
        item_rows = get_db().execute(
            "SELECT external_userid, status, sent_record_id FROM automation_sop_batch_item ORDER BY external_userid ASC"
        ).fetchall()

    assert result["created_batch_count"] == 1
    assert result["total_success_count"] == 2
    assert len(dispatched) == 1
    assert sorted(dispatched[0]["external_userid"]) == ["wm_sop_group_001", "wm_sop_group_002"]
    assert dict(batch) == {"total_count": 2, "success_count": 2, "failed_count": 0}
    assert [(row["external_userid"], row["status"]) for row in item_rows] == [
        ("wm_sop_group_001", "success"),
        ("wm_sop_group_002", "success"),
    ]
    assert len({row["sent_record_id"] for row in item_rows}) == 1


def test_record_sop_pool_entry_reentry_preserves_anchor_date(app):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _seed_contact(app, external_userid="wm_sop_progress_001", mobile="13800009501", owner_userid="sales_sop", customer_name="SOP 进度客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_progress_001",
        phone="13800009501",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )

    with app.app_context():
        member_id = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm_sop_progress_001",),
        ).fetchone()["id"]
        first = record_sop_pool_entry(member_id=member_id, pool_key="new_user", entered_at="2026-04-08 08:00:00")
        second = record_sop_pool_entry(member_id=member_id, pool_key="new_user", entered_at="2026-04-10 08:30:00")
        row = get_db().execute(
            """
            SELECT COUNT(*) AS total, sop_anchor_date, first_effective_in_pool_at, last_in_pool_at
            FROM automation_sop_progress
            WHERE member_id = ? AND pool_key = ?
            """,
            (member_id, "new_user"),
        ).fetchone()

    assert first["id"] == second["id"]
    assert row["total"] == 1
    assert row["sop_anchor_date"] == "2026-04-08"
    assert row["first_effective_in_pool_at"] == "2026-04-08 08:00:00"
    assert row["last_in_pool_at"] == "2026-04-10 08:30:00"


def test_sop_run_due_reentry_keeps_anchor_and_does_not_backfill(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="inactive_normal", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="inactive_normal", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="inactive_normal", day_index=2, content="")
    _save_sop_template(app, pool_key="inactive_normal", day_index=3, content="day3 跟进")
    _seed_contact(app, external_userid="wm_sop_reenter_001", mobile="13800009521", owner_userid="sales_sop", customer_name="SOP 重入客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_reenter_001",
        phone="13800009521",
        owner_staff_id="sales_sop",
        current_pool="inactive_normal",
        activation_status="inactive",
        questionnaire_status="submitted",
        questionnaire_result="normal",
        decision_source="questionnaire",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-10 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 803, "wecom_result": {"msgid": "msg-803"}},
    )

    with app.app_context():
        member_id = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm_sop_reenter_001",),
        ).fetchone()["id"]
        record_sop_pool_entry(member_id=member_id, pool_key="inactive_normal", entered_at="2026-04-08 08:00:00")
        record_sop_pool_entry(member_id=member_id, pool_key="inactive_normal", entered_at="2026-04-10 08:30:00")
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch = get_db().execute("SELECT day_index FROM automation_sop_batch ORDER BY id DESC LIMIT 1").fetchone()
        progress = get_db().execute(
            "SELECT sop_anchor_date, last_sent_day, last_in_pool_at FROM automation_sop_progress WHERE member_id = ? AND pool_key = ?",
            (member_id, "inactive_normal"),
        ).fetchone()

    assert result["total_success_count"] == 1
    assert dispatched[0]["text"]["content"] == "day3 跟进"
    assert batch["day_index"] == 3
    assert progress["sop_anchor_date"] == "2026-04-08"
    assert progress["last_sent_day"] == 3
    assert progress["last_in_pool_at"] == "2026-04-10 08:30:00"


def test_manual_send_does_not_change_sop_anchor_or_progress(app, client, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _seed_contact(app, external_userid="wm_sop_manual_001", mobile="13800009566", owner_userid="sales_sop", customer_name="SOP 手工群发客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_manual_001",
        phone="13800009566",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 900, "wecom_result": {"msgid": "msg-900"}},
    )

    with app.app_context():
        member_id = get_db().execute(
            "SELECT id FROM automation_member WHERE external_contact_id = ?",
            ("wm_sop_manual_001",),
        ).fetchone()["id"]
        record_sop_pool_entry(member_id=member_id, pool_key="new_user", entered_at="2026-04-08 08:00:00")
        before = dict(
            get_db().execute(
                """
                SELECT sop_anchor_date, first_effective_in_pool_at, last_in_pool_at, last_sent_day, last_sent_at
                FROM automation_sop_progress
                WHERE member_id = ? AND pool_key = ?
                """,
                (member_id, "new_user"),
            ).fetchone()
        )

    response = client.post(
        "/api/admin/automation-conversion/stage/new-user/manual-send",
        json={"content": "手工先发一条", "operator": "tester"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True

    with app.app_context():
        after = dict(
            get_db().execute(
                """
                SELECT sop_anchor_date, first_effective_in_pool_at, last_in_pool_at, last_sent_day, last_sent_at
                FROM automation_sop_progress
                WHERE member_id = ? AND pool_key = ?
                """,
                (member_id, "new_user"),
            ).fetchone()
        )

    assert after == before


def test_sop_run_due_template_empty_skips_today_and_moves_to_next_day(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2 继续跟进")
    _seed_contact(app, external_userid="wm_sop_empty_001", mobile="13800009561", owner_userid="sales_sop", customer_name="SOP 空模板客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_empty_001",
        phone="13800009561",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 806, "wecom_result": {"msgid": "msg-806"}},
    )

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    with app.app_context():
        first = run_due_sop(operator_id="sop-runner", operator_type="system")
        first_item = get_db().execute(
            "SELECT status, error_message FROM automation_sop_batch_item ORDER BY id ASC LIMIT 1"
        ).fetchone()
        first_progress = get_db().execute(
            "SELECT last_sent_day FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert first["total_success_count"] == 0
    assert first["total_skipped_count"] == 1
    assert dispatched == []
    assert (first_item["status"], first_item["error_message"]) == ("skipped", "template_empty")
    assert first_progress["last_sent_day"] == 1

    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-09 09:05:00")
    with app.app_context():
        second = run_due_sop(operator_id="sop-runner", operator_type="system")
        second_progress = get_db().execute(
            "SELECT last_sent_day FROM automation_sop_progress ORDER BY id DESC LIMIT 1"
        ).fetchone()

    assert second["total_success_count"] == 1
    assert len(dispatched) == 1
    assert dispatched[0]["text"]["content"] == "day2 继续跟进"
    assert second_progress["last_sent_day"] == 2


def test_sop_historical_member_uses_real_entry_date_and_clamps_to_last_day(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _save_sop_template(app, pool_key="new_user", day_index=2, content="day2 跟进消息")
    _save_sop_template(app, pool_key="new_user", day_index=3, content="day3 最后一条消息")
    _seed_contact(app, external_userid="wm_sop_history_001", mobile="13800009571", owner_userid="sales_sop", customer_name="SOP 历史客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_history_001",
        phone="13800009571",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-01 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 807, "wecom_result": {"msgid": "msg-807"}},
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        progress = get_db().execute(
            """
            SELECT sop_anchor_date, first_effective_in_pool_at, last_sent_day
            FROM automation_sop_progress
            ORDER BY id DESC LIMIT 1
            """
        ).fetchone()

    assert result["total_success_count"] == 1
    assert dispatched[0]["text"]["content"] == "day3 最后一条消息"
    assert progress["sop_anchor_date"] == "2026-04-01"
    assert progress["first_effective_in_pool_at"] == "2026-04-01 08:00:00"
    assert progress["last_sent_day"] == 3


def test_recent_execution_summary_appears_on_pool_cards(app, client):
    with app.app_context():
        ensure_sop_v1_defaults()
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_sop_batch (
                pool_key, day_index, template_id, scheduled_for, status,
                total_count, success_count, skipped_count, failed_count, summary_json,
                created_at, updated_at
            )
            VALUES (?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                "active_normal",
                2,
                "2026-04-08 10:00:00",
                "finished",
                6,
                3,
                2,
                1,
                json.dumps({"source": "test"}, ensure_ascii=False),
            ),
        )
        db.commit()

    response = client.get(
        "/admin/automation-conversion/sop",
        query_string={"pool": "active_normal", "day": 1},
        follow_redirects=True,
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "2026-04-08 10:00:00" in html
    assert "成功 3 / 跳过 2 / 失败 1" in html


def test_sop_run_due_api_requires_token_and_returns_batches(app, client, monkeypatch):
    app.config["AUTOMATION_INTERNAL_API_TOKEN"] = "sop-token"
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_api_001", mobile="13800009581", owner_userid="sales_sop", customer_name="SOP API 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_api_001",
        phone="13800009581",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: {"task_id": 808, "wecom_result": {"msgid": "msg-808"}},
    )

    unauthorized = client.post("/api/admin/automation-conversion/sop/run-due", json={"operator": "tester"})
    authorized = client.post(
        "/api/admin/automation-conversion/sop/run-due",
        json={"operator": "tester"},
        headers={"Authorization": "Bearer sop-token"},
    )

    assert unauthorized.status_code == 401
    assert authorized.status_code == 200
    payload = authorized.get_json()
    assert payload["ok"] is True
    assert payload["scanned_pool_count"] == 1
    assert payload["created_batch_count"] == 1
    assert payload["total_success_count"] == 1
    assert len(payload["batch_ids"]) == 1


def test_sop_run_due_api_fails_closed_when_token_is_not_configured(app, client, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_api_closed_001", mobile="13800009582", owner_userid="sales_sop", customer_name="SOP API 客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_api_closed_001",
        phone="13800009582",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")

    response = client.post("/api/admin/automation-conversion/sop/run-due", json={"operator": "tester"})

    assert response.status_code == 503
    assert response.get_json()["error"] == "internal token not configured"
    with app.app_context():
        batch_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch").fetchone()["total"]
    assert batch_total == 0


def test_sop_run_due_second_pass_does_not_create_duplicate_empty_batch(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_dup_001", mobile="13800009583", owner_userid="sales_sop", customer_name="SOP 重复客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_dup_001",
        phone="13800009583",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    dispatched: list[dict[str, object]] = []
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.service.dispatch_wecom_task",
        lambda task_type, fn_name, payload: dispatched.append(dict(payload)) or {"task_id": 809, "wecom_result": {"msgid": "msg-809"}},
    )

    with app.app_context():
        first = run_due_sop(operator_id="sop-runner", operator_type="system")
        second = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch").fetchone()["total"]
        item_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch_item").fetchone()["total"]

    assert first["created_batch_count"] == 1
    assert first["total_success_count"] == 1
    assert second["created_batch_count"] == 0
    assert second["total_success_count"] == 0
    assert second["total_skipped_count"] == 0
    assert batch_total == 1
    assert item_total == 1
    assert len(dispatched) == 1


def test_sop_run_due_skips_pool_when_lock_is_held(app, monkeypatch):
    _configure_only_sop_pool(app, pool_key="new_user", send_time="09:00")
    _set_sop_pool_effective_start(app, pool_key="new_user", effective_start_at="2026-04-08 06:00:00")
    _save_sop_template(app, pool_key="new_user", day_index=1, content="day1 欢迎消息")
    _seed_contact(app, external_userid="wm_sop_lock_001", mobile="13800009584", owner_userid="sales_sop", customer_name="SOP 锁客户")
    _seed_automation_member(
        app,
        external_contact_id="wm_sop_lock_001",
        phone="13800009584",
        owner_staff_id="sales_sop",
        current_pool="new_user",
        activation_status="inactive",
        questionnaire_status="pending",
        questionnaire_result="unknown",
        decision_source="system",
        joined_at="2026-04-08 08:00:00",
    )
    monkeypatch.setattr("wecom_ability_service.domains.automation_conversion.service._iso_now", lambda: "2026-04-08 09:05:00")
    monkeypatch.setattr(
        "wecom_ability_service.domains.automation_conversion.repo.try_acquire_sop_pool_run_lock",
        lambda *, pool_key: False,
    )

    with app.app_context():
        result = run_due_sop(operator_id="sop-runner", operator_type="system")
        batch_total = get_db().execute("SELECT COUNT(*) AS total FROM automation_sop_batch").fetchone()["total"]

    assert result["scanned_pool_count"] == 1
    assert result["created_batch_count"] == 0
    assert result["total_success_count"] == 0
    assert batch_total == 0


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

def test_qrcode_callback_sends_official_welcome_message(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import service as automation_service

    captured: dict[str, object] = {}

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            captured["payload"] = payload
            return {"errcode": 0, "errmsg": "ok"}

    monkeypatch.setattr(automation_service, "get_contact_runtime_client", lambda: _StubClient())

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, welcome_message, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-welcome', 'QianLan', '欢迎加入', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = automation_service.handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_002",
            phone="13800004002",
            payload_json={"state": "scene-welcome", "WelcomeCode": "welcome-001"},
            operator_id="callback-user",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["welcome_message"]["sent"] is True
        assert captured["payload"] == {
            "welcome_code": "welcome-001",
            "text": {"content": "欢迎加入"},
        }
        events = db.execute(
            "SELECT action FROM automation_event ORDER BY id DESC LIMIT 2"
        ).fetchall()
        assert [str(row["action"]) for row in events] == ["qrcode_welcome_sent", "qrcode_enter"]


def test_qrcode_callback_welcome_message_requires_welcome_code(app, monkeypatch):
    from wecom_ability_service.domains.automation_conversion import service as automation_service

    class _StubClient:
        def send_welcome_msg(self, payload: dict[str, object]) -> dict[str, object]:
            raise AssertionError("send_welcome_msg should not be called without welcome_code")

    monkeypatch.setattr(automation_service, "get_contact_runtime_client", lambda: _StubClient())

    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_channel (
                channel_code, channel_name, scene_value, owner_staff_id, welcome_message, status, created_at, updated_at
            )
            VALUES ('default_qrcode', '默认渠道二维码', 'scene-no-code', 'QianLan', '欢迎加入', 'active', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

        result = automation_service.handle_qrcode_enter_from_callback(
            external_contact_id="wm_qrcode_003",
            phone="13800004003",
            payload_json={"state": "scene-no-code"},
            operator_id="callback-user",
            send_welcome_message=True,
        )

        assert result["handled"] is True
        assert result["welcome_message"]["sent"] is False
        assert result["welcome_message"]["error"] == "missing_welcome_code"
        event = db.execute(
            "SELECT action, remark FROM automation_event ORDER BY id DESC LIMIT 1"
        ).fetchone()
        assert dict(event) == {
            "action": "qrcode_welcome_failed",
            "remark": "missing_welcome_code",
        }
