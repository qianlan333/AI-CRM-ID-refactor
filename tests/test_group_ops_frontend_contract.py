from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GROUP_OPS_JS = ROOT / "aicrm_next/frontend_compat/static/admin_console/group_ops.js"
GROUP_OPS_TEMPLATE = ROOT / "aicrm_next/frontend_compat/templates/admin_console/group_ops.html"


def _source() -> str:
    return GROUP_OPS_TEMPLATE.read_text(encoding="utf-8") + "\n" + GROUP_OPS_JS.read_text(encoding="utf-8")


def _function_source(name: str) -> str:
    source = GROUP_OPS_JS.read_text(encoding="utf-8")
    start = source.index(f"function {name}")
    next_function = source.find("\n  function ", start + 1)
    return source[start:] if next_function == -1 else source[start:next_function]


@pytest.fixture()
def group_ops_frontend_client(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENV", "test")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "0")
    return TestClient(create_app(), raise_server_exceptions=False)


def test_group_ops_frontend_routes_are_owned_by_next(group_ops_frontend_client):
    for path in [
        "/admin/automation-conversion/group-ops/ui",
        "/admin/automation-conversion/group-ops/plans/1",
        "/admin/automation-conversion/group-ops/groups/ui",
    ]:
        response = group_ops_frontend_client.get(path)
        assert response.status_code == 200
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
        assert 'id="group-ops-app"' in response.text


def test_group_ops_list_frontend_contract_has_required_actions_and_columns():
    source = _source()

    assert "查看所有群" in source
    assert "创建计划" in source
    for label in ["运营计划", "已绑定群", "今日预估", "通知排队队列"]:
        assert label in source
    assert "<th>计划名称</th><th>类型</th><th>运营成员</th><th>绑定群</th><th>今日预估</th><th>状态</th><th>操作</th>" in source
    assert "编辑" in source
    assert "停用 / 删除" in source
    assert 'name="create_plan_type"' in source
    assert "标准编排计划" in source
    assert "Webhook 接收计划" in source
    assert "create_owner_userid" in source
    assert "apiMembers" in source
    assert "/api/admin/common/operation-members?scope=group_ops" in source
    assert "OperationMemberPicker.open" in source
    assert "create_owner_userid_text" not in source
    assert '"owner_001"' not in source

    for forbidden in ["下一次动作", "计划详情", "队列策略", "可发主体", "管理员判断"]:
        assert forbidden not in source


def test_group_ops_detail_frontend_contract_matches_standard_and_webhook_requirements():
    source = _source()
    detail_source = _function_source("renderDetail")

    for label in ["返回列表", "保存计划", "运营成员", "刷新名下群聊", "绑定群", "选择群"]:
        assert label in source
    for label in ["绑定群", "内部联系人", "外部联系人", "预计通知"]:
        assert label in source
    for label in ["第几天", "发送时间", "动作标题", "标准话术摘要", "素材标签", "编辑 / 删除"]:
        assert label in source
    assert "添加动作" in source
    assert "open-node-modal" in source
    assert "group-ops__modal" in source
    assert "group_picker_keyword" in source
    assert "groupPickerNotice" in source
    assert "绑定中" in source
    assert "requestErrorMessage(error, \"绑定失败\")" in source
    assert "配置话术和素材" in source
    assert "AICRMSendContentComposer.open" in source
    assert "配置群运营动作内容" in source
    assert "save-node" in source
    assert "delete-node" in source
    assert "node_" + "attachments" not in source
    assert "node_" + "text_content" not in source
    assert "素材 " + "JSON" not in source
    assert 'data-action="noop"' not in source
    assert "data-available-groups" not in source
    assert "renderAvailableGroups" not in source
    assert "素材 JSON" not in source
    for forbidden_time in ["入群后 10 分钟", "入群后 30 分钟", "入群后 1 小时"]:
        assert forbidden_time not in GROUP_OPS_JS.read_text(encoding="utf-8")
    for label in ["接收方式", "默认动作", "Webhook 接收地址", "POST", "复制地址", "Token 状态 / 重置入口", "Token："]:
        assert label in source
    assert "一次性 token" in source
    assert "复制后不可再次查看" in source

    for forbidden in ["适用场景", "JSON 示例", "请求字段说明大表", "请求字段说明", "明文 token", "明文 Token"]:
        assert forbidden not in source
    assert "查看所有群" not in detail_source
    assert "创建计划" not in detail_source
    assert "保存接口计划" not in detail_source


def test_group_ops_detail_refresh_owner_groups_contract_is_manual_and_owner_scoped():
    source = _source()
    refresh_source = _function_source("refreshOwnerGroups")

    assert "刷新名下群聊" in source
    assert "/api/admin/automation-conversion/group-ops/groups/sync" in source
    assert "owner_userid: owner" in refresh_source
    assert 'operator: "admin_ui"' in refresh_source
    assert "limit: 100" in refresh_source
    assert "owner_userid=${encodeURIComponent(owner)}" in refresh_source
    assert "已刷新：新增" in refresh_source
    assert "requestErrorMessage(error" in refresh_source
    assert "loadDetailPage(state.plan.id)" not in refresh_source


def test_group_ops_detail_refresh_error_uses_backend_sync_reason():
    source = _source()
    error_source = _function_source("requestErrorMessage")

    assert "payload.error_message" in error_source
    assert "detail.detail" in error_source
    assert "detail.error_code" in error_source
    assert "Conflict" not in error_source


def test_group_ops_detail_scheduled_time_options_contract():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(GROUP_OPS_JS))}, "utf8");
const app = {{
  dataset: {{}},
  querySelectorAll() {{ return []; }},
  querySelector() {{ return null; }},
  innerHTML: ""
}};
const sandbox = {{
  window: {{}},
  document: {{ getElementById() {{ return app; }} }},
  Intl
}};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
console.log(JSON.stringify(sandbox.window.AICRMGroupOpsContentAdapter.scheduledTimeOptions()));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    options = json.loads(result.stdout)

    assert "08:00" in options
    assert "20:30" in options
    assert "23:30" in options
    assert "07:30" not in options
    assert "24:00" not in options


