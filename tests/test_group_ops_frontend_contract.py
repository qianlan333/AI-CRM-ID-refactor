from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
GROUP_OPS_JS = ROOT / "aicrm_next/frontend_compat/static/admin_console/group_ops.js"
GROUP_OPS_TEMPLATE = ROOT / "aicrm_next/frontend_compat/templates/admin_console/group_ops.html"


def _source() -> str:
    return GROUP_OPS_TEMPLATE.read_text(encoding="utf-8") + "\n" + GROUP_OPS_JS.read_text(encoding="utf-8")


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

    for label in ["返回列表", "保存计划", "保存接口计划", "运营成员", "绑定群", "固定群包"]:
        assert label in source
    for label in ["绑定群", "内部联系人", "外部联系人", "预计通知"]:
        assert label in source
    for label in ["第几天", "时间", "动作标题", "标准话术摘要", "素材标签", "编辑 / 删除"]:
        assert label in source
    assert "添加动作" in source
    assert "save-node" in source
    assert "delete-node" in source
    assert 'data-action="noop"' not in source
    for label in ["接收方式", "默认动作", "Webhook 接收地址", "POST", "复制地址", "Token 状态 / 重置入口", "Token："]:
        assert label in source
    assert "一次性 token" in source
    assert "复制后不可再次查看" in source

    for forbidden in ["适用场景", "JSON 示例", "请求字段说明大表", "请求字段说明", "明文 token", "明文 Token"]:
        assert forbidden not in source


def test_group_ops_all_groups_frontend_contract_has_only_required_columns():
    source = _source()

    for label in ["群名 / 群 ID", "群主", "所属计划", "已绑定 / 未绑定"]:
        assert label in source
    assert "<th>群名</th><th>群 ID</th><th>群主</th><th>所属计划</th><th>状态</th>" in source

    for forbidden in ["群规模", "谁可发谁不可发", "下一次动作"]:
        assert forbidden not in source
