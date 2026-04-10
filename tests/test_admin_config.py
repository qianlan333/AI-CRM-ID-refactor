from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import (
    get_routing_config,
    get_signup_conversion_config,
    resolve_contact_routing_context,
)


def _asia_shanghai_today() -> datetime.date:
    return datetime.now(ZoneInfo("Asia/Shanghai")).date()


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-config.sqlite3"
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


def _admin_action_token(client, path: str = "/admin/automation-conversion/flow-design") -> str:
    client.get(path, follow_redirects=True)
    with client.session_transaction() as session:
        return str(session["admin_console_action_token"])


def _seed_signup_conversion_questionnaire(
    app,
    *,
    questionnaire_id: int = 71,
    question_count: int = 5,
) -> dict[str, object]:
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
                f"marketing-automation-{questionnaire_id}",
                "自动化转化初判问卷",
                "自动化转化初判问卷",
            ),
        )
        question_ids: list[int] = []
        option_ids_by_question: dict[int, list[int]] = {}
        for index in range(1, question_count + 1):
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
        mobile_question_id = questionnaire_id * 100 + question_count + 1
        db.execute(
            """
            INSERT INTO questionnaire_questions (
                id, questionnaire_id, type, title, required, sort_order, created_at, updated_at
            )
            VALUES (?, ?, 'mobile', '手机号', 1, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (mobile_question_id, questionnaire_id, question_count + 1),
        )
        db.commit()
    return {
        "questionnaire_id": questionnaire_id,
        "question_ids": question_ids,
        "option_ids_by_question": option_ids_by_question,
        "mobile_question_id": mobile_question_id,
    }


def _signup_conversion_config_payload(
    questionnaire_seed: dict[str, object],
    *,
    enabled: bool = True,
    core_threshold: int = 3,
    top_threshold: int = 4,
    day_start_hour: int = 9,
    quiet_hour_start: int = 23,
    timezone: str = "Asia/Shanghai",
    question_ids: list[int] | None = None,
    hit_option_ids_by_question: dict[int, list[int]] | None = None,
    silent_threshold_days_by_pool: dict[str, int] | None = None,
) -> dict[str, object]:
    selected_question_ids = list(question_ids or questionnaire_seed["question_ids"])
    option_ids_by_question = dict(questionnaire_seed["option_ids_by_question"])
    return {
        "enabled": enabled,
        "questionnaire_id": int(questionnaire_seed["questionnaire_id"]),
        "core_threshold": core_threshold,
        "top_threshold": top_threshold,
        "day_start_hour": day_start_hour,
        "quiet_hour_start": quiet_hour_start,
        "timezone": timezone,
        "silent_threshold_days_by_pool": silent_threshold_days_by_pool
        or {
            "new_user": 7,
            "inactive_normal": 7,
            "inactive_focus": 7,
            "active_normal": 7,
            "active_focus": 7,
        },
        "question_rules": [
            {
                "questionnaire_question_id": question_id,
                "hit_option_ids_json": list(
                    hit_option_ids_by_question.get(question_id, [option_ids_by_question[question_id][0]])
                    if hit_option_ids_by_question
                    else [option_ids_by_question[question_id][0]]
                ),
                "sort_order": index,
            }
            for index, question_id in enumerate(selected_question_ids, start=1)
        ],
    }


def _seed_marketing_dispatch_history(app) -> None:
    with app.app_context():
        db = get_db()
        today = _asia_shanghai_today().isoformat()
        rows = [
            {
                "batch_id": 9101,
                "external_userid": "wm_dispatch_pending",
                "owner_userid": "sales_dispatch_01",
                "segment": "focus",
                "main_stage": "pool",
                "sub_stage": "inactive_focus",
                "dispatch_status": "pending",
                "created_at": f"{today} 10:01:00",
                "acked_at": "",
            },
            {
                "batch_id": 9102,
                "external_userid": "wm_dispatch_blocked",
                "owner_userid": "sales_dispatch_02",
                "segment": "focus",
                "main_stage": "pool",
                "sub_stage": "active_focus",
                "dispatch_status": "blocked_quiet_hours",
                "created_at": f"{today} 10:02:00",
                "acked_at": "",
            },
            {
                "batch_id": 9103,
                "external_userid": "wm_dispatch_acked",
                "owner_userid": "sales_dispatch_03",
                "segment": "normal",
                "main_stage": "pool",
                "sub_stage": "active_normal",
                "dispatch_status": "acked",
                "created_at": f"{today} 10:03:00",
                "acked_at": f"{today} 10:05:00",
            },
            {
                "batch_id": 9104,
                "external_userid": "wm_dispatch_converted",
                "owner_userid": "sales_dispatch_04",
                "segment": "focus",
                "main_stage": "converted",
                "sub_stage": "enrolled",
                "dispatch_status": "converted_before_dispatch",
                "created_at": f"{today} 10:04:00",
                "acked_at": "",
            },
        ]
        for item in rows:
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
                VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
                """,
                (item["external_userid"], item["external_userid"], item["owner_userid"]),
            )
            db.execute(
                """
                INSERT INTO message_batches (
                    id, batch_key, window_start, window_end, status, message_count, created_at
                )
                VALUES (?, ?, ?, ?, 'pending', 1, CURRENT_TIMESTAMP)
                """,
                (
                    item["batch_id"],
                    f"dispatch-batch-{item['batch_id']}",
                    f"{today} 10:00:00",
                    f"{today} 10:10:00",
                ),
            )
            db.execute(
                """
                INSERT INTO customer_marketing_state_current (
                    external_userid, automation_key, main_stage, sub_stage, activated, converted,
                    eligible_for_conversion, lifecycle_status, last_activation_at, last_conversion_marked_at,
                    last_message_at, last_batch_id, last_batch_status, last_batch_window_start, last_batch_window_end,
                    last_trigger_message_at, entered_at, exited_at, exit_reason, state_payload_json, created_at, updated_at
                )
                VALUES (?, 'signup_conversion_v1', ?, ?, 0, ?, 0, ?, '', '', '', ?, ?, '', '', '', ?, '', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["main_stage"],
                    item["sub_stage"],
                    1 if item["main_stage"] == "converted" else 0,
                    item["main_stage"],
                    item["batch_id"],
                    item["dispatch_status"],
                    item["created_at"],
                ),
            )
            db.execute(
                """
                UPDATE customer_marketing_state_current
                SET state_payload_json = ?
                WHERE external_userid = ?
                """,
                (
                    json.dumps({"followup_segment": item["segment"]}, ensure_ascii=False),
                    item["external_userid"],
                ),
            )
            db.execute(
                """
                INSERT INTO conversion_dispatch_log (
                    automation_key, batch_id, external_userid, dispatch_status, dispatch_channel,
                    dispatch_payload_json, dispatch_note, dispatched_at, acked_at, created_at, updated_at
                )
                VALUES ('signup_conversion_v1', ?, ?, ?, 'text_message', '{}', 'seed', ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (
                    item["batch_id"],
                    item["external_userid"],
                    item["dispatch_status"],
                    item["created_at"],
                    item["acked_at"] or None,
                    item["created_at"],
                ),
            )
        db.commit()


def _seed_automation_conversion_stage_board(app) -> None:
    today_date = _asia_shanghai_today()
    today = today_date.isoformat()
    yesterday = (today_date - timedelta(days=1)).isoformat()
    rows = [
        {
            "external_userid": "wm_stage_new_001",
            "owner_userid": "sales_stage_01",
            "phone": "13800000001",
            "follow_type": "",
            "current_pool": "new_user",
            "in_pool": 1,
            "activation_status": "unknown",
            "questionnaire_status": "pending",
            "questionnaire_result": "unknown",
            "joined_at": f"{today} 09:00:00",
        },
        {
            "external_userid": "wm_stage_inactive_normal_001",
            "owner_userid": "sales_stage_02",
            "phone": "13800000002",
            "follow_type": "normal",
            "current_pool": "inactive_normal",
            "in_pool": 1,
            "activation_status": "inactive",
            "questionnaire_status": "submitted",
            "questionnaire_result": "normal",
            "joined_at": f"{today} 10:00:00",
        },
        {
            "external_userid": "wm_stage_inactive_focus_001",
            "owner_userid": "sales_stage_03",
            "phone": "13800000003",
            "follow_type": "focus",
            "current_pool": "inactive_focus",
            "in_pool": 1,
            "activation_status": "inactive",
            "questionnaire_status": "submitted",
            "questionnaire_result": "focus",
            "joined_at": f"{yesterday} 11:00:00",
        },
        {
            "external_userid": "wm_stage_active_normal_001",
            "owner_userid": "sales_stage_04",
            "phone": "13800000004",
            "follow_type": "normal",
            "current_pool": "active_normal",
            "in_pool": 1,
            "activation_status": "active",
            "questionnaire_status": "submitted",
            "questionnaire_result": "normal",
            "joined_at": f"{today} 12:00:00",
        },
        {
            "external_userid": "wm_stage_active_focus_001",
            "owner_userid": "sales_stage_05",
            "phone": "13800000005",
            "follow_type": "focus",
            "current_pool": "active_focus",
            "in_pool": 1,
            "activation_status": "active",
            "questionnaire_status": "submitted",
            "questionnaire_result": "focus",
            "joined_at": f"{yesterday} 13:00:00",
        },
        {
            "external_userid": "wm_stage_silent_001",
            "owner_userid": "sales_stage_06",
            "phone": "13800000006",
            "follow_type": "normal",
            "current_pool": "silent",
            "in_pool": 1,
            "activation_status": "inactive",
            "questionnaire_status": "submitted",
            "questionnaire_result": "normal",
            "joined_at": f"{yesterday} 14:00:00",
        },
        {
            "external_userid": "wm_stage_won_001",
            "owner_userid": "sales_stage_07",
            "phone": "13800000007",
            "follow_type": "focus",
            "current_pool": "won",
            "in_pool": 0,
            "activation_status": "active",
            "questionnaire_status": "submitted",
            "questionnaire_result": "focus",
            "joined_at": f"{today} 15:00:00",
        },
    ]
    with app.app_context():
        db = get_db()
        for item in rows:
            db.execute(
                """
                INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
                VALUES (?, ?, ?, '', '', CURRENT_TIMESTAMP)
                """,
                (item["external_userid"], item["external_userid"], item["owner_userid"]),
            )
            db.execute(
                """
                INSERT INTO automation_member (
                    external_contact_id, phone, owner_staff_id, in_pool, current_pool, follow_type,
                    activation_status, questionnaire_status, questionnaire_result, decision_source,
                    source_type, joined_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'system', 'system', ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["phone"],
                    item["owner_userid"],
                    item["in_pool"],
                    item["current_pool"],
                    item["follow_type"],
                    item["activation_status"],
                    item["questionnaire_status"],
                    item["questionnaire_result"],
                    item["joined_at"],
                ),
            )
        db.commit()


def _mcp_list_tools(client, token: str = "mcp-token"):
    response = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    return response.get_json()


def _visible_text(html: str) -> str:
    without_scripts = re.sub(r"<script.*?</script>", " ", html, flags=re.S)
    without_tags = re.sub(r"<[^>]+>", " ", without_scripts)
    return " ".join(without_tags.split())


def _contains_standalone_token(text: str, token: str) -> bool:
    return re.search(rf"(?<![\w]){re.escape(token)}(?![\w])", text) is not None


def test_admin_config_pages_render(client):
    expected = {
        "/admin/config": "配置中心",
        "/admin/config/routing": "负责人 / 分配规则",
        "/admin/config/signup-tags": "报名标签规则",
        "/admin/config/class-term-tags": "班期标签规则",
        "/admin/automation-conversion": "自动化转化",
        "/admin/config/app-settings": "系统设置",
        "/admin/config/mcp-tools": "AI 工具设置",
    }
    for path, marker in expected.items():
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert marker in html
        if path.startswith("/admin/config"):
            assert "配置中心" in html


def test_admin_marketing_automation_legacy_route_redirects_to_new_page(client):
    response = client.get("/admin/marketing-automation/ui", query_string={"status": "blocked_quiet_hours"})

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion?status=blocked_quiet_hours")


def test_admin_config_routing_save_updates_runtime_and_audit(app, client):
    owner_response = client.post(
        "/api/admin/config/routing/owner-role",
        json={
            "userid": "sales_01",
            "display_name": "销售一号",
            "role": "sales",
            "active": True,
            "operator": "tester-routing",
        },
    )
    rule_response = client.post(
        "/api/admin/config/routing/rule",
        json={
            "rule_key": "signed_999",
            "routing_alias": "signed_999",
            "route_owner_userid": "sales_01",
            "route_owner_role": "sales",
            "routing_target": "manual_review",
            "fallback_target": "manual_review",
            "active": True,
            "operator": "tester-routing",
        },
    )

    assert owner_response.status_code == 200
    assert rule_response.status_code == 200

    with app.app_context():
        payload = get_routing_config()
        assert payload["routing_rules"]["signed_999"]["routing_target"] == "manual_review"
        context = resolve_contact_routing_context("sales_01", "sales", "signed_999")
        assert context["routing_target"] == "manual_review"

        logs = get_db().execute(
            """
            SELECT target_type, target_id, operator
            FROM admin_operation_logs
            ORDER BY id ASC
            """
        ).fetchall()
        assert any(row["target_type"] == "owner_role_map" and row["target_id"] == "sales_01" for row in logs)
        assert any(row["target_type"] == "routing_rule_config" and row["target_id"] == "signed_999" for row in logs)
        assert all(row["operator"] == "tester-routing" for row in logs)


def test_admin_config_settings_keep_secrets_masked_and_write_audit(app, client):
    update_response = client.put(
        "/api/settings",
        json={
            "settings": {
                "WECOM_SECRET": "secret-123456",
                "WECOM_API_BASE": "https://qyapi.example.test",
            },
            "operator": "tester-settings",
            "confirm": True,
        },
    )
    compat_payload = update_response.get_json()
    admin_payload = client.get("/api/admin/config/app-settings").get_json()

    assert update_response.status_code == 200
    assert compat_payload["ok"] is True
    assert compat_payload["settings"]["WECOM_SECRET"] != "secret-123456"
    assert "***" in compat_payload["settings"]["WECOM_SECRET"]
    assert compat_payload["settings"]["WECOM_API_BASE"] == "https://qyapi.example.test"

    secret_row = next(
        item for item in admin_payload["config"]["rows"] if item["key"] == "WECOM_SECRET"
    )
    assert secret_row["value"] == ""
    assert secret_row["display_value"] != "secret-123456"
    assert secret_row["configured"] is True

    with app.app_context():
        logs = get_db().execute(
            """
            SELECT target_id, operator
            FROM admin_operation_logs
            WHERE target_type = 'app_setting'
            ORDER BY id ASC
            """
        ).fetchall()
        assert any(row["target_id"] == "WECOM_SECRET" for row in logs)
        assert any(row["target_id"] == "WECOM_API_BASE" for row in logs)
        assert all(row["operator"] == "tester-settings" for row in logs)


def test_admin_config_settings_require_confirmation(client):
    response = client.put(
        "/api/settings",
        json={
            "settings": {
                "WECOM_API_BASE": "https://qyapi.example.test",
            },
            "operator": "tester-settings",
        },
    )

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "confirm is required before saving app settings"


def test_admin_config_mcp_tool_settings_control_runtime(client):
    before = _mcp_list_tools(client)
    before_names = [item["name"] for item in before["result"]["tools"]]
    assert "get_routing_config" in before_names

    save_response = client.post(
        "/api/admin/config/mcp-tools",
        json={
            "tool_name": "get_routing_config",
            "tool_group": "config",
            "display_name": "Get Routing Config",
            "description_override": "disabled for test",
            "enabled": False,
            "visible_in_console": True,
            "show_sample_args": False,
            "show_sample_output": False,
            "sort_order": 99,
            "operator": "tester-mcp",
        },
    )
    assert save_response.status_code == 200

    after = _mcp_list_tools(client)
    after_names = [item["name"] for item in after["result"]["tools"]]
    assert "get_routing_config" not in after_names

    call_response = client.post(
        "/mcp",
        headers={"Authorization": "Bearer mcp-token"},
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {"name": "get_routing_config", "arguments": {}},
        },
    )
    payload = call_response.get_json()
    assert payload["error"]["code"] == -32000
    assert "tool is disabled" in payload["error"]["message"]


def test_admin_config_class_term_and_signup_pages_have_seeded_config(client):
    signup_response = client.get("/api/admin/config/signup-tags")
    class_term_response = client.get("/api/admin/config/class-term-tags")

    signup_payload = signup_response.get_json()
    class_term_payload = class_term_response.get_json()

    assert signup_response.status_code == 200
    assert class_term_response.status_code == 200
    assert signup_payload["config"]["tag_group_name"] == "AI 产品报名情况"
    assert len(class_term_payload["config"]["rows"]) >= 1


def test_admin_automation_conversion_page_renders_saved_config_and_preview_panel(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=81)
    _seed_automation_conversion_stage_board(app)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(
            seed,
            core_threshold=2,
            top_threshold=5,
            silent_threshold_days_by_pool={
                "new_user": 3,
                "inactive_normal": 4,
                "inactive_focus": 5,
                "active_normal": 6,
                "active_focus": 7,
            },
        ),
    )
    assert save_response.status_code == 200

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "自动化转化" in visible_text
    assert "经营驾驶舱" in visible_text
    assert "经营摘要" in visible_text
    assert "在池总人数" in visible_text
    assert "今日入池" in visible_text
    assert "待问卷" in visible_text
    assert "普通跟进" in visible_text
    assert "重点跟进" in visible_text
    assert "沉默池" in visible_text
    assert "已成交" in visible_text
    assert "阶段漏斗 / 阶段分布" in visible_text
    assert "待处理事项" in visible_text
    assert "最近运行摘要" in visible_text
    assert "快捷动作" in visible_text
    assert "流程设计" in visible_text
    assert "成员运营" in visible_text
    assert "运行中心" in visible_text
    assert "/admin/automation-conversion/member-ops?stage=new-user" in html
    assert "/admin/automation-conversion/member-ops?stage=inactive-focus" in html
    assert "/admin/automation-conversion/flow-design?section=questionnaire" in html
    assert "/admin/automation-conversion/run-center?tab=overview" in html
    assert "配置步骤" not in visible_text
    assert "最近处理情况" not in visible_text
    assert "立即刷新一次" not in visible_text
    assert "进入设置页" not in visible_text
    assert "进入调试页" not in visible_text
    assert "JSON" not in visible_text


def test_admin_automation_conversion_page_survives_missing_configured_questionnaire(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=82)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(seed, core_threshold=2, top_threshold=5),
    )
    assert save_response.status_code == 200

    with app.app_context():
        db = get_db()
        db.execute(
            "DELETE FROM questionnaire_options WHERE question_id IN (SELECT id FROM questionnaire_questions WHERE questionnaire_id = ?)",
            (82,),
        )
        db.execute("DELETE FROM questionnaire_questions WHERE questionnaire_id = ?", (82,))
        db.execute("DELETE FROM questionnaires WHERE id = ?", (82,))
        db.commit()

    legacy_response = client.get("/admin/automation-conversion/settings")
    assert legacy_response.status_code == 302
    assert "/admin/automation-conversion/flow-design" in legacy_response.headers["Location"]
    assert "section=questionnaire" in legacy_response.headers["Location"]

    response = client.get("/admin/automation-conversion/settings", follow_redirects=True)
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "流程设计" in visible_text
    assert "已配置的问卷 #82 不存在" in visible_text
    assert "当前不会继续展示失效问卷的旧规则" in visible_text
    assert "关键题规则 JSON" not in visible_text


def test_admin_automation_conversion_settings_page_uses_visual_rule_editor(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=83, question_count=2)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(
            seed,
            day_start_hour=8,
            question_ids=[seed["question_ids"][0]],
            hit_option_ids_by_question={seed["question_ids"][0]: seed["option_ids_by_question"][seed["question_ids"][0]]},
        ),
    )
    assert save_response.status_code == 200

    response = client.get("/admin/automation-conversion/settings", follow_redirects=True)
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "流程设计" in visible_text
    assert "入池与问卷规则" in visible_text
    assert "自动启动时间窗" in visible_text
    assert "白天开始小时" in visible_text
    assert "关键题规则" in visible_text
    assert "新增关键题" in visible_text
    assert "关键题规则 JSON" not in visible_text
    assert 'name="day_start_hour"' in html
    assert 'id="question-rule-editor-root"' in html
    assert 'type="hidden" name="question_rules_json"' in html
    assert "关键问题1" in html
    assert "问题1-选项1" in html
    assert "问题1-选项2" in html


def test_admin_automation_conversion_settings_save_form_persists_visual_rules(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=84, question_count=2)
    question_id = seed["question_ids"][1]
    option_ids = seed["option_ids_by_question"][question_id]
    action_token = _admin_action_token(client, "/admin/automation-conversion/flow-design?section=questionnaire")

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={
            "admin_action_token": action_token,
            "section": "questionnaire",
            "enabled": "1",
            "questionnaire_id": str(seed["questionnaire_id"]),
            "core_threshold": "2",
            "top_threshold": "3",
            "day_start_hour": "9",
            "quiet_hour_start": "22",
            "timezone": "Asia/Shanghai",
            "silent_threshold_new_user": "7",
            "silent_threshold_inactive_normal": "8",
            "silent_threshold_inactive_focus": "9",
            "silent_threshold_active_normal": "10",
            "silent_threshold_active_focus": "11",
            "question_rules_json": json.dumps(
                [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": option_ids,
                        "sort_order": 1,
                    }
                ],
                ensure_ascii=False,
            ),
        },
    )

    assert response.status_code == 302
    assert "/admin/automation-conversion/flow-design" in response.headers["Location"]
    assert "section=questionnaire" in response.headers["Location"]
    assert "saved=1" in response.headers["Location"]

    with app.app_context():
        config = get_signup_conversion_config()
        assert config["questionnaire_id"] == seed["questionnaire_id"]
        assert config["core_threshold"] == 2
        assert config["top_threshold"] == 3
        assert config["day_start_hour"] == 9
        assert config["quiet_hour_start"] == 22
        assert config["silent_threshold_days_by_pool"]["inactive_focus"] == 9
        assert len(config["question_rules"]) == 1
        rule = config["question_rules"][0]
        assert rule["questionnaire_id"] == seed["questionnaire_id"]
        assert rule["questionnaire_question_id"] == question_id
        assert rule["question_title"] == "关键问题2"
        assert rule["question_type"] == "single_choice"
        assert rule["hit_option_ids_json"] == option_ids
        assert rule["hit_options"] == [
            {"id": option_ids[0], "option_text": "问题2-选项1"},
            {"id": option_ids[1], "option_text": "问题2-选项2"},
        ]
        assert rule["sort_order"] == 1


def test_admin_automation_conversion_settings_save_form_persists_default_channel_fields(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=185, question_count=2)
    question_id = seed["question_ids"][0]
    option_id = seed["option_ids_by_question"][question_id][0]
    action_token = _admin_action_token(client, "/admin/automation-conversion/flow-design?section=channel")

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={
            "admin_action_token": action_token,
            "section": "channel",
            "enabled": "1",
            "questionnaire_id": str(seed["questionnaire_id"]),
            "core_threshold": "2",
            "top_threshold": "3",
            "day_start_hour": "9",
            "quiet_hour_start": "22",
            "timezone": "Asia/Shanghai",
            "welcome_message": "保存后的默认欢迎语",
            "auto_accept_friend": "1",
            "silent_threshold_new_user": "7",
            "silent_threshold_inactive_normal": "8",
            "silent_threshold_inactive_focus": "9",
            "silent_threshold_active_normal": "10",
            "silent_threshold_active_focus": "11",
            "question_rules_json": json.dumps(
                [
                    {
                        "questionnaire_question_id": question_id,
                        "hit_option_ids_json": [option_id],
                        "sort_order": 1,
                    }
                ],
                ensure_ascii=False,
            ),
        },
    )

    assert response.status_code == 302
    assert "/admin/automation-conversion/flow-design" in response.headers["Location"]
    assert "section=channel" in response.headers["Location"]
    assert "saved=1" in response.headers["Location"]

    page = client.get(response.headers["Location"])
    html = page.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert page.status_code == 200
    assert "默认渠道入口" in visible_text
    assert "保存后的默认欢迎语" in html
    assert "自动通过好友" in html

    with app.app_context():
        row = get_db().execute(
            """
            SELECT welcome_message, auto_accept_friend, status
            FROM automation_channel
            WHERE channel_code = 'default_qrcode'
            """
        ).fetchone()
        assert row is not None
        assert row["welcome_message"] == "保存后的默认欢迎语"
        assert bool(row["auto_accept_friend"]) is True
        assert row["status"] == "configured"


def test_admin_automation_conversion_settings_save_form_rejects_invalid_auto_start_window(app, client):
    seed = _seed_signup_conversion_questionnaire(app, questionnaire_id=184, question_count=2)
    action_token = _admin_action_token(client, "/admin/automation-conversion/flow-design?section=global-rules")

    response = client.post(
        "/admin/automation-conversion/settings/save",
        data={
            "admin_action_token": action_token,
            "section": "global-rules",
            "enabled": "1",
            "questionnaire_id": str(seed["questionnaire_id"]),
            "core_threshold": "2",
            "top_threshold": "3",
            "day_start_hour": "23",
            "quiet_hour_start": "23",
            "timezone": "Asia/Shanghai",
            "silent_threshold_new_user": "7",
            "silent_threshold_inactive_normal": "8",
            "silent_threshold_inactive_focus": "9",
            "silent_threshold_active_normal": "10",
            "silent_threshold_active_focus": "11",
            "question_rules_json": json.dumps([], ensure_ascii=False),
        },
    )

    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "day_start_hour must be" in html
    assert "全局规则" in visible_text
    assert "白天开始小时" in visible_text
    assert 'value="23"' in html


def test_admin_automation_conversion_stage_detail_page_renders_filtered_customers(app, client):
    _seed_automation_conversion_stage_board(app)

    legacy_response = client.get("/admin/automation-conversion/stage/inactive-focus")
    assert legacy_response.status_code == 302
    assert "/admin/automation-conversion/member-ops" in legacy_response.headers["Location"]
    assert "stage=inactive-focus" in legacy_response.headers["Location"]
    assert "panel=members" in legacy_response.headers["Location"]

    response = client.get("/admin/automation-conversion/stage/inactive-focus", follow_redirects=True)
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "成员运营" in visible_text
    assert "未激活重点跟进池" in visible_text
    assert "重点跟进" in visible_text
    assert "总人数" in visible_text
    assert "今日新增" in visible_text
    assert "创建群发" in visible_text
    assert "wm_stage_inactive_focus_001" in visible_text
    assert "wm_stage_active_focus_001" not in visible_text
    assert "搜索与筛选条" in visible_text

    filtered_response = client.get(
        "/admin/automation-conversion/stage/inactive-focus",
        query_string={"keyword": "focus_001"},
        follow_redirects=True,
    )
    filtered_text = _visible_text(filtered_response.get_data(as_text=True))
    assert filtered_response.status_code == 200
    assert "wm_stage_inactive_focus_001" in filtered_text
    assert "wm_stage_inactive_normal_001" not in filtered_text


def test_admin_automation_conversion_preview_page_renders_runtime_search_shell(client):
    response = client.get("/admin/automation-conversion/preview")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion/run-center?tab=debug")


def test_admin_marketing_automation_dispatch_history_api_supports_status_filter(app, client):
    _seed_marketing_dispatch_history(app)

    response = client.get("/api/admin/marketing-automation/dispatch-history")
    blocked_response = client.get(
        "/api/admin/marketing-automation/dispatch-history",
        query_string={"status": "blocked_quiet_hours"},
    )

    payload = response.get_json()
    blocked_payload = blocked_response.get_json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["dispatch_history"]["count"] == 4
    statuses = {item["dispatch_status"] for item in payload["dispatch_history"]["items"]}
    assert {"pending", "blocked_quiet_hours", "acked", "converted_before_dispatch"} <= statuses

    assert blocked_response.status_code == 200
    assert blocked_payload["dispatch_history"]["status"] == "blocked_quiet_hours"
    assert blocked_payload["dispatch_history"]["count"] == 1
    assert blocked_payload["dispatch_history"]["items"][0]["external_userid"] == "wm_dispatch_blocked"
    assert blocked_payload["dispatch_history"]["items"][0]["stage"] == "pool/active_focus"


def test_admin_automation_conversion_debug_page_renders_search_shell(client):
    response = client.get("/admin/automation-conversion/debug", follow_redirects=True)
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "运行中心" in visible_text
    assert "单客调试" in visible_text
    assert "external_contact_id" in visible_text
    assert "手机号" in visible_text
    assert "查看状态" in visible_text
