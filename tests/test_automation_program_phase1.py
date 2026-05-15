from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

import pytest

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.admin_auth import save_admin_user


@pytest.fixture()
def app(tmp_path):
    from tests.conftest import build_pg_test_app

    with build_pg_test_app(tmp_path, SECRET_KEY="test-secret-key", ADMIN_AUTH_MODE="wecom_sso") as app:
        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _authorize_admin(app) -> None:
    with app.app_context():
        save_admin_user(
            {
                "wecom_userid": "root.admin",
                "display_name": "Root Admin",
                "wecom_corpid": app.config["WECOM_CORP_ID"],
                "role_codes": ["super_admin"],
                "is_active": "1",
            },
            operator="test-suite",
        )


def _login(client, app, monkeypatch) -> None:
    _authorize_admin(app)
    start_response = client.get("/auth/wecom/start?mode=qr&next=/admin/automation-conversion", follow_redirects=False)
    state = parse_qs(urlparse(start_response.headers["Location"]).query)["state"][0]
    monkeypatch.setattr(
        "wecom_ability_service.http.internal_auth.exchange_code_for_wecom_user",
        lambda code: {
            "wecom_userid": "root.admin",
            "display_name": "Root Admin",
            "wecom_corpid": app.config["WECOM_CORP_ID"],
            "raw_identity": {"UserId": "root.admin"},
        },
    )
    callback_response = client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)
    assert callback_response.status_code == 302


def _default_program_id(app) -> int:
    with app.app_context():
        row = get_db().execute(
            "SELECT id FROM automation_program WHERE program_code = 'signup_conversion_v1' LIMIT 1"
        ).fetchone()
        return int(row["id"])


def _admin_action_token(html: str) -> str:
    match = re.search(r'name="admin_action_token" value="([^"]+)"', html)
    assert match
    return match.group(1)


def _program_row(html: str, program_id: int) -> str:
    match = re.search(rf'<tr id="program-row-{program_id}".*?</tr>', html, flags=re.S)
    assert match
    return match.group(0)


def test_default_program_bootstraps_and_automation_entry_lists_programs(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)
    program_id = _default_program_id(app)
    default_row = _program_row(html, program_id)

    assert response.status_code == 200
    assert "自动化运营方案" in html
    assert "id=\"program-create-panel\" class=\"admin-card program-panel\" hidden" in html
    assert "共享资源" in html
    assert "/admin/automation-conversion/shared/agents" in html
    assert "运行时中心" in html
    assert "/admin/automation-conversion/runtime" in html
    assert "新建方案" in html
    assert "默认自动化转化方案" in html
    assert "方案列表" in html
    assert f'href="/admin/automation-conversion/programs/{program_id}/overview">编辑</a>' in default_row
    assert ">进入</a>" not in default_row
    assert "edit_program_id" not in default_row
    assert "复制" in html
    assert ("停用" in html) or ("启用" in html)
    assert "归档" in html


