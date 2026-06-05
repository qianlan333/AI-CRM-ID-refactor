from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import Response
from fastapi.testclient import TestClient
from flask import Flask, jsonify, request as flask_request

from aicrm_next.integration_gateway import legacy_flask_facade
from aicrm_next.main import create_app
from tools import check_next_production_cutover_readiness as cutover_checker
from tools import check_next_production_runtime_gaps as gap_checker

ROOT = Path(__file__).resolve().parents[1]


def test_health_degrades_when_production_uses_fixture(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    monkeypatch.delenv("AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE", raising=False)
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["runtime_owner"] == "ai_crm_next"
    assert payload["database_mode"] == "fixture"
    assert payload["fixture_mode"] is True
    assert payload["production_data_ready"] is False
    assert payload["ok"] is False
    assert payload["status"] == "degraded"


def test_health_reports_postgres_when_database_url_is_real(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    client = TestClient(create_app())

    payload = client.get("/health").json()

    assert payload["database_mode"] == "postgres"
    assert payload["fixture_mode"] is False
    assert payload["production_data_ready"] is True
    assert payload["runtime_owner"] == "ai_crm_next"


def test_next_production_facade_catches_legacy_routes_without_404(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql://probe:probe@127.0.0.1:1/aicrm_probe")
    monkeypatch.setenv("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE", "1")
    monkeypatch.setenv("AUTOMATION_INTERNAL_API_TOKEN", "probe-token")
    client = TestClient(create_app())

    for path in [
        "/admin/customers",
        "/api/customers",
        "/api/admin/questionnaires",
        "/api/h5/wechat-pay/jsapi/orders",
        "/wecom/external-contact/callback",
    ]:
        response = client.get(path) if path.startswith("/admin") or path == "/api/customers" or "questionnaires" in path else client.post(path, json={})
        assert response.status_code != 404
        assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_runtime_gap_checker_returns_ok():
    result = gap_checker.run_check()

    assert result["ok"] is True
    assert result["database_mode"] == "postgres"
    assert result["route_404_blockers"] == []
    assert result["content_blockers"] == []
    assert result["oauth_blockers"] == []
    assert result["callback_currently_has_5013_fallback"] is True


def test_runtime_gap_checker_flags_fixture_questionnaire_payload():
    routes = {
        "GET /api/admin/questionnaires": {
            "status_code": 200,
            "json": {"questionnaires": [{"slug": "hxc-activation-v1"}, {"slug": "disabled-demo"}]},
        }
    }

    blockers, warnings = gap_checker._questionnaire_content_blockers(routes, local_probe_database=False)

    assert warnings == []
    assert "questionnaire_fixture_demo_only" in blockers


def test_runtime_gap_checker_flags_fixture_automation_payload():
    routes = {
        "GET /api/admin/automation-conversion/overview": {
            "status_code": 200,
            "json": {"generated_at": "fixture", "status": "partial"},
        }
    }

    blockers, warnings = gap_checker._automation_content_blockers(routes, local_probe_database=False)

    assert warnings == []
    assert "automation_generated_at_fixture" in blockers
    assert "automation_status_partial" in blockers


def test_runtime_gap_checker_flags_oauth_500_and_localhost_redirect():
    routes = {
        "GET /api/h5/wechat/oauth/start?next=/admin": {
            "status_code": 500,
            "json": {},
            "location": "",
        },
        "GET /api/h5/wechat-pay/oauth/start?next=/admin": {
            "status_code": 302,
            "json": {},
            "location": "https://open.weixin.qq.com/connect/oauth2/authorize?redirect_uri=http%3A%2F%2Flocalhost%2Fapi%2Fh5%2Fwechat-pay%2Foauth%2Fcallback",
        },
    }

    blockers = gap_checker._oauth_blockers(routes)

    assert any(item.startswith("oauth_start_500:/api/h5/wechat/oauth/start") for item in blockers)
    assert "oauth_redirect_uri_localhost:/api/h5/wechat-pay/oauth/start" in blockers


def test_legacy_flask_facade_normalizes_int_status_response():
    response = legacy_flask_facade.normalize_legacy_response(204)

    assert response.status_code == 204
    assert response.headers["X-AICRM-Route-Owner"] == "ai_crm_next"


def test_legacy_flask_facade_uses_public_base_url_in_production(monkeypatch):
    monkeypatch.setenv("AICRM_NEXT_ENV", "production")
    for key in ["AICRM_PUBLIC_BASE_URL", "PUBLIC_BASE_URL", "EXTERNAL_BASE_URL", "APP_EXTERNAL_BASE_URL"]:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("WECHAT_PAY_NOTIFY_URL", "http://localhost/api/h5/wechat-pay/notify")

    assert legacy_flask_facade._public_base_url() == "https://www.youcangogogo.com"


def test_legacy_flask_facade_forwards_request_cookies(monkeypatch):
    monkeypatch.setenv("AICRM_PUBLIC_BASE_URL", "http://testserver")
    legacy_app = Flask(__name__)

    @legacy_app.get("/legacy-cookie-probe")
    def legacy_cookie_probe():
        return jsonify({"session": flask_request.cookies.get("session", "")})

    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", lambda: legacy_app)
    app = FastAPI()

    @app.get("/legacy-cookie-probe")
    async def probe(request: Request) -> Response:
        return await legacy_flask_facade.forward_to_legacy_flask(request)

    client = TestClient(app)
    client.cookies.set("session", "signed-session")
    response = client.get("/legacy-cookie-probe")

    assert response.status_code == 200
    assert response.json()["session"] == "signed-session"


def test_legacy_flask_facade_does_not_rewrite_questionnaire_enable(monkeypatch):
    monkeypatch.setenv("AICRM_PUBLIC_BASE_URL", "http://testserver")
    legacy_app = Flask(__name__)
    received = {}

    @legacy_app.post("/api/admin/questionnaires/<int:questionnaire_id>/disable")
    def legacy_disable(questionnaire_id: int):
        received["questionnaire_id"] = questionnaire_id
        received["payload"] = flask_request.get_json(silent=True) or {}
        return jsonify({"ok": True, "questionnaire": {"id": questionnaire_id, "is_disabled": received["payload"].get("is_disabled")}})

    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", lambda: legacy_app)
    app = FastAPI()

    @app.post("/api/admin/questionnaires/{questionnaire_id}/enable")
    async def enable(request: Request) -> Response:
        return await legacy_flask_facade.forward_to_legacy_flask(request)

    response = TestClient(app).post("/api/admin/questionnaires/42/enable", json={})

    assert response.status_code == 404
    assert received == {}


def test_legacy_flask_facade_does_not_rewrite_questionnaire_patch_update(monkeypatch):
    monkeypatch.setenv("AICRM_PUBLIC_BASE_URL", "http://testserver")
    legacy_app = Flask(__name__)
    received = {}

    @legacy_app.put("/api/admin/questionnaires/<int:questionnaire_id>")
    def legacy_update(questionnaire_id: int):
        received["method"] = flask_request.method
        received["questionnaire_id"] = questionnaire_id
        received["payload"] = flask_request.get_json(silent=True) or {}
        return jsonify({"ok": True, "questionnaire": {"id": questionnaire_id, **received["payload"]}})

    monkeypatch.setattr(legacy_flask_facade, "_legacy_app", lambda: legacy_app)
    app = FastAPI()

    @app.patch("/api/admin/questionnaires/{questionnaire_id}")
    async def update(request: Request) -> Response:
        return await legacy_flask_facade.forward_to_legacy_flask(request)

    response = TestClient(app).patch("/api/admin/questionnaires/42", json={"title": "生产更新"})

    assert response.status_code == 405
    assert received == {}


def test_cutover_checker_contract(monkeypatch):
    monkeypatch.setattr(
        cutover_checker,
        "run_gap_check",
        lambda: {
            "ok": True,
            "database_mode": "postgres",
            "route_404_blockers": [],
            "content_blockers": [],
            "oauth_blockers": [],
            "automation_production_data_ready": True,
            "production_config_modified": False,
        },
    )
    monkeypatch.setattr(
        cutover_checker,
        "run_timer_check",
        lambda: {"ok": True, "safe_to_enable_timers": True, "dry_run_db_sentinel": {"ok": True}},
    )
    result = cutover_checker.run_check()

    assert result["ok"] is True
    assert result["database_mode"] == "postgres"
    assert result["fixture_in_production"] is False
    assert result["route_404_blockers"] == []
    assert result["callback_ready"] is True
    assert result["timer_routes_ready"] is True
    assert result["payment_routes_ready"] is True
    assert result["oauth_routes_ready"] is True
    assert result["safe_to_enable_timers"] is True
    assert result["safe_to_remove_5013_callback_fallback"] is False


def test_cutover_checker_requires_dry_run_db_sentinel(monkeypatch):
    monkeypatch.setattr(
        cutover_checker,
        "run_gap_check",
        lambda: {
            "ok": True,
            "database_mode": "postgres",
            "route_404_blockers": [],
            "content_blockers": [],
            "oauth_blockers": [],
            "automation_production_data_ready": True,
            "production_config_modified": False,
        },
    )
    monkeypatch.setattr(
        cutover_checker,
        "run_timer_check",
        lambda: {"ok": True, "safe_to_enable_timers": True, "dry_run_db_sentinel": {"ok": False}},
    )

    result = cutover_checker.run_check()

    assert result["safe_to_enable_timers"] is False
    assert result["dry_run_db_sentinel_ok"] is False


def test_cutover_checker_avoids_forbidden_status_markers():
    content = "\n".join(
        [
            (ROOT / "tools/check_next_production_cutover_readiness.py").read_text(encoding="utf-8"),
            (ROOT / "tools/check_next_production_runtime_gaps.py").read_text(encoding="utf-8"),
        ]
    )
    for marker in ("delete_ready", "production_ready", "production_approved"):
        assert marker not in content


def test_production_config_not_modified():
    assert gap_checker.production_config_modified() is False
