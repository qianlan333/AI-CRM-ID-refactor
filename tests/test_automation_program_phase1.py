from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

from wecom_ability_service import create_app
from wecom_ability_service.db import get_db, init_db
from wecom_ability_service.domains.admin_auth import save_admin_user


@pytest.fixture()
def app(tmp_path):
    db_path = tmp_path / "automation-program-phase1.sqlite3"
    private_key_path = tmp_path / "wecom_private_key.pem"
    sdk_lib_path = tmp_path / "libWeWorkFinanceSdk_C.so"
    private_key_path.write_text("fake-key", encoding="utf-8")
    sdk_lib_path.write_text("fake-so", encoding="utf-8")

    app = create_app(
        {
            "TESTING": True,
            "DATABASE_PATH": str(db_path),
            "SECRET_KEY": "test-secret-key",
            "WECOM_CORP_ID": "ww-test",
            "WECOM_SECRET": "secret-test",
            "WECOM_CONTACT_SECRET": "contact-secret-test",
            "WECOM_AGENT_ID": "1000002",
            "WECOM_API_BASE": "http://fake-wecom.local",
            "WECOM_ARCHIVE_SECRET": "archive-secret",
            "WECOM_PRIVATE_KEY_PATH": str(private_key_path),
            "WECOM_SDK_LIB_PATH": str(sdk_lib_path),
            "WECOM_CALLBACK_TOKEN": "callback-token",
            "WECOM_CALLBACK_AES_KEY": "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFG",
            "ADMIN_AUTH_MODE": "wecom_sso",
        }
    )
    with app.app_context():
        init_db()
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


def test_default_program_bootstraps_and_automation_entry_lists_programs(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    response = client.get("/admin/automation-conversion")
    html = response.get_data(as_text=True)

    assert response.status_code == 200
    assert "自动化运营方案列表" in html
    assert "默认自动化转化方案" in html
    assert "新建方案" in html


def test_program_routes_render_and_legacy_routes_redirect(app, client, monkeypatch):
    _login(client, app, monkeypatch)
    program_id = _default_program_id(app)

    overview_response = client.get(f"/admin/automation-conversion/programs/{program_id}/overview")
    legacy_overview = client.get("/admin/automation-conversion/overview", follow_redirects=False)
    legacy_operations = client.get("/admin/automation-conversion/operations", follow_redirects=False)

    assert overview_response.status_code == 200
    assert "默认自动化转化方案" in overview_response.get_data(as_text=True)
    assert legacy_overview.status_code == 302
    assert legacy_overview.headers["Location"].endswith(f"/admin/automation-conversion/programs/{program_id}/overview")
    assert legacy_operations.status_code == 302
    assert legacy_operations.headers["Location"].endswith(f"/admin/automation-conversion/programs/{program_id}/operations")


def test_shared_and_runtime_compatibility_redirects(app, client, monkeypatch):
    _login(client, app, monkeypatch)

    agent_config = client.get("/admin/automation-conversion/agent-config", follow_redirects=False)
    run_center = client.get("/admin/automation-conversion/run-center", follow_redirects=False)

    assert agent_config.status_code == 302
    assert agent_config.headers["Location"].endswith("/admin/automation-conversion/shared/agents")
    assert run_center.status_code == 302
    assert run_center.headers["Location"].endswith("/admin/automation-conversion/runtime")


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

