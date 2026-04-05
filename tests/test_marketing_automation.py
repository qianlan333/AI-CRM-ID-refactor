from __future__ import annotations

import json
from datetime import datetime as real_datetime

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "marketing-automation.sqlite3"
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
            "MCP_BEARER_TOKEN": "mcp-token",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _seed_customer(
    app,
    *,
    external_userid: str,
    mobile: str,
    customer_name: str,
    owner_userid: str,
    signup_status: str,
    signup_label_name: str,
    add_questionnaire: bool = False,
    messages: list[tuple[str, str, str]] | None = None,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT OR IGNORE INTO owner_role_map (userid, display_name, role, active)
            VALUES (?, ?, ?, ?)
            """,
            (owner_userid, owner_userid, "sales", 1),
        )
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (external_userid, customer_name, owner_userid, f"{customer_name}备注", external_userid),
        )
        db.execute(
            """
            INSERT INTO people (mobile, third_party_user_id, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile, f"tp-{external_userid}"),
        )
        person_id = db.execute("SELECT id FROM people WHERE mobile = ?", (mobile,)).fetchone()["id"]
        db.execute(
            """
            INSERT INTO external_contact_bindings (
                external_userid, person_id, first_bound_by_userid, first_owner_userid, last_owner_userid, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (external_userid, person_id, owner_userid, owner_userid, owner_userid),
        )
        db.execute(
            """
            INSERT INTO class_user_status_current (
                external_userid, signup_status, signup_label_name, customer_name_snapshot, owner_userid_snapshot,
                mobile_snapshot, set_by_userid, set_at, wecom_tag_sync_status, wecom_tag_sync_error, status_flags_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
            (external_userid, signup_status, signup_label_name, customer_name, owner_userid, mobile, owner_userid, "success", "", "{}"),
        )
        if add_questionnaire:
            db.execute(
                """
                INSERT OR IGNORE INTO questionnaires (id, slug, name, title, description, is_disabled, redirect_url)
                VALUES (1, 'marketing-auto', '自动化问卷', '自动化问卷', '', 0, '')
                """
            )
            db.execute(
                """
                INSERT INTO questionnaire_submissions (
                    questionnaire_id, respondent_key, openid, unionid, external_userid, follow_user_userid,
                    matched_by, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    1,
                    f"resp-{external_userid}",
                    f"openid-{external_userid}",
                    f"union-{external_userid}",
                    external_userid,
                    owner_userid,
                    "external_userid",
                    mobile,
                    88,
                    "[]",
                    "",
                    "2026-04-04 09:58:00",
                ),
            )
        for index, (sender, content, send_time) in enumerate(messages or [], start=1):
            receiver = owner_userid if sender == external_userid else external_userid
            db.execute(
                """
                INSERT INTO archived_messages
                (seq, msgid, chat_type, external_userid, owner_userid, sender, receiver, msgtype, content, send_time, raw_payload)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    index,
                    f"{external_userid}-msg-{index}",
                    "private",
                    external_userid,
                    owner_userid,
                    sender,
                    receiver,
                    "text",
                    content,
                    send_time,
                    json.dumps({"decrypted_message": {"from": sender, "tolist": [receiver], "roomid": ""}}, ensure_ascii=False),
                ),
            )
        db.commit()


def _mcp_call(client, name: str, arguments: dict):
    return client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
    )


def _freeze_router_time(monkeypatch, *, timestamp: str):
    from wecom_ability_service.domains.marketing_automation import service as marketing_service

    frozen = real_datetime.strptime(timestamp, "%Y-%m-%d %H:%M:%S")

    class FrozenDateTime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return cls(
                    frozen.year,
                    frozen.month,
                    frozen.day,
                    frozen.hour,
                    frozen.minute,
                    frozen.second,
                )
            return cls(
                frozen.year,
                frozen.month,
                frozen.day,
                frozen.hour,
                frozen.minute,
                frozen.second,
                tzinfo=tz,
            )

    monkeypatch.setattr(marketing_service, "datetime", FrozenDateTime)


def _save_default_signup_conversion_config(client, app, *, questionnaire_id: int) -> dict[str, object]:
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=questionnaire_id)
    response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert response.status_code == 200
    return seed


def _seed_marketing_fixture(app):
    _seed_customer(
        app,
        external_userid="wm_conv_001",
        mobile="13800138001",
        customer_name="候选客户",
        owner_userid="sales_01",
        signup_status="lead",
        signup_label_name="报名引流品",
        add_questionnaire=True,
        messages=[
            ("wm_conv_001", "老师我想了解课程", "2026-04-04 10:01:10"),
            ("sales_01", "好的，我发你课程安排", "2026-04-04 10:01:20"),
        ],
    )
    _seed_customer(
        app,
        external_userid="wm_conv_002",
        mobile="13800138002",
        customer_name="已报名客户",
        owner_userid="sales_01",
        signup_status="signed_999",
        signup_label_name="已报名999",
        messages=[("wm_conv_002", "我已经报名了", "2026-04-04 10:01:30")],
    )
    _seed_customer(
        app,
        external_userid="wm_conv_003",
        mobile="13800138003",
        customer_name="深夜客户",
        owner_userid="sales_01",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_conv_003", "晚上再聊", "2026-04-04 23:05:10")],
    )


