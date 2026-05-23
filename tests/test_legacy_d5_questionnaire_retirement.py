from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_text(encoding="utf-8")


def _route_methods() -> dict[str, set[str]]:
    pytest.importorskip("flask")
    from wecom_ability_service import create_app

    app = create_app({"TESTING": True})
    routes: dict[str, set[str]] = {}
    for rule in app.url_map.iter_rules():
        routes.setdefault(rule.rule, set()).update(set(rule.methods) - {"HEAD", "OPTIONS"})
    return routes


def test_legacy_flask_no_longer_registers_admin_questionnaire_readonly_get_routes() -> None:
    routes = _route_methods()
    retired = [
        "/admin/questionnaires",
        "/admin/questionnaires/ui",
        "/admin/questionnaires/new",
        "/admin/questionnaires/<int:questionnaire_id>",
        "/api/admin/questionnaires",
        "/api/admin/questionnaires/preflight",
        "/api/admin/questionnaires/<int:questionnaire_id>",
        "/api/admin/questionnaires/<int:questionnaire_id>/latest-submit-debug",
        "/api/admin/questionnaires/<int:questionnaire_id>/export",
    ]
    for route in retired:
        assert "GET" not in routes.get(route, set()), route


def test_legacy_flask_no_longer_registers_public_questionnaire_readonly_get_routes() -> None:
    routes = _route_methods()
    retired = [
        "/s/<slug>",
        "/s/<slug>/submitted",
        "/s/<slug>/result/<result_token>",
        "/api/h5/questionnaires/<slug>",
    ]
    for route in retired:
        assert "GET" not in routes.get(route, set()), route


def test_legacy_flask_preserves_admin_write_and_console_write_fallback_routes() -> None:
    routes = _route_methods()
    assert "POST" in routes["/api/admin/questionnaires"]
    assert {"PUT", "DELETE"} <= routes["/api/admin/questionnaires/<int:questionnaire_id>"]
    assert "POST" in routes["/api/admin/questionnaires/<int:questionnaire_id>/disable"]
    assert "POST" in routes["/admin/questionnaires/<int:questionnaire_id>/save"]
    assert "POST" in routes["/admin/questionnaires/<int:questionnaire_id>/toggle"]


def test_legacy_flask_preserves_public_submit_oauth_diagnostics_and_push_fallback_routes() -> None:
    routes = _route_methods()
    assert "POST" in routes["/api/h5/questionnaires/<slug>/submit"]
    assert "GET" in routes["/api/h5/wechat/oauth/start"]
    assert "GET" in routes["/api/h5/wechat/oauth/callback"]
    assert "POST" in routes["/api/h5/questionnaires/<slug>/client-diagnostics"]
    assert "GET" in routes["/api/debug/questionnaire/session"]
    for route in [
        "/admin/questionnaires/external-push-logs",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs",
    ]:
        assert "GET" in routes[route]
    for route in [
        "/admin/questionnaires/external-push-logs/retry-batch",
        "/admin/questionnaires/external-push-logs/<int:push_log_id>/retry",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/<int:push_log_id>/retry",
        "/admin/questionnaires/<int:questionnaire_id>/external-push-logs/retry-batch",
    ]:
        assert "POST" in routes[route]


def test_questionnaire_mixed_modules_keep_only_non_readonly_route_registrations() -> None:
    admin_source = _read("wecom_ability_service/http/admin_questionnaires.py")
    console_source = _read("wecom_ability_service/http/admin_questionnaire_console.py")
    public_source = _read("wecom_ability_service/http/public_questionnaires.py")
    for source in [admin_source, console_source, public_source]:
        route_lines = [line.strip() for line in source.splitlines() if "bp.route(" in line]
        assert not [line for line in route_lines if "methods=['GET']" in line or 'methods=["GET"]' in line]


def test_questionnaire_fallback_files_still_exist() -> None:
    for path in [
        "wecom_ability_service/http/admin_questionnaires.py",
        "wecom_ability_service/http/admin_questionnaire_console.py",
        "wecom_ability_service/http/public_questionnaires.py",
        "wecom_ability_service/http/public_questionnaire_oauth.py",
        "wecom_ability_service/http/public_questionnaire_diagnostics.py",
        "wecom_ability_service/http/admin_questionnaire_push_logs.py",
        "wecom_ability_service/http/questionnaire_support.py",
        "wecom_ability_service/domains/questionnaire/service.py",
    ]:
        assert (REPO_ROOT / path).exists(), path