def test_group_ops_detail_imports_standard_send_content_assets():
    source = _source()

    assert "send_content_composer.js" in source
    assert "send_content_composer.css" in source
    assert "material_picker.js" in source
    assert "material_picker.css" in source
    for forbidden in [
        "/api/admin/image-" + "library",
        "/api/admin/miniprogram-" + "library",
        "/api/admin/attachment-" + "library",
        "groupOpsMaterial" + "Pick" + "er",
    ]:
        assert forbidden not in source


def test_group_ops_frontend_content_package_adapter_round_trips():
    script = f"""
const fs = require("fs");
const vm = require("vm");
const source = fs.readFileSync({json.dumps(str(GROUP_OPS_JS))}, "utf8");
const app = {{
  dataset: {{}},
  querySelectorAll() {{ return []; }},
  querySelector() {{ return null; }},
  innerHTML: ""
}};
const sandbox = {{
  window: {{}},
  document: {{ getElementById() {{ return app; }} }},
  Intl
}};
vm.createContext(sandbox);
vm.runInContext(source, sandbox);
const adapter = sandbox.window.AICRMGroupOpsContentAdapter;
const fromOld = adapter.nodeToContentPackage({{ text_content: "  老话术  ", attachments: [{{msgtype:"image"}}] }});
const fromPackage = adapter.nodeToContentPackage({{
  content_package_json: {{
    content_text: "  新话术  ",
    image_library_ids: [12, "12", 34],
    miniprogram_library_ids: ["56"],
    attachment_library_ids: "78, 78, 90"
  }}
}});
const toNode = adapter.contentPackageToNodePayload({{
  content_text: "  保存话术  ",
  image_library_ids: ["101", 102],
  miniprogram_library_ids: [201],
  attachment_library_ids: ["301", "301", 302]
}});
const empty = adapter.normalizeContentPackage({{}});
console.log(JSON.stringify({{ fromOld, fromPackage, toNode, empty }}));
"""
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    payload = json.loads(result.stdout)

    assert payload["fromOld"] == {
        "content_text": "老话术",
        "image_library_ids": [],
        "miniprogram_library_ids": [],
        "attachment_library_ids": [],
    }
    assert payload["fromPackage"] == {
        "content_text": "新话术",
        "image_library_ids": [12, 34],
        "miniprogram_library_ids": [56],
        "attachment_library_ids": [78, 90],
    }
    assert payload["toNode"] == {
        "text_content": "保存话术",
        "content_package_json": {
            "content_text": "保存话术",
            "image_library_ids": [101, 102],
            "miniprogram_library_ids": [201],
            "attachment_library_ids": [301, 302],
        },
    }
    assert payload["empty"] == {
        "content_text": "",
        "image_library_ids": [],
        "miniprogram_library_ids": [],
        "attachment_library_ids": [],
    }


def test_group_ops_all_groups_frontend_contract_has_only_required_columns():
    source = _source()

    for label in ["群名 / 群 ID", "群主", "所属计划", "已绑定 / 未绑定"]:
        assert label in source
    assert "<th>群名</th><th>群 ID</th><th>群主</th><th>所属计划</th><th>状态</th>" in source

    for forbidden in ["群规模", "谁可发谁不可发", "下一次动作"]:
        assert forbidden not in source
