from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from werkzeug.security import generate_password_hash

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.admin_auth import save_admin_user


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "admin-slim-phase1.sqlite3"
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
            "SECRET_KEY": "test-secret-key",
            "ADMIN_AUTH_MODE": "wecom_sso",
        }
    )
    with app.app_context():
        init_db()
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def _authorize_admin_user(
    app,
    *,
    wecom_userid: str,
    roles: list[str],
    display_name: str | None = None,
    is_active: bool = True,
) -> None:
    with app.app_context():
        save_admin_user(
            {
                "wecom_userid": wecom_userid,
                "display_name": display_name or wecom_userid,
                "wecom_corpid": app.config["WECOM_CORP_ID"],
                "role_codes": roles,
                "is_active": "1" if is_active else "",
            },
            operator="test-suite",
        )


def _extract_state_from_redirect(location: str) -> str:
    parsed = urlparse(location)
    return parse_qs(parsed.query).get("state", [""])[0]


def _login_via_wecom(
    client,
    app,
    monkeypatch,
    *,
    wecom_userid: str,
    roles: list[str],
    next_path: str = "/admin/config/login-access",
    mode: str = "qr",
):
    try:
        _authorize_admin_user(app, wecom_userid=wecom_userid, roles=roles, display_name="Root Admin")
    except ValueError:
        pass
    start_response = client.get(f"/auth/wecom/start?mode={mode}&next={next_path}", follow_redirects=False)
    assert start_response.status_code == 302
    state = _extract_state_from_redirect(start_response.headers["Location"])
    monkeypatch.setattr(
        "wecom_ability_service.http.internal_auth.exchange_code_for_wecom_user",
        lambda code: {
            "wecom_userid": wecom_userid,
            "display_name": "Root Admin",
            "wecom_corpid": app.config["WECOM_CORP_ID"],
            "raw_identity": {"UserId": wecom_userid},
        },
    )
    return client.get(f"/auth/wecom/callback?code=mock-code&state={state}", follow_redirects=False)


def _enable_break_glass(app):
    app.config.update(
        ADMIN_BREAK_GLASS_LOGIN_ENABLED="true",
        ADMIN_BREAK_GLASS_USERNAME="bg-admin",
        ADMIN_BREAK_GLASS_PASSWORD_HASH=generate_password_hash("bg-password-123"),
    )


def test_unauthenticated_admin_request_redirects_to_login(client):
    response = client.get("/admin/automation-conversion", follow_redirects=False)

    assert response.status_code == 302
    assert "/login?next=/admin/automation-conversion" in response.headers["Location"]


def test_login_page_renders_wecom_entry(client):
    response = client.get("/login")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "企业微信登录" in html
    assert "企业微信扫码登录" in html
    assert "/auth/wecom/start" in html
    assert "mode=qr" in html


def test_auth_wecom_start_generates_qr_redirect(client):
    response = client.get("/auth/wecom/start?mode=qr&next=/admin/config", follow_redirects=False)
    parsed = urlparse(response.headers["Location"])
    query = parse_qs(parsed.query)

    assert response.status_code == 302
    assert parsed.netloc == "open.work.weixin.qq.com"
    assert parsed.path.endswith("/wwopen/sso/qrConnect")
    assert query["appid"] == ["ww-test"]
    assert query["agentid"] == ["1000002"]
    assert query["state"][0]


def test_auth_wecom_callback_builds_session_on_success(app, client, monkeypatch):
    callback_response = _login_via_wecom(
        client,
        app,
        monkeypatch,
        wecom_userid="root.admin",
        roles=["super_admin"],
        next_path="/admin/config/login-access",
    )

    assert callback_response.status_code == 302
    assert callback_response.headers["Location"].endswith("/admin/config/login-access")

    with client.session_transaction() as sess:
        assert sess["admin_session_user_id"] > 0
        assert sess["admin_session_wecom_userid"] == "root.admin"
        assert sess["admin_session_role_list"] == ["super_admin"]
        assert sess["admin_session_login_type"] == "wecom_qr"


def test_admin_root_redirects_to_automation_conversion(client):
    response = client.get("/admin", follow_redirects=False)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/automation-conversion")


def test_super_admin_navigation_restores_customer_primary_entry(app, client, monkeypatch):
    _login_via_wecom(client, app, monkeypatch, wecom_userid="root.admin", roles=["super_admin"], next_path="/admin/config")

    response = client.get("/admin/config")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动化运营" in html
    assert "客户" in html
    assert "问卷" in html
    assert "配置" in html
    assert "API 文档" in html
    assert 'href="/admin/customers"' in html
    assert 'href="/admin/user-ops"' not in html
    assert 'href="/admin/customer-pulse"' not in html
    assert 'href="/admin/followup-orchestrator"' not in html
    assert 'href="/admin/jobs"' not in html
    assert 'href="/admin/audit"' not in html
    assert 'href="/admin/system"' not in html