def _seed_signup_conversion_questionnaire(app, *, questionnaire_id: int = 11) -> dict[str, object]:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaires (
                id, slug, name, title, description, is_disabled, redirect_url, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, 0, '', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                questionnaire_id,
                f"signup-conv-{questionnaire_id}",
                "报名成功自动化问卷",
                "报名成功自动化问卷",
                "",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, 6):
            question_id = questionnaire_id * 100 + index
            db.execute(
                """
                INSERT INTO questionnaire_questions (
                    id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
                )
                VALUES (?, ?, 'single_choice', ?, 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (question_id, questionnaire_id, f"关键问题{index}", index),
            )
            option_ids: list[int] = []
            for option_index in range(1, 3):
                option_id = question_id * 10 + option_index
                option_ids.append(option_id)
                db.execute(
                    """
                    INSERT INTO questionnaire_options (
                        id, question_id, option_text, score, tag_codes, sort_order, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, '[]', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                    """,
                    (
                        option_id,
                        question_id,
                        f"问题{index}-选项{option_index}",
                        option_index * 10,
                        option_index,
                    ),
                )
            question_ids.append(question_id)
            option_ids_by_question[question_id] = option_ids
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
    }


def _create_questionnaire_submission(
    app,
    questionnaire_seed: dict[str, object],
    *,
    submission_id: int,
    external_userid: str,
    mobile_snapshot: str,
    hit_question_count: int,
    submitted_at: str,
):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO questionnaire_submissions (
                id, questionnaire_id, respondent_key, external_userid, mobile_snapshot, total_score, final_tags, redirect_url_snapshot, submitted_at
            )
            VALUES (?, ?, ?, ?, ?, ?, '[]', '', ?)
            """,
            (
                submission_id,
                int(questionnaire_seed["questionnaire_id"]),
                f"resp-{submission_id}",
                external_userid,
                mobile_snapshot,
                hit_question_count * 10,
                submitted_at,
            ),
        )
        for index, question_id in enumerate(questionnaire_seed["question_ids"], start=1):
            option_id = questionnaire_seed["option_ids_by_question"][question_id][0 if index <= hit_question_count else 1]
            db.execute(
                """
                INSERT INTO questionnaire_submission_answers (
                    submission_id, question_id, question_type, question_title_snapshot,
                    selected_option_ids, selected_option_texts_snapshot, selected_option_scores_snapshot,
                    selected_option_tags_snapshot, text_value, score_contribution, created_at
                )
                VALUES (?, ?, 'single_choice', ?, ?, '[]', '[]', '[]', '', ?, CURRENT_TIMESTAMP)
                """,
                (
                    submission_id,
                    question_id,
                    f"关键问题{index}",
                    json.dumps([option_id]),
                    10 if index <= hit_question_count else 0,
                ),
            )
        db.commit()


def _seed_activation_source(app, *, mobile: str, updated_at: str):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO user_ops_huangxiaocan_activation_source (
                mobile, activation_state, import_batch_id, created_by, is_active, created_at, updated_at
            )
            VALUES (?, 'activated', 'batch-seed', 'seed', 1, ?, ?)
            """,
            (mobile, updated_at, updated_at),
        )
        db.commit()


def _signup_conversion_config_payload(
    questionnaire_seed: dict[str, object],
    *,
    enabled: bool = True,
    core_threshold: int = 3,
    top_threshold: int = 4,
    quiet_hour_start: int = 23,
    timezone: str = "Asia/Shanghai",
) -> dict[str, object]:
    question_ids = list(questionnaire_seed["question_ids"])
    option_ids_by_question = dict(questionnaire_seed["option_ids_by_question"])
    return {
        "enabled": enabled,
        "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
        "core_threshold": core_threshold,
        "top_threshold": top_threshold,
        "quiet_hour_start": quiet_hour_start,
        "timezone": timezone,
        "question_rules": [
            {
                "questionnaire_question_id": question_id,
                "hit_option_ids_json": [option_ids_by_question[question_id][0]],
                "sort_order": index,
            }
            for index, question_id in enumerate(question_ids, start=1)
        ],
    }


def test_signup_conversion_batch_api_filters_candidates_and_attaches_customer_context(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=41)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4101,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:02:00",
    )

    list_response = client.get("/api/customers/automation/signup-conversion/batches")
    list_payload = list_response.get_json()

    assert list_response.status_code == 200
    assert list_payload["ok"] is True
    assert list_payload["automation_batches"]["count"] == 1
    batch_preview = list_payload["automation_batches"]["items"][0]
    assert batch_preview["candidate_count"] == 1
    assert batch_preview["blocked_count"] == 0
    assert batch_preview["candidates_preview"][0]["external_userid"] == "wm_conv_001"
    assert batch_preview["candidates_preview"][0]["value_segment"] == "top"
    assert batch_preview["candidates_preview"][0]["current_stage"] == "prospect/wecom_connected"
    assert batch_preview["candidates_preview"][0]["dispatch_status"] == "pending"

    detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_preview['id']}")
    detail_payload = detail_response.get_json()["automation_batch"]
    candidate = detail_payload["candidates"][0]

    assert detail_response.status_code == 200
    assert detail_payload["candidate_count"] == 1
    assert detail_payload["blocked_count"] == 0
    assert candidate["external_userid"] == "wm_conv_001"
    assert candidate["current_stage"] == "prospect/wecom_connected"
    assert candidate["current_segment"] == "top"
    assert candidate["dispatch_status"] == "pending"
    assert candidate["customer_context"]["customer"]["marketing_profile"]["marketing_state"]["marketing_phase"] == "waiting_openclaw"
    assert candidate["customer_context"]["customer"]["marketing_profile"]["value_segment"]["value_segment"] == "top"
    assert detail_payload["skipped_count"] == 1

    signed_detail = client.get("/api/customers/wm_conv_002").get_json()["customer"]
    assert signed_detail["marketing_profile"]["marketing_state"]["marketing_phase"] == "exited_signup_success"


def test_signup_conversion_batch_mcp_tools_return_filtered_profiles(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=42)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4201,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:03:00",
    )

    tools_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    tool_names = {tool["name"] for tool in tools_response.get_json()["result"]["tools"]}
    assert "get_customer_marketing_profile" in tool_names
    assert "get_pending_conversion_batches" in tool_names
    assert "get_conversion_batch" in tool_names
    assert "ack_conversion_batch" in tool_names
    assert "get_signup_conversion_batches" in tool_names
    assert "get_signup_conversion_batch" in tool_names

    profile_payload = _mcp_call(
        client,
        "get_customer_marketing_profile",
        {"external_userid": "wm_conv_001", "recent_message_limit": 2},
    ).get_json()["result"]["structuredContent"]
    assert profile_payload["customer"]["external_userid"] == "wm_conv_001"
    assert profile_payload["owner"]["owner_userid"] == "sales_01"
    assert profile_payload["marketing_state"]["main_stage"] == "prospect"
    assert profile_payload["value_segment"]["segment"] == "top"
    assert profile_payload["routing"]["reason"] == "eligible_by_router"
    assert profile_payload["recent_text_summary"]["latest_customer_message_summary"] == "老师我想了解课程"
    assert profile_payload["recent_text_summary"]["latest_staff_message_summary"] == "好的，我发你课程安排"
    assert profile_payload["recent_text_summary"]["sample_size"] <= 2
    assert "items" not in profile_payload["recent_text_summary"]

    batches_payload = _mcp_call(client, "get_pending_conversion_batches", {"limit": 10}).get_json()["result"]["structuredContent"]
    assert batches_payload["count"] == 1
    batch_id = batches_payload["items"][0]["batch_id"]
    assert batches_payload["items"][0]["candidates_preview"][0]["reason"] == "pending_text_message_batch"

    batch_payload = _mcp_call(client, "get_conversion_batch", {"batch_id": batch_id}).get_json()["result"]["structuredContent"]
    candidate = batch_payload["candidates"][0]

    assert batch_payload["candidate_count"] == 1
    assert candidate["external_userid"] == "wm_conv_001"
    assert candidate["dispatch_status"] == "pending"
    assert candidate["marketing_profile"]["marketing_state"]["stage_key"] == "prospect/wecom_connected"
    assert candidate["marketing_profile"]["value_segment"]["is_top"] is True
    assert candidate["routing"]["reason"] == "pending_text_message_batch"


def test_ack_conversion_batch_mcp_tool_updates_dispatch_logs(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=142)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=14201,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:03:00",
    )

    pending_payload = _mcp_call(client, "get_pending_conversion_batches", {"limit": 10}).get_json()["result"]["structuredContent"]
    batch_id = pending_payload["items"][0]["batch_id"]

    ack_payload = _mcp_call(
        client,
        "ack_conversion_batch",
        {"batch_id": batch_id, "acked_by": "openclaw", "ack_note": "accepted by openclaw"},
    ).get_json()["result"]["structuredContent"]

    assert ack_payload["batch_id"] == batch_id
    assert ack_payload["acknowledged_count"] == 1
    assert ack_payload["dispatch_logs"][0]["dispatch_status"] == "acked"
    assert ack_payload["dispatch_logs"][0]["acked_at"] != ""

    with app.app_context():
        row = get_db().execute(
            """
            SELECT dispatch_status, acked_at
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_conv_001"),
        ).fetchone()
        assert row["dispatch_status"] == "acked"
        assert row["acked_at"] != ""