def test_aicrm_next_questionnaire_readonly_routes_are_served_by_ai_crm_next() -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    from aicrm_next.main import create_app
    from aicrm_next.questionnaire.repo import reset_questionnaire_fixture_state

    reset_questionnaire_fixture_state()
    client = TestClient(create_app())
    list_response = client.get("/api/admin/questionnaires")
    assert list_response.status_code == 200
    assert list_response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    item = (list_response.json().get("items") or [])[0]
    questionnaire_id = item["id"]
    slug = item["slug"]
    debug_payload = client.get(f"/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug").json()
    submission_id = debug_payload["submission"]["submission_id"]

    for path in [
        "/admin/questionnaires",
        "/admin/questionnaires/ui",
        "/api/admin/questionnaires/preflight",
        f"/api/admin/questionnaires/{questionnaire_id}",
        f"/api/admin/questionnaires/{questionnaire_id}/latest-submit-debug",
        f"/api/admin/questionnaires/{questionnaire_id}/export",
        f"/s/{slug}",
        f"/api/h5/questionnaires/{slug}",
        f"/api/h5/questionnaires/{slug}/result/{submission_id}",
    ]:
        response = client.get(path)
        assert response.status_code == 200, path
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"

    export_response = client.get(f"/api/admin/questionnaires/{questionnaire_id}/export")
    assert export_response.status_code == 200
    assert export_response.headers["Content-Disposition"].startswith('attachment; filename="')


def test_public_h5_page_uses_production_facade_when_database_ready(monkeypatch) -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    import aicrm_next.questionnaire.api as questionnaire_api
    from aicrm_next.main import create_app

    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        questionnaire_api,
        "get_public_questionnaire_from_legacy",
        lambda slug: {
            "ok": True,
            "questionnaire": {
                "id": 21,
                "slug": slug,
                "title": "真实生产公开问卷",
                "description": "生产 PostgreSQL facade 问卷",
                "enabled": True,
                "redirect_url": "",
                "submit_button_text": "提交",
                "created_at": datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 22, 0, 1, tzinfo=timezone.utc),
            },
            "questions": [
                {
                    "id": 348,
                    "type": "mobile",
                    "title": "请输入手机号",
                    "required": True,
                    "options": [],
                    "placeholder_text": "请输入手机号",
                }
            ],
            "source_status": "production_postgres",
        },
    )

    response = TestClient(create_app()).get("/s/q-20260414135818-5d8fba")

    assert response.status_code == 200
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"
    assert "真实生产公开问卷" in response.text
    assert "请输入手机号" in response.text
    assert "InMemoryQuestionnaireRepository" not in response.text
    assert "fake OAuth" not in response.text


def test_next_admin_questionnaire_detail_keeps_questions_nested_and_public_hides_sidebar_mapping(monkeypatch) -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    import aicrm_next.questionnaire.api as questionnaire_api
    from aicrm_next.main import create_app

    legacy_payload = {
        "ok": True,
        "questionnaire": {
            "id": 21,
            "slug": "real-questionnaire",
            "title": "真实生产问卷",
            "description": "生产 PostgreSQL facade 问卷",
            "enabled": True,
        },
        "questions": [
            {
                "id": 348,
                "type": "textarea",
                "title": "真实生产题目",
                "required": True,
                "options": [],
                "placeholder_text": "请输入",
                "sidebar_profile_field": "needs_blockers_followup",
            }
        ],
        "source_status": "production_postgres",
    }
    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    monkeypatch.setattr(questionnaire_api, "get_questionnaire_detail_from_legacy", lambda questionnaire_id: legacy_payload)
    monkeypatch.setattr(questionnaire_api, "get_public_questionnaire_from_legacy", lambda slug: legacy_payload)

    client = TestClient(create_app())
    admin_payload = client.get("/api/admin/questionnaires/21").json()
    public_payload = client.get("/api/h5/questionnaires/real-questionnaire").json()

    assert admin_payload["questionnaire"]["questions"][0]["title"] == "真实生产题目"
    assert admin_payload["questionnaire"]["questions"][0]["sidebar_profile_field"] == "needs_blockers_followup"
    assert "questions" in admin_payload
    assert "sidebar_profile_field" not in public_payload["questions"][0]


def test_public_h5_page_uses_legacy_wechat_oauth_gate_when_wechat_browser(monkeypatch) -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    import aicrm_next.integration_gateway.legacy_flask_facade as legacy_facade
    import aicrm_next.questionnaire.api as questionnaire_api
    from aicrm_next.main import create_app

    monkeypatch.setenv("SECRET_KEY", "questionnaire-oauth-test-secret")
    monkeypatch.setenv("WECHAT_MP_APP_ID", "wx-questionnaire-app")
    monkeypatch.setenv("WECHAT_MP_APP_SECRET", "questionnaire-secret")
    legacy_facade._legacy_app.cache_clear()
    monkeypatch.setattr(questionnaire_api, "production_data_ready", lambda: True)
    monkeypatch.setattr(
        questionnaire_api,
        "get_public_questionnaire_from_legacy",
        lambda slug: {
            "ok": True,
            "questionnaire": {
                "id": 21,
                "slug": slug,
                "title": "真实生产公开问卷",
                "description": "生产 PostgreSQL facade 问卷",
                "enabled": True,
                "redirect_url": "",
                "submit_button_text": "提交",
                "created_at": datetime(2026, 5, 22, 0, 0, tzinfo=timezone.utc),
                "updated_at": datetime(2026, 5, 22, 0, 1, tzinfo=timezone.utc),
            },
            "questions": [
                {
                    "id": 348,
                    "type": "mobile",
                    "title": "请输入手机号",
                    "required": True,
                    "options": [],
                    "placeholder_text": "请输入手机号",
                }
            ],
            "source_status": "production_postgres",
        },
    )

    response = TestClient(create_app()).get(
        "/s/q-20260414135818-5d8fba?campaign_id=cmp-001",
        headers={"User-Agent": "Mozilla/5.0 MicroMessenger"},
    )

    assert response.status_code == 200
    assert "授权后即可填写问卷信息。" in response.text
    assert "/api/h5/wechat/oauth/start?slug=q-20260414135818-5d8fba&amp;campaign_id=cmp-001" in response.text
    assert "fake OAuth" not in response.text