def test_legacy_mcp_redirects_to_api_docs_and_docs_page_renders(app, client, monkeypatch):
    _login_via_wecom(client, app, monkeypatch, wecom_userid="root.admin", roles=["super_admin"], next_path="/admin/api-docs")

    response = client.get("/admin/mcp", follow_redirects=False)
    docs_response = client.get("/admin/api-docs")
    docs_html = docs_response.get_data(as_text=True)

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/admin/api-docs")
    assert docs_response.status_code == 200
    assert "API 文档" in docs_html
    assert "企业微信 SSO 扫码登录" in docs_html
    assert "自动化运营" in docs_html
    assert "问卷" in docs_html
    assert "Webhook / 回调" in docs_html


def test_config_center_keeps_login_access_and_removes_mcp_tools_tab(app, client, monkeypatch):
    _login_via_wecom(client, app, monkeypatch, wecom_userid="root.admin", roles=["super_admin"], next_path="/admin/config")

    response = client.get("/admin/config")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "登录与权限" in html
    assert "AI 工具设置" not in html
    assert "/admin/config/mcp-tools" not in html


def test_core_pages_still_open_after_login(app, client, monkeypatch):
    _login_via_wecom(client, app, monkeypatch, wecom_userid="root.admin", roles=["super_admin"])

    automation_response = client.get("/admin/automation-conversion")
    customers_response = client.get("/admin/customers")
    questionnaire_response = client.get("/admin/questionnaires")
    config_response = client.get("/admin/config")

    assert automation_response.status_code == 200
    assert customers_response.status_code == 200
    assert questionnaire_response.status_code == 200
    assert config_response.status_code == 200


def test_role_access_and_viewer_write_restriction(app, client, monkeypatch):
    _authorize_admin_user(app, wecom_userid="auto.admin", roles=["automation_admin"])
    _authorize_admin_user(app, wecom_userid="viewer.admin", roles=["viewer"])

    _login_via_wecom(client, app, monkeypatch, wecom_userid="auto.admin", roles=["automation_admin"])
    automation_response = client.get("/admin/automation-conversion")
    forbidden_response = client.get("/admin/config")

    assert automation_response.status_code == 200
    assert forbidden_response.status_code == 403
    assert "无权限访问" in forbidden_response.get_data(as_text=True)

    client.get("/logout")
    _login_via_wecom(client, app, monkeypatch, wecom_userid="viewer.admin", roles=["viewer"])
    viewer_read_response = client.get("/admin/config")
    viewer_write_response = client.post("/admin/config/routing/owner-role", data={"userid": "owner-a"})

    assert viewer_read_response.status_code == 200
    assert viewer_write_response.status_code == 403


def test_login_access_page_renders_login_audit(app, client, monkeypatch):
    _login_via_wecom(client, app, monkeypatch, wecom_userid="root.admin", roles=["super_admin"], next_path="/admin/config/login-access")

    response = client.get("/admin/config/login-access")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "最近登录审计" in html
    assert "企微 UserId" in html


def test_sunset_pages_are_offline_and_logged(app, client, monkeypatch):
    _login_via_wecom(client, app, monkeypatch, wecom_userid="root.admin", roles=["super_admin"])

    response = client.get("/admin/jobs")
    html = response.get_data(as_text=True)

    assert response.status_code == 410
    assert "模块已下线" in html

    with app.app_context():
        row = get_db().execute(
            """
            SELECT target_type, target_id, action_type
            FROM admin_operation_logs
            WHERE target_type = 'sunset_route'
            ORDER BY id DESC
            LIMIT 1
            """
        ).fetchone()
        assert row is not None
        assert row["target_id"] == "/admin/jobs"
        assert row["action_type"] == "sunset_route_access"


def test_break_glass_can_login_when_enabled_and_fails_when_disabled(app, client):
    disabled_response = client.post(
        "/login",
        data={
            "login_type": "break_glass",
            "username": "bg-admin",
            "password": "bg-password-123",
        },
        follow_redirects=True,
    )
    assert disabled_response.status_code == 200
    assert "应急账号不可用" in disabled_response.get_data(as_text=True)

    _enable_break_glass(app)
    enabled_response = client.post(
        "/login",
        data={
            "login_type": "break_glass",
            "username": "bg-admin",
            "password": "bg-password-123",
            "next": "/admin/config/login-access",
        },
        follow_redirects=False,
    )

    assert enabled_response.status_code == 302
    assert enabled_response.headers["Location"].endswith("/admin/config/login-access")

    with client.session_transaction() as sess:
        assert sess["admin_session_login_type"] == "break_glass"
        assert sess["admin_session_role_list"] == ["super_admin"]