def test_sidebar_contact_binding_status_includes_marketing_profile(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=43)
    _seed_marketing_fixture(app)
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4301,
        external_userid="wm_conv_001",
        mobile_snapshot="13800138001",
        hit_question_count=4,
        submitted_at="2026-04-04 10:04:00",
    )

    response = client.get(
        "/api/sidebar/contact-binding-status",
        query_string={"external_userid": "wm_conv_001", "owner_userid": "sales_01"},
    )
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["marketing_profile"]["marketing_state"]["marketing_phase"] in {"waiting_openclaw", "awaiting_trigger"}
    assert payload["marketing_profile"]["value_segment"]["value_segment"] == "top"


def test_candidate_router_filters_normal_stage_and_is_idempotent(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=44)

    _seed_customer(
        app,
        external_userid="wm_router_top",
        mobile="13800138401",
        customer_name="Top 候选",
        owner_userid="sales_44",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_top", "我想尽快报名", "2026-04-04 10:11:00")],
    )
    _seed_customer(
        app,
        external_userid="wm_router_core",
        mobile="13800138402",
        customer_name="Core 候选",
        owner_userid="sales_44",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_core", "能介绍一下课程吗", "2026-04-04 10:11:20")],
    )
    _seed_customer(
        app,
        external_userid="wm_router_normal",
        mobile="13800138403",
        customer_name="Normal 客户",
        owner_userid="sales_44",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_normal", "先看看", "2026-04-04 10:11:40")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4401,
        external_userid="wm_router_top",
        mobile_snapshot="13800138401",
        hit_question_count=4,
        submitted_at="2026-04-04 10:12:00",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4402,
        external_userid="wm_router_core",
        mobile_snapshot="13800138402",
        hit_question_count=3,
        submitted_at="2026-04-04 10:12:10",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4403,
        external_userid="wm_router_normal",
        mobile_snapshot="13800138403",
        hit_question_count=2,
        submitted_at="2026-04-04 10:12:20",
    )
    _seed_activation_source(app, mobile="13800138402", updated_at="2026-04-04 10:12:30")

    list_response = client.get("/api/customers/automation/signup-conversion/batches")
    list_payload = list_response.get_json()["automation_batches"]
    assert list_response.status_code == 200
    assert list_payload["count"] == 1
    batch_id = list_payload["items"][0]["id"]

    first_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    first_detail = first_detail_response.get_json()["automation_batch"]
    candidate_external_userids = {item["external_userid"] for item in first_detail["candidates"]}
    skipped_map = {item["external_userid"]: item["reason"] for item in first_detail["skipped_customers"]}

    assert first_detail_response.status_code == 200
    assert first_detail["candidate_count"] == 2
    assert candidate_external_userids == {"wm_router_top", "wm_router_core"}
    assert skipped_map["wm_router_normal"] == "segment_not_core_top"
    assert {item["current_stage"] for item in first_detail["candidates"]} == {
        "prospect/wecom_connected",
        "active/activated",
    }
    assert {item["current_segment"] for item in first_detail["candidates"]} == {"top", "core"}

    with app.app_context():
        db = get_db()
        pending_rows = db.execute(
            """
            SELECT external_userid, dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ?
            ORDER BY external_userid ASC
            """,
            (batch_id,),
        ).fetchall()
        assert [(row["external_userid"], row["dispatch_status"]) for row in pending_rows] == [
            ("wm_router_core", "pending"),
            ("wm_router_top", "pending"),
        ]

    second_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    second_detail = second_detail_response.get_json()["automation_batch"]
    assert second_detail_response.status_code == 200
    assert second_detail["candidate_count"] == 2

    with app.app_context():
        db = get_db()
        pending_count = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND dispatch_status = 'pending'
            """,
            (batch_id,),
        ).fetchone()["total"]
        assert int(pending_count) == 2

        db.execute(
            """
            UPDATE conversion_dispatch_log
            SET dispatch_status = 'dispatched', dispatched_at = '2026-04-04 10:13:00'
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_router_top"),
        )
        db.commit()

    third_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    third_detail = third_detail_response.get_json()["automation_batch"]
    third_candidates = {item["external_userid"] for item in third_detail["candidates"]}
    third_skipped = {item["external_userid"]: item["reason"] for item in third_detail["skipped_customers"]}

    assert third_detail_response.status_code == 200
    assert third_candidates == {"wm_router_core"}
    assert third_skipped["wm_router_top"] == "already_dispatched"

    with app.app_context():
        db = get_db()
        row_count = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM conversion_dispatch_log
            WHERE batch_id = ?
            """,
            (batch_id,),
        ).fetchone()["total"]
        assert int(row_count) == 2


def test_candidate_router_blocks_after_quiet_hours_and_reenters_next_day(app, client, monkeypatch):
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=45)
    _seed_customer(
        app,
        external_userid="wm_router_blocked",
        mobile="13800138405",
        customer_name="夜间候选",
        owner_userid="sales_45",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_router_blocked", "今晚先问一下", "2026-04-04 10:21:00")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4501,
        external_userid="wm_router_blocked",
        mobile_snapshot="13800138405",
        hit_question_count=4,
        submitted_at="2026-04-04 10:22:00",
    )

    _freeze_router_time(monkeypatch, timestamp="2026-04-04 23:10:00")
    late_list_response = client.get("/api/customers/automation/signup-conversion/batches")
    late_payload = late_list_response.get_json()["automation_batches"]
    assert late_list_response.status_code == 200
    assert late_payload["count"] == 1
    batch_id = late_payload["items"][0]["id"]
    assert late_payload["items"][0]["candidate_count"] == 0
    assert late_payload["items"][0]["blocked_count"] == 1

    late_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    late_detail = late_detail_response.get_json()["automation_batch"]
    late_skipped = {item["external_userid"]: item["reason"] for item in late_detail["skipped_customers"]}

    assert late_detail_response.status_code == 200
    assert late_detail["candidate_count"] == 0
    assert late_detail["blocked_count"] == 1
    assert late_skipped["wm_router_blocked"] == "blocked_quiet_hours"

    with app.app_context():
        db = get_db()
        blocked_row = db.execute(
            """
            SELECT dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_router_blocked"),
        ).fetchone()
        assert blocked_row["dispatch_status"] == "blocked_quiet_hours"

    _freeze_router_time(monkeypatch, timestamp="2026-04-05 09:05:00")
    next_day_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    next_day_detail = next_day_detail_response.get_json()["automation_batch"]

    assert next_day_detail_response.status_code == 200
    assert next_day_detail["candidate_count"] == 1
    assert next_day_detail["blocked_count"] == 0
    assert next_day_detail["candidates"][0]["external_userid"] == "wm_router_blocked"
    assert next_day_detail["candidates"][0]["dispatch_status"] == "pending"

    with app.app_context():
        db = get_db()
        rows = db.execute(
            """
            SELECT dispatch_status
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_router_blocked"),
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["dispatch_status"] == "pending"


def test_sidebar_marketing_status_query_and_mark_unmark_reflect_latest_state(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=23)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_sidebar_marketing",
        mobile="13800138123",
        customer_name="侧边栏营销客户",
        owner_userid="sales_23",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _seed_activation_source(app, mobile="13800138123", updated_at="2026-04-04 13:00:00")
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2301,
        external_userid="wm_sidebar_marketing",
        mobile_snapshot="13800138123",
        hit_question_count=4,
        submitted_at="2026-04-04 13:05:00",
    )

    initial_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_marketing"},
    )
    initial_payload = initial_response.get_json()["marketing_status"]

    assert initial_response.status_code == 200
    assert initial_payload["external_userid"] == "wm_sidebar_marketing"
    assert initial_payload["main_stage"] == "active"
    assert initial_payload["sub_stage"] == "activated"
    assert initial_payload["segment"] == "top"
    assert initial_payload["stage_display"] == "已开始使用"
    assert initial_payload["segment_display"] == "最高优先用户"
    assert initial_payload["eligibility_display"] == "会"
    assert initial_payload["hit_count"] == 4
    assert initial_payload["matched_question_ids"] == seed["question_ids"][:4]
    assert initial_payload["eligible_for_conversion"] is True
    assert initial_payload["last_activation_at"] == "2026-04-04 13:00:00"
    assert initial_payload["last_conversion_marked_at"] == ""

    mark_response = client.post(
        "/api/sidebar/marketing-status/mark-enrolled",
        json={"external_userid": "wm_sidebar_marketing", "owner_userid": "sales_23", "operator": "sales_23"},
    )
    mark_payload = mark_response.get_json()

    assert mark_response.status_code == 200
    assert mark_payload["conversion"]["source"] == "sidebar_manual"
    assert mark_payload["marketing_status"]["main_stage"] == "converted"
    assert mark_payload["marketing_status"]["sub_stage"] == "enrolled"
    assert mark_payload["marketing_status"]["stage_display"] == "已报名成功"
    assert mark_payload["marketing_status"]["eligibility_display"] == "不会"
    assert "已退出自动化" in mark_payload["marketing_status"]["ineligible_reason_display"]
    assert mark_payload["marketing_status"]["eligible_for_conversion"] is False
    assert mark_payload["marketing_status"]["last_conversion_marked_at"] != ""

    marked_status_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_marketing"},
    )
    marked_status = marked_status_response.get_json()["marketing_status"]
    assert marked_status_response.status_code == 200
    assert marked_status["main_stage"] == "converted"
    assert marked_status["sub_stage"] == "enrolled"

    unmark_response = client.post(
        "/api/sidebar/marketing-status/unmark-enrolled",
        json={"external_userid": "wm_sidebar_marketing", "owner_userid": "sales_23", "operator": "sales_23"},
    )
    unmark_payload = unmark_response.get_json()

    assert unmark_response.status_code == 200
    assert unmark_payload["conversion"]["source"] == "sidebar_manual"
    assert unmark_payload["marketing_status"]["main_stage"] == "active"
    assert unmark_payload["marketing_status"]["sub_stage"] == "activated"
    assert unmark_payload["marketing_status"]["stage_display"] == "已开始使用"
    assert unmark_payload["marketing_status"]["eligible_for_conversion"] is True

    unmarked_status_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_marketing"},
    )
    unmarked_status = unmarked_status_response.get_json()["marketing_status"]
    assert unmarked_status_response.status_code == 200
    assert unmarked_status["main_stage"] == "active"
    assert unmarked_status["sub_stage"] == "activated"
    assert unmarked_status["segment"] == "top"


def test_sidebar_marketing_status_rejects_missing_and_unknown_external_userid(app, client):
    missing_response = client.get("/api/sidebar/marketing-status")
    assert missing_response.status_code == 400
    assert missing_response.get_json()["error"] == "external_userid is required"

    unknown_response = client.get(
        "/api/sidebar/marketing-status",
        query_string={"external_userid": "wm_sidebar_unknown"},
    )
    assert unknown_response.status_code == 404

    mark_missing_response = client.post("/api/sidebar/marketing-status/mark-enrolled", json={})
    assert mark_missing_response.status_code == 400
    assert mark_missing_response.get_json()["error"] == "external_userid is required"

    unmark_unknown_response = client.post(
        "/api/sidebar/marketing-status/unmark-enrolled",
        json={"external_userid": "wm_sidebar_unknown"},
    )
    assert unmark_unknown_response.status_code == 404


def test_signup_conversion_config_api_saves_and_reads_back(app, client):
    seed = _seed_signup_conversion_questionnaire(app)

    initial_response = client.get("/api/admin/marketing-automation/config")
    assert initial_response.status_code == 200
    assert initial_response.get_json()["config"]["configured"] is False
    assert initial_response.get_json()["config"]["core_threshold"] == 3
    assert initial_response.get_json()["config"]["top_threshold"] == 4

    payload = _signup_conversion_config_payload(
        seed,
        enabled=True,
        core_threshold=35,
        top_threshold=65,
        quiet_hour_start=22,
    )
    save_response = client.put("/api/admin/marketing-automation/config", json=payload)
    save_payload = save_response.get_json()["config"]

    assert save_response.status_code == 200
    assert save_payload["configured"] is True
    assert save_payload["enabled"] is True
    assert save_payload["questionnaire_id"] == seed["questionnaire_id"]
    assert save_payload["core_threshold"] == 35
    assert save_payload["top_threshold"] == 65
    assert save_payload["quiet_hour_start"] == 22
    assert save_payload["timezone"] == "Asia/Shanghai"
    assert len(save_payload["question_rules"]) == 5
    assert save_payload["question_rules"][0]["questionnaire_question_id"] == seed["question_ids"][0]
    assert save_payload["question_rules"][0]["hit_option_ids_json"] == [seed["option_ids_by_question"][seed["question_ids"][0]][0]]

    read_response = client.get("/api/admin/config/marketing-automation/signup-conversion")
    read_payload = read_response.get_json()["config"]

    assert read_response.status_code == 200
    assert read_payload["configured"] is True
    assert read_payload["top_threshold"] == 65
    assert read_payload["question_rules"][4]["sort_order"] == 5


def test_signup_conversion_config_api_rejects_invalid_question_and_option(app, client):
    seed = _seed_signup_conversion_questionnaire(app)

    bad_question_payload = _signup_conversion_config_payload(seed)
    bad_question_payload["question_rules"][0]["questionnaire_question_id"] = 999999
    bad_question_response = client.put("/api/admin/marketing-automation/config", json=bad_question_payload)

    assert bad_question_response.status_code == 400
    assert "does not belong to questionnaire" in bad_question_response.get_json()["error"]

    bad_option_payload = _signup_conversion_config_payload(seed)
    first_question_id = seed["question_ids"][0]
    second_question_id = seed["question_ids"][1]
    bad_option_payload["question_rules"][0]["questionnaire_question_id"] = first_question_id
    bad_option_payload["question_rules"][0]["hit_option_ids_json"] = [seed["option_ids_by_question"][second_question_id][0]]
    bad_option_response = client.put("/api/admin/marketing-automation/config", json=bad_option_payload)

    assert bad_option_response.status_code == 400
    assert "does not belong to question" in bad_option_response.get_json()["error"]


def test_disabled_signup_conversion_config_blocks_candidate_batches(app, client):
    seed = _seed_signup_conversion_questionnaire(app)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(seed, enabled=False),
    )
    assert save_response.status_code == 200

    _seed_marketing_fixture(app)

    list_response = client.get("/api/customers/automation/signup-conversion/batches")
    payload = list_response.get_json()["automation_batches"]

    assert list_response.status_code == 200
    assert payload["count"] == 0
    assert payload["items"] == []


def test_admin_marketing_automation_preview_returns_current_state_and_hits(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=21)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_admin_preview",
        mobile="13800138121",
        customer_name="预览客户",
        owner_userid="sales_21",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2101,
        external_userid="wm_admin_preview",
        mobile_snapshot="13800138121",
        hit_question_count=3,
        submitted_at="2026-04-04 11:00:00",
    )

    response = client.post(
        "/api/admin/marketing-automation/config/preview",
        json={"external_userid": "wm_admin_preview"},
    )
    payload = response.get_json()["preview"]

    assert response.status_code == 200
    assert payload["resolved_customer"]["external_userid"] == "wm_admin_preview"
    assert payload["summary"]["current_stage"] == "prospect/wecom_connected"
    assert payload["summary"]["current_segment"] == "core"
    assert payload["summary"]["hit_count"] == 3
    assert payload["summary"]["eligible"] is True
    assert [item["questionnaire_question_id"] for item in payload["summary"]["matched_questions"]] == seed["question_ids"][:3]

    with app.app_context():
        state_row = get_db().execute(
            """
            SELECT main_stage, sub_stage, eligible_for_conversion
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_admin_preview",),
        ).fetchone()
        segment_row = get_db().execute(
            """
            SELECT segment, score, matched_question_ids_json
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_admin_preview",),
        ).fetchone()
        assert f"{state_row['main_stage']}/{state_row['sub_stage']}" == payload["summary"]["current_stage"]
        assert bool(state_row["eligible_for_conversion"]) is True
        assert segment_row["segment"] == payload["summary"]["current_segment"]
        assert int(segment_row["score"]) == payload["summary"]["hit_count"]
        assert json.loads(segment_row["matched_question_ids_json"]) == payload["summary"]["matched_question_ids"]


def test_admin_marketing_automation_preview_supports_mobile_only_person(app, client):
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO people (id, mobile, third_party_user_id, created_at, updated_at)
            VALUES (6101, '13800138601', 'tp-6101', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """
        )
        db.commit()

    response = client.post(
        "/api/admin/marketing-automation/config/preview",
        json={"person_id": 6101},
    )
    payload = response.get_json()["preview"]

    assert response.status_code == 200
    assert payload["resolved_customer"]["person_id"] == 6101
    assert payload["resolved_customer"]["external_userid"] == ""
    assert payload["summary"]["current_stage"] == "prospect/mobile_only"
    assert payload["summary"]["current_segment"] == "unknown"
    assert payload["summary"]["eligible"] is False
    assert payload["summary"]["ineligible_reason"] == "missing_external_userid"


