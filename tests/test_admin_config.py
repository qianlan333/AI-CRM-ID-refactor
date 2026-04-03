from __future__ import annotations

import json

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


def _mcp_list_tools(client, token: str = "mcp-token"):
    response = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {token}"},
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    return response.get_json()


def test_admin_config_pages_render(client):
    expected = {
        "/admin/config": "配置中心",
        "/admin/config/routing": "负责人 / 分配规则",
        "/admin/config/signup-tags": "报名标签规则",
        "/admin/config/class-term-tags": "班期标签规则",
        "/admin/config/app-settings": "系统设置",
        "/admin/config/mcp-tools": "AI 工具设置",
    }
    for path, marker in expected.items():
        response = client.get(path)
        html = response.get_data(as_text=True)
        assert response.status_code == 200
        assert marker in html
        assert "配置中心" in html


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
