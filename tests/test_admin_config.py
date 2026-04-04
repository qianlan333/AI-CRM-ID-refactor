from __future__ import annotations

import json
import re
from datetime import datetime, timedelta

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.services import get_routing_config, resolve_contact_routing_context


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


def _seed_signup_conversion_questionnaire(app, *, questionnaire_id: int = 71) -> dict[str, object]:
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
                "报名成功自动化问卷",
                "报名成功自动化问卷",
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


def _seed_marketing_dispatch_history(app) -> None:
    with app.app_context():
        db = get_db()
        today = datetime.now().date().isoformat()
        rows = [
            {
                "batch_id": 9101,
                "external_userid": "wm_dispatch_pending",
                "owner_userid": "sales_dispatch_01",
                "segment": "core",
                "main_stage": "prospect",
                "sub_stage": "wecom_connected",
                "dispatch_status": "pending",
                "created_at": f"{today} 10:01:00",
                "acked_at": "",
            },
            {
                "batch_id": 9102,
                "external_userid": "wm_dispatch_blocked",
                "owner_userid": "sales_dispatch_02",
                "segment": "top",
                "main_stage": "active",
                "sub_stage": "activated",
                "dispatch_status": "blocked_quiet_hours",
                "created_at": f"{today} 10:02:00",
                "acked_at": "",
            },
            {
                "batch_id": 9103,
                "external_userid": "wm_dispatch_acked",
                "owner_userid": "sales_dispatch_03",
                "segment": "top",
                "main_stage": "prospect",
                "sub_stage": "wecom_connected",
                "dispatch_status": "acked",
                "created_at": f"{today} 10:03:00",
                "acked_at": f"{today} 10:05:00",
            },
            {
                "batch_id": 9104,
                "external_userid": "wm_dispatch_converted",
                "owner_userid": "sales_dispatch_04",
                "segment": "core",
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
                INSERT INTO customer_value_segment_current (
                    external_userid, segment, segment_rank, score, scoring_version, computed_reason, submission_id,
                    matched_question_ids_json, source_payload_json, evaluated_at, computed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'signup_conversion_question_hits_v1', 'seed', NULL, '[]', '{}', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["segment"],
                    3 if item["segment"] == "top" else 2,
                    4 if item["segment"] == "top" else 3,
                    item["created_at"],
                    item["created_at"],
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
    today = datetime.now().date().isoformat()
    yesterday = (datetime.now().date() - timedelta(days=1)).isoformat()
    rows = [
        {
            "external_userid": "wm_stage_wait_001",
            "owner_userid": "sales_stage_01",
            "segment": "normal",
            "main_stage": "prospect",
            "sub_stage": "wecom_connected",
            "entered_at": f"{today} 09:00:00",
        },
        {
            "external_userid": "wm_stage_wait_002",
            "owner_userid": "sales_stage_02",
            "segment": "core",
            "main_stage": "prospect",
            "sub_stage": "wecom_connected",
            "entered_at": f"{today} 10:00:00",
        },
        {
            "external_userid": "wm_stage_wait_003",
            "owner_userid": "sales_stage_03",
            "segment": "top",
            "main_stage": "prospect",
            "sub_stage": "wecom_connected",
            "entered_at": f"{yesterday} 11:00:00",
        },
        {
            "external_userid": "wm_stage_active_001",
            "owner_userid": "sales_stage_04",
            "segment": "core",
            "main_stage": "active",
            "sub_stage": "activated",
            "entered_at": f"{today} 12:00:00",
        },
        {
            "external_userid": "wm_stage_active_002",
            "owner_userid": "sales_stage_05",
            "segment": "top",
            "main_stage": "active",
            "sub_stage": "activated",
            "entered_at": f"{yesterday} 13:00:00",
        },
        {
            "external_userid": "wm_stage_converted_001",
            "owner_userid": "sales_stage_06",
            "segment": "core",
            "main_stage": "converted",
            "sub_stage": "enrolled",
            "entered_at": f"{today} 14:00:00",
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
                INSERT INTO customer_marketing_state_current (
                    external_userid, automation_key, main_stage, sub_stage, activated, converted,
                    eligible_for_conversion, lifecycle_status, last_activation_at, last_conversion_marked_at,
                    last_message_at, last_batch_id, last_batch_status, last_batch_window_start, last_batch_window_end,
                    last_trigger_message_at, entered_at, exited_at, exit_reason, state_payload_json, created_at, updated_at
                )
                VALUES (?, 'signup_conversion_v1', ?, ?, ?, ?, 0, ?, '', '', '', NULL, '', '', '', '', ?, '', '', '{}', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["main_stage"],
                    item["sub_stage"],
                    1 if item["main_stage"] == "active" else 0,
                    1 if item["main_stage"] == "converted" else 0,
                    item["main_stage"],
                    item["entered_at"],
                ),
            )
            db.execute(
                """
                INSERT INTO customer_value_segment_current (
                    external_userid, segment, segment_rank, score, scoring_version, computed_reason, submission_id,
                    matched_question_ids_json, source_payload_json, evaluated_at, computed_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 'signup_conversion_question_hits_v1', 'seed', NULL, '[]', '{}', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
                """,
                (
                    item["external_userid"],
                    item["segment"],
                    3 if item["segment"] == "top" else (2 if item["segment"] == "core" else 1),
                    4 if item["segment"] == "top" else (3 if item["segment"] == "core" else 2),
                    item["entered_at"],
                    item["entered_at"],
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
    _seed_marketing_dispatch_history(app)
    _seed_automation_conversion_stage_board(app)
    save_response = client.put(
        "/api/admin/marketing-automation/config",
        json=_signup_conversion_config_payload(seed, core_threshold=2, top_threshold=5),
    )
    assert save_response.status_code == 200

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "自动化转化" in visible_text
    assert "当前状态" in visible_text
    assert "配置步骤" in visible_text
    assert "阶段分栏" in visible_text
    assert "重点用户分布" in visible_text
    assert "普通用户" in visible_text
    assert "重点用户" in visible_text
    assert "最高优先用户" in visible_text
    assert "待转化" in visible_text
    assert "最近处理情况" in visible_text
    assert "wm_dispatch_pending" in visible_text
    assert "等待 AI 接手" in visible_text
    assert "夜间暂停" in visible_text
    assert "客户已完成报名" in visible_text
    assert "23:00 后暂停启动" in visible_text
    assert "报名成功自动化问卷" in visible_text
    assert 'value="2"' in html
    assert 'value="5"' in html
    assert "const initialMarketingConfig" in html
    assert '"questionnaire_id": 81' in html or '"questionnaire_id":81' in html
    assert '/admin/automation-conversion/preview' in html
    assert '/admin/automation-conversion/stage/waiting-conversion' in html
    assert 'data-priority-card="regular_users"' in html
    assert 'data-priority-count="1"' in html
    assert 'data-priority-card="priority_users"' in html
    assert 'data-priority-count="5"' in html
    assert 'data-priority-card="highest_priority_users"' in html
    assert 'data-priority-count="4"' in html
    assert 'data-stage-main-stage="prospect"' in html
    assert 'data-total-count="5"' in html
    assert 'data-focus-count="4"' in html
    assert 'data-highest-priority-count="2"' in html
    assert 'data-today-new-count="4"' in html
    assert 'data-stage-main-stage="active"' in html
    assert 'data-total-count="3"' in html
    assert 'data-stage-main-stage="converted"' in html
    assert 'data-total-count="2"' in html
    assert 'id="automation-stage-detail-drawer"' in html
    assert not _contains_standalone_token(visible_text, "core")
    assert not _contains_standalone_token(visible_text, "top")
    assert not _contains_standalone_token(visible_text, "unknown")
    assert not _contains_standalone_token(visible_text, "normal")
    assert not _contains_standalone_token(visible_text, "pending")
    assert not _contains_standalone_token(visible_text, "acked")
    assert not _contains_standalone_token(visible_text, "blocked_quiet_hours")
    assert not _contains_standalone_token(visible_text, "converted_before_dispatch")
    assert "conversion dispatch log" not in visible_text
    assert "JSON" not in visible_text


def test_admin_automation_conversion_stage_detail_page_renders_filtered_customers(app, client):
    _seed_automation_conversion_stage_board(app)

    response = client.get("/admin/automation-conversion/stage/waiting-conversion")
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "待转化客户" in visible_text
    assert "wm_stage_wait_001" in visible_text
    assert "wm_stage_wait_002" in visible_text
    assert "wm_stage_wait_003" in visible_text
    assert "wm_stage_active_001" not in visible_text
    assert "手机号或客户编号" in visible_text

    filtered_response = client.get(
        "/admin/automation-conversion/stage/waiting-conversion",
        query_string={"keyword": "003"},
    )
    filtered_text = _visible_text(filtered_response.get_data(as_text=True))
    assert filtered_response.status_code == 200
    assert "wm_stage_wait_003" in filtered_text
    assert "wm_stage_wait_001" not in filtered_text


def test_admin_automation_conversion_preview_page_renders_runtime_search_shell(client):
    response = client.get("/admin/automation-conversion/preview")
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "客户试运行" in visible_text
    assert "手机号、客户姓名或客户编号" in visible_text
    assert "当前阶段" in visible_text
    assert "当前分层" in visible_text
    assert "命中题数" in visible_text
    assert "是否进入自动化" in visible_text
    assert "未进入原因" in visible_text
    assert "高级信息" in visible_text
    assert "/api/admin/customers/profile" in html
    assert "/api/customers?keyword=" in html
    assert "/api/admin/marketing-automation/config/preview" in html


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
    assert blocked_payload["dispatch_history"]["items"][0]["stage"] == "active/activated"


def test_admin_automation_conversion_page_dispatch_history_filter_renders_selected_status(app, client):
    _seed_marketing_dispatch_history(app)

    response = client.get("/admin/automation-conversion", query_string={"status": "night_pause"})
    html = response.get_data(as_text=True)
    visible_text = _visible_text(html)

    assert response.status_code == 200
    assert "最近处理情况" in visible_text
    assert "wm_dispatch_blocked" in visible_text
    assert "夜间暂停" in visible_text
    assert "wm_dispatch_pending" not in visible_text