def test_admin_marketing_automation_recompute_refreshes_current_and_history(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=22)
    save_response = client.put("/api/admin/marketing-automation/config", json=_signup_conversion_config_payload(seed))
    assert save_response.status_code == 200

    _seed_customer(
        app,
        external_userid="wm_admin_recompute",
        mobile="13800138122",
        customer_name="重算客户",
        owner_userid="sales_22",
        signup_status="lead",
        signup_label_name="报名引流品",
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2201,
        external_userid="wm_admin_recompute",
        mobile_snapshot="13800138122",
        hit_question_count=2,
        submitted_at="2026-04-04 09:00:00",
    )

    first_response = client.post(
        "/api/admin/marketing-automation/recompute",
        json={"external_userid": "wm_admin_recompute"},
    )
    first_item = first_response.get_json()["recompute"]["item"]

    assert first_response.status_code == 200
    assert first_item["summary"]["current_stage"] == "prospect/wecom_connected"
    assert first_item["summary"]["current_segment"] == "normal"
    assert first_item["history_refresh"]["marketing_state_history_written"] is True
    assert first_item["history_refresh"]["value_segment_history_written"] is True

    _seed_activation_source(app, mobile="13800138122", updated_at="2026-04-04 12:00:00")
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=2202,
        external_userid="wm_admin_recompute",
        mobile_snapshot="13800138122",
        hit_question_count=4,
        submitted_at="2026-04-04 12:05:00",
    )

    second_response = client.post(
        "/api/admin/marketing-automation/recompute",
        json={"external_userid": "wm_admin_recompute"},
    )
    second_item = second_response.get_json()["recompute"]["item"]

    assert second_response.status_code == 200
    assert second_item["summary"]["current_stage"] == "active/activated"
    assert second_item["summary"]["current_segment"] == "top"
    assert second_item["history_refresh"]["marketing_state_history_written"] is True
    assert second_item["history_refresh"]["value_segment_history_written"] is True

    with app.app_context():
        db = get_db()
        state_current = db.execute(
            """
            SELECT main_stage, sub_stage
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()
        segment_current = db.execute(
            """
            SELECT segment, submission_id
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()
        state_history_total = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM customer_marketing_state_history
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()["total"]
        segment_history_total = db.execute(
            """
            SELECT COUNT(*) AS total
            FROM customer_value_segment_history
            WHERE external_userid = ?
            """,
            ("wm_admin_recompute",),
        ).fetchone()["total"]

        assert f"{state_current['main_stage']}/{state_current['sub_stage']}" == "active/activated"
        assert segment_current["segment"] == "top"
        assert int(segment_current["submission_id"]) == 2202
        assert int(state_history_total) == 2
        assert int(segment_history_total) == 2


def test_signup_conversion_e2e_chain_from_questionnaire_hit_to_enrolled_exit(app, client, monkeypatch):
    _freeze_router_time(monkeypatch, timestamp="2026-04-04 10:30:00")
    seed = _save_default_signup_conversion_config(client, app, questionnaire_id=46)

    _seed_customer(
        app,
        external_userid="wm_e2e_signup",
        mobile="13800138406",
        customer_name="完整链路客户",
        owner_userid="sales_46",
        signup_status="lead",
        signup_label_name="报名引流品",
        messages=[("wm_e2e_signup", "老师我想报名，先了解一下", "2026-04-04 10:06:00")],
    )
    _create_questionnaire_submission(
        app,
        seed,
        submission_id=4601,
        external_userid="wm_e2e_signup",
        mobile_snapshot="13800138406",
        hit_question_count=4,
        submitted_at="2026-04-04 10:05:00",
    )

    preview_response = client.post(
        "/api/admin/marketing-automation/config/preview",
        json={"external_userid": "wm_e2e_signup"},
    )
    preview = preview_response.get_json()["preview"]

    assert preview_response.status_code == 200
    assert preview["summary"]["current_stage"] == "prospect/wecom_connected"
    assert preview["summary"]["current_segment"] == "top"
    assert preview["summary"]["hit_count"] == 4
    assert preview["summary"]["eligible"] is True

    batches_response = client.get("/api/customers/automation/signup-conversion/batches")
    batches_payload = batches_response.get_json()["automation_batches"]

    assert batches_response.status_code == 200
    assert batches_payload["count"] == 1
    assert batches_payload["items"][0]["candidate_count"] == 1
    batch_id = batches_payload["items"][0]["id"]

    batch_detail_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    batch_detail = batch_detail_response.get_json()["automation_batch"]

    assert batch_detail_response.status_code == 200
    assert batch_detail["candidate_count"] == 1
    assert batch_detail["candidates"][0]["external_userid"] == "wm_e2e_signup"
    assert batch_detail["candidates"][0]["current_segment"] == "top"
    assert batch_detail["candidates"][0]["current_stage"] == "prospect/wecom_connected"
    assert batch_detail["candidates"][0]["dispatch_status"] == "pending"

    mark_response = client.post(
        "/api/sidebar/marketing-status/mark-enrolled",
        json={"external_userid": "wm_e2e_signup", "owner_userid": "sales_46", "operator": "sales_46"},
    )
    mark_payload = mark_response.get_json()

    assert mark_response.status_code == 200
    assert mark_payload["marketing_status"]["main_stage"] == "converted"
    assert mark_payload["marketing_status"]["sub_stage"] == "enrolled"
    assert mark_payload["marketing_status"]["eligible_for_conversion"] is False

    customer_response = client.get("/api/customers/wm_e2e_signup")
    customer_payload = customer_response.get_json()["customer"]

    assert customer_response.status_code == 200
    assert customer_payload["marketing_summary"]["main_stage"] == "converted"
    assert customer_payload["marketing_summary"]["sub_stage"] == "enrolled"
    assert customer_payload["marketing_summary"]["segment"] == "top"
    assert customer_payload["marketing_summary"]["hit_count"] == 4
    assert customer_payload["marketing_summary"]["eligible_for_conversion"] is False
    assert customer_payload["marketing_summary"]["last_conversion_marked_at"] != ""

    timeline_response = client.get("/api/customers/wm_e2e_signup/timeline")
    timeline_items = timeline_response.get_json()["timeline"]["items"]

    assert timeline_response.status_code == 200
    assert any(item["event_type"] == "value_segment_change" and item["payload"]["current_segment"] == "top" for item in timeline_items)
    assert any(item["event_type"] == "conversion_marked" and item["payload"]["conversion_action"] == "mark_enrolled" for item in timeline_items)

    exited_batch_response = client.get(f"/api/customers/automation/signup-conversion/batches/{batch_id}")
    exited_batch = exited_batch_response.get_json()["automation_batch"]
    skipped_map = {item["external_userid"]: item["reason"] for item in exited_batch["skipped_customers"]}

    assert exited_batch_response.status_code == 200
    assert exited_batch["candidate_count"] == 0
    assert skipped_map["wm_e2e_signup"] == "enrolled"

    with app.app_context():
        db = get_db()
        dispatch_row = db.execute(
            """
            SELECT dispatch_status, acked_at
            FROM conversion_dispatch_log
            WHERE batch_id = ? AND external_userid = ?
            """,
            (batch_id, "wm_e2e_signup"),
        ).fetchone()
        state_row = db.execute(
            """
            SELECT main_stage, sub_stage, eligible_for_conversion
            FROM customer_marketing_state_current
            WHERE external_userid = ?
            """,
            ("wm_e2e_signup",),
        ).fetchone()
        segment_row = db.execute(
            """
            SELECT segment, score
            FROM customer_value_segment_current
            WHERE external_userid = ?
            """,
            ("wm_e2e_signup",),
        ).fetchone()

        assert dispatch_row["dispatch_status"] == "converted_before_dispatch"
        assert dispatch_row["acked_at"] in {"", None}
        assert f"{state_row['main_stage']}/{state_row['sub_stage']}" == "converted/enrolled"
        assert bool(state_row["eligible_for_conversion"]) is False
        assert segment_row["segment"] == "top"
        assert int(segment_row["score"]) == 4