def test_program_routes_render_and_removed_legacy_routes_404(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    overview_response = client.get(f"/admin/automation-conversion/programs/{program_id}/overview")
    operations_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations")
    flow_design_response = client.get(f"/admin/automation-conversion/programs/{program_id}/flow-design")
    member_ops_response = client.get(f"/admin/automation-conversion/programs/{program_id}/member-ops")
    workflow_new_response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations/workflows/new")
    executions_response = client.get(f"/admin/automation-conversion/programs/{program_id}/executions")
    legacy_overview = client.get("/admin/automation-conversion/overview", follow_redirects=False)
    legacy_operations = client.get("/admin/automation-conversion/operations", follow_redirects=False)
    legacy_flow_design = client.get("/admin/automation-conversion/flow-design", follow_redirects=False)
    legacy_member_ops = client.get("/admin/automation-conversion/member-ops", follow_redirects=False)

    assert overview_response.status_code == 200
    assert operations_response.status_code == 200
    assert flow_design_response.status_code == 200
    assert member_ops_response.status_code == 200
    assert workflow_new_response.status_code == 200
    assert executions_response.status_code == 200
    assert "默认自动化转化方案" in overview_response.get_data(as_text=True)
    assert legacy_overview.status_code == 404
    assert legacy_operations.status_code == 404
    assert legacy_flow_design.status_code == 404
    assert legacy_member_ops.status_code == 404

    assert client.get("/admin/automation-conversion/operations/workflows/new").status_code == 404
    assert client.get("/admin/automation-conversion/operations/workflows/1/edit").status_code == 404
    assert client.get("/admin/automation-conversion/operations/workflows/1/nodes").status_code == 404
    assert client.get("/admin/automation-conversion/operations/executions").status_code == 404


def test_program_basic_info_edit_updates_list_and_context_header(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)
    list_response = client.get("/admin/automation-conversion")
    token = _admin_action_token(list_response.get_data(as_text=True))

    update_response = client.post(
        f"/admin/automation-conversion/programs/{program_id}/update",
        data={
            "admin_action_token": token,
            "program_name": "默认自动化转化方案 UI 已编辑",
            "description": "列表页编辑后的方案说明",
            "next": "/admin/automation-conversion",
        },
        follow_redirects=False,
    )
    assert update_response.status_code == 302

    updated_list = client.get("/admin/automation-conversion").get_data(as_text=True)
    assert "默认自动化转化方案 UI 已编辑" in updated_list
    assert "列表页编辑后的方案说明" in updated_list

    updated_context = client.get(f"/admin/automation-conversion/programs/{program_id}/overview").get_data(as_text=True)
    assert "默认自动化转化方案 UI 已编辑" in updated_context
    assert "列表页编辑后的方案说明" not in updated_context
    assert "编辑方案信息" not in updated_context
    assert "内部编码" not in updated_context


def test_archived_program_badge_renders(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_program (
                program_code, program_name, description, status, config_json, created_by, updated_by
            )
            VALUES ('archived_ui_case', '归档 UI 方案', '归档状态展示用例', 'archived', '{}', 'test', 'test')
            """
        )
        db.commit()

    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "归档 UI 方案" in html
    assert "program-status--archived" in html
    assert ">归档</span>" in html


def test_removed_shared_and_runtime_legacy_routes_are_gone(app, client, monkeypatch):
    _login(client, app, monkeypatch)

    legacy_agent_config = client.get("/admin/automation-conversion/agent-config", follow_redirects=False)
    legacy_run_center = client.get("/admin/automation-conversion/run-center", follow_redirects=False)
    shared_agents = client.get("/admin/automation-conversion/shared/agents", follow_redirects=False)
    runtime = client.get("/admin/automation-conversion/runtime", follow_redirects=False)

    assert legacy_agent_config.status_code == 404
    assert legacy_run_center.status_code == 404
    assert shared_agents.status_code == 200
    assert runtime.status_code == 200


def test_workflow_list_filters_by_program_id(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    default_program_id = _default_program_id(app)
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO automation_program (program_code, program_name, status, config_json)
            VALUES ('secondary_program', '第二方案', 'active', '{}')
            """
        )
        second_program_id = int(db.execute("SELECT id FROM automation_program WHERE program_code = 'secondary_program'").fetchone()["id"])
        db.execute(
            """
            INSERT INTO automation_workflow (
                program_id, workflow_code, workflow_name, status, created_by, updated_by
            )
            VALUES
                (?, 'default_wf', '默认任务流', 'active', 'test', 'test'),
                (?, 'second_wf', '第二任务流', 'active', 'test', 'test')
            """,
            (default_program_id, second_program_id),
        )
        db.commit()

    default_response = client.get(f"/api/admin/automation-conversion/workflows?program_id={default_program_id}")
    second_response = client.get(f"/api/admin/automation-conversion/workflows?program_id={second_program_id}")

    default_codes = [item["workflow"]["workflow_code"] for item in default_response.get_json()["items"]]
    second_codes = [item["workflow"]["workflow_code"] for item in second_response.get_json()["items"]]
    assert default_codes == ["default_wf"]
    assert second_codes == ["second_wf"]


def test_operation_action_templates_and_from_template_create_current_workflow(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    templates_response = client.get("/api/admin/automation-conversion/action-templates")
    assert templates_response.status_code == 200
    templates_payload = templates_response.get_json()
    template_names = {item["template_name"] for item in templates_payload["items"]}
    assert {"问卷提交后跟进", "未填问卷提醒", "低互动用户唤醒"}.issubset(template_names)
    assert {item["template_source"] for item in templates_payload["items"]} >= {"builtin"}

    local_response = client.post(
        "/api/admin/automation-conversion/action-templates",
        json={
            "template_name": "本地提醒模板",
            "template_source": "crm_local",
            "category": "questionnaire",
            "description": "用于本地沉淀",
            "default_config": {
                "action_name": "本地提醒模板",
                "content_strategy": "standard_content",
                "standard_content_text": "请完成问卷",
            },
            "workflow_blueprint": {
                "audiences": ["pending_questionnaire"],
                "generation_mode": "manual_layered",
            },
            "node_blueprints": [
                {
                    "node_name": "本地提醒节点",
                    "target_audience_code": "pending_questionnaire",
                    "trigger_mode": "daily_recurring",
                    "day_offset": 1,
                    "send_time": "10:00",
                    "content_mode": "standard_direct",
                    "standard_content_text": "请完成问卷",
                }
            ],
        },
    )
    assert local_response.status_code == 201
    assert local_response.get_json()["template"]["template_source"] == "crm_local"

    create_response = client.post(
        f"/api/admin/automation-conversion/programs/{program_id}/actions/from-template",
        json={
            "template_code": "questionnaire_pending_reminder",
            "config": {
                "action_name": "提醒填写问卷动作",
                "content_strategy": "standard_content",
                "standard_content_text": "请先完成问卷，我会根据结果给你后续建议。",
                "status": "draft",
            },
        },
    )
    assert create_response.status_code == 201
    created_payload = create_response.get_json()
    workflow = created_payload["workflow_bundle"]["workflow"]
    nodes = created_payload["workflow_bundle"]["nodes"]
    assert workflow["workflow_name"] == "提醒填写问卷动作"
    assert workflow["generation_mode"] == "manual_layered"
    assert nodes[0]["node_name"] == "提醒用户填写问卷"
    assert nodes[0]["standard_content_text"] == "请先完成问卷，我会根据结果给你后续建议。"

    from_workflow_response = client.post(
        "/api/admin/automation-conversion/action-templates/from-workflow",
        json={
            "workflow_id": created_payload["workflow_id"],
            "template_name": "从动作保存模板",
            "description": "反向保存",
        },
    )
    assert from_workflow_response.status_code == 201
    saved_template = from_workflow_response.get_json()["template"]
    assert saved_template["template_source"] == "crm_local"
    assert saved_template["template_name"] == "从动作保存模板"


def test_action_orchestration_page_is_main_operations_entry(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    response = client.get(f"/admin/automation-conversion/programs/{program_id}/operations")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "运营动作" in html
    assert "新增动作" in html
    assert "从模板创建" in html
    assert "保存草稿" in html
    assert "触发与对象" in html
    assert "内容策略" in html
    assert "执行节点" in html
    assert "action-list-feedback" in html
    assert "正在加载..." in html
    assert "复制中..." in html
    assert "这个动作选择了「Agent 单人定制化」，必须先选择 1 个智能体后才能保存。" in html
    assert "当前还没有可用智能体，请先创建或启用一个智能体，再保存 Agent 单人定制化动作。" in html
    assert "当前选择的智能体不可用，请重新选择。" in html
    assert "保存并启用" not in html
    assert "执行预览" not in html
    assert "在一个页面里维护当前方案下所有运营动作" not in html


def test_ai_action_template_generate_returns_chinese_error_when_model_unavailable(app, client, monkeypatch):
    _login(client, app, monkeypatch)

    response = client.post(
        "/api/admin/automation-conversion/action-templates/generate",
        json={
            "business_goal": "用户加入社群后，如果 3 天内没填问卷，就自动发提醒。",
            "preference": "尽量简单，一个节点优先",
        },
    )

    assert response.status_code == 400
    assert response.get_json()["error"] == "AI 模板生成失败，请稍后重试或改用 CRM 本地创建"
