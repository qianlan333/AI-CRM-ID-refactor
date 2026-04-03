from __future__ import annotations

import json

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-mcp-console.sqlite3"
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


def _seed_customer(app) -> None:
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO contacts (external_userid, customer_name, owner_userid, remark, description, updated_at)
            VALUES ('ext-1', '客户一', 'owner-a', '高意向', 'seed customer', '2026-04-02 09:30:00')
            """
        )
        db.execute(
            """
            INSERT INTO owner_role_map (userid, display_name, role, active)
            VALUES ('owner-a', '顾问甲', 'sales', 1)
            """
        )
        db.commit()


def test_admin_mcp_console_page_renders_registry_and_runtime(client):
    response = client.get("/admin/mcp")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "AI 工具控制台" in html
    assert "AI 工具连接状态" in html
    assert "工具清单" in html
    assert "试运行" in html
    assert "resolve_customer" in html
    assert "客户定位查询" in html


def test_admin_mcp_preflight_writes_audit_log(app, client):
    response = client.post("/admin/mcp/preflight", data={"operator": "tester-mcp"})
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "环境检查已执行。" in html
    assert "本次检查" in html

    with app.app_context():
        row = get_db().execute(
            """
            SELECT operator, target_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'mcp_preflight'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["operator"] == "tester-mcp"
        assert row["target_id"] == "/mcp"


def test_admin_mcp_sample_call_defaults_task_tool_to_dry_run(app, client):
    _seed_customer(app)

    response = client.post(
        "/admin/mcp/sample-call",
        data={
            "tool_name": "create_private_message_task",
            "arguments_json": json.dumps(
                {
                    "external_userid": "ext-1",
                    "content": "你好，跟进一下报名进度",
                },
                ensure_ascii=False,
            ),
            "operator": "tester-preview",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "试运行预览已生成。" in html
    assert "create_private_message_task" in html
    assert "实际执行否" in html

    with app.app_context():
        outbound_count = get_db().execute("SELECT COUNT(*) AS total FROM outbound_tasks").fetchone()["total"]
        log = get_db().execute(
            """
            SELECT operator, action_type, target_type, target_id
            FROM admin_operation_logs
            WHERE target_type = 'mcp_sample_call'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert outbound_count == 0
        assert log["operator"] == "tester-preview"
        assert log["action_type"] == "preview_mcp_sample_call"
        assert log["target_id"] == "create_private_message_task"


def test_admin_mcp_sample_call_blocks_live_high_risk_without_confirmation(app, client):
    _seed_customer(app)

    response = client.post(
        "/admin/mcp/sample-call",
        data={
            "tool_name": "create_private_message_task",
            "arguments_json": json.dumps(
                {
                    "external_userid": "ext-1",
                    "content": "需要立即发送",
                },
                ensure_ascii=False,
            ),
            "live_run": "1",
            "operator": "tester-live",
        },
    )
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "高风险工具需要二次确认" in html

    with app.app_context():
        outbound_count = get_db().execute("SELECT COUNT(*) AS total FROM outbound_tasks").fetchone()["total"]
        assert outbound_count == 0