def test_questionnaire_oauth_start_forwards_to_legacy_wechat_authorize(monkeypatch) -> None:
    testclient_module = pytest.importorskip("fastapi.testclient")
    TestClient = testclient_module.TestClient
    import aicrm_next.integration_gateway.legacy_flask_facade as legacy_facade
    from aicrm_next.main import create_app

    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://route:route@127.0.0.1:1/aicrm_route")
    monkeypatch.setenv("SECRET_KEY", "questionnaire-oauth-test-secret")
    monkeypatch.setenv("WECHAT_MP_APP_ID", "wx-questionnaire-app")
    monkeypatch.setenv("WECHAT_MP_APP_SECRET", "questionnaire-secret")
    monkeypatch.setenv("AICRM_PUBLIC_BASE_URL", "https://www.youcangogogo.com")
    legacy_facade._legacy_app.cache_clear()

    response = TestClient(create_app()).get(
        "/api/h5/wechat/oauth/start?slug=q-20260414135818-5d8fba&campaign_id=cmp-001",
        follow_redirects=False,
    )

    assert response.status_code == 302
    assert response.headers["X-AICRM-Compatibility-Facade"] == "legacy_flask_facade"
    assert response.headers["location"].startswith("https://open.weixin.qq.com/connect/oauth2/authorize?")
    assert "appid=wx-questionnaire-app" in response.headers["location"]
    assert "redirect_uri=https%3A%2F%2Fwww.youcangogogo.com%2Fapi%2Fh5%2Fwechat%2Foauth%2Fcallback" in response.headers["location"]


def test_questionnaire_readonly_smoke_declares_submit_oauth_and_external_paths_not_executed() -> None:
    from tools import questionnaire_readonly_gray_smoke as gray_smoke

    args = gray_smoke.build_parser().parse_args(["--next-testclient", "--output-md", "/tmp/questionnaire.md", "--output-json", "/tmp/questionnaire.json"])
    report = gray_smoke.run_smoke(args)
    safety = report["side_effect_safety"]
    assert safety["old_submit_executed"] is False
    assert safety["real_oauth_executed"] is False
    assert safety["wecom_tag_executed"] is False
    assert safety["external_webhook_executed"] is False
    assert any(item["reason"] == "fake_submit_not_requested" for item in report["skipped"])


def test_app_py_default_is_still_next_and_legacy_fallback_exists() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert "uvicorn.run(NEXT_APP_IMPORT" in content
    assert (REPO_ROOT / "legacy_flask_app.py").exists()


def test_deploy_and_production_config_not_modified_by_d5() -> None:
    result = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    changed = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    forbidden = [
        path
        for path in changed
        if path.startswith("deploy/")
        or (path.startswith(".github/") and path != ".github/workflows/ci.yml")
        or any(keyword in path.lower() for keyword in ["nginx", "systemd", "supervisor", "docker-compose", "production"])
        and not path.startswith(("docs/", "tests/", "tools/"))
    ]
    assert forbidden == []


def test_d7_to_d9_docs_are_not_marked_retired_or_deleted() -> None:
    content = _read("docs/legacy_delete_batches.md")
    for batch in ["D7", "D8", "D9"]:
        section = content.split(f"## {batch}:", 1)[1].split("## ", 1)[0]
        status_line = next((line.strip().lower() for line in section.splitlines() if line.strip().lower().startswith("status:")), "")
        assert not status_line.startswith("status: retired")
        assert not status_line.startswith("status: deleted")


def test_d5_retirement_checker_returns_ok(tmp_path: Path) -> None:
    output_md = tmp_path / "d5.md"
    output_json = tmp_path / "d5.json"
    subprocess.run(
        [
            "python3",
            "tools/check_legacy_d5_questionnaire_retirement.py",
            "--output-md",
            str(output_md),
            "--output-json",
            str(output_json),
        ],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(output_json.read_text(encoding="utf-8"))
    assert payload["ok"] is True
    assert payload["stale_readonly_routes"] == []
    assert payload["production_config_modified"] is False
