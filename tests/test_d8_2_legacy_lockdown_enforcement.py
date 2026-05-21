from __future__ import annotations

import importlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def _lockdown():
    module_path = PROJECT_ROOT / "wecom_ability_service/legacy_lockdown.py"
    spec = importlib.util.spec_from_file_location("d8_legacy_lockdown_test", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_legacy_lockdown_module_and_register_exist() -> None:
    module = _lockdown()
    assert (PROJECT_ROOT / "wecom_ability_service/legacy_lockdown.py").exists()
    assert callable(module.register_legacy_lockdown)
    assert hasattr(module, "RetiredRouteRule")
    assert hasattr(module, "AllowedFallbackRule")


def test_retired_route_rules_include_d1_d6_groups() -> None:
    retired, _ = _lockdown().load_lockdown_rules()
    groups = {rule.category for rule in retired}
    assert {
        "media_readonly",
        "product_readonly",
        "customer_readonly",
        "user_ops_readonly",
        "questionnaire_readonly",
        "automation_readonly",
    } <= groups


def test_allowed_fallback_rules_include_write_external_examples() -> None:
    _, allowed = _lockdown().load_lockdown_rules()
    patterns = {rule.pattern for rule in allowed}
    assert "/p/{product_code}" in patterns
    assert "/api/products/{product_code}" in patterns
    assert "/api/h5/questionnaires/{slug}/submit" in patterns
    assert "/api/h5/wechat/oauth/start" in patterns
    assert "/api/archive/sync" in patterns
    assert "/api/admin/automation-conversion/member/push-openclaw" in patterns


def test_match_retired_route_matches_readonly_and_not_allowed_fallback() -> None:
    module = _lockdown()
    matched, rule = module.match_retired_route("GET", "/api/customers")
    assert matched is True
    assert rule is not None
    assert rule.reason == "retired_readonly_route"
    assert module.match_retired_route("POST", "/api/h5/questionnaires/demo/submit")[0] is False
    assert module.match_retired_route("GET", "/p/course-a")[0] is False


def test_allowed_fallback_matcher_keeps_fallback_available() -> None:
    module = _lockdown()
    assert module.match_allowed_fallback_route("POST", "/api/h5/questionnaires/demo/submit")[0] is True
    assert module.match_allowed_fallback_route("GET", "/p/course-a")[0] is True
    assert module.match_allowed_fallback_route("GET", "/api/system/health")[0] is True
    assert module.match_allowed_fallback_route("GET", "/api/customers")[0] is False


def test_legacy_flask_client_returns_retired_response_shape() -> None:
    script = """
import json
from wecom_ability_service import create_app
app = create_app({"TESTING": True, "DATABASE_URL": ""})
client = app.test_client()
resp = client.get("/api/customers")
print(json.dumps({
    "status_code": resp.status_code,
    "payload": resp.get_json(silent=True),
    "route_owner": resp.headers.get("X-AICRM-Route-Owner"),
    "next_owner": resp.headers.get("X-AICRM-Next-Owner"),
}, ensure_ascii=False))
"""
    completed = subprocess.run(
        ["python3", "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["status_code"] == 410
    assert result["payload"]["error"] == "legacy_route_retired"
    assert result["payload"]["route_owner"] == "ai_crm_next"
    assert result["payload"]["legacy_fallback"] is True
    assert result["payload"]["status"] == "retired"
    assert result["route_owner"] == "legacy_flask_retired"
    assert result["next_owner"] == "aicrm_next.customer_read_model"


def test_allowed_fallback_route_is_not_blocked_by_lockdown() -> None:
    script = """
import json
from wecom_ability_service import create_app
app = create_app({"TESTING": True, "DATABASE_URL": ""})
client = app.test_client()
resp = client.get("/api/system/health")
payload = resp.get_json(silent=True) or {}
print(json.dumps({
    "status_code": resp.status_code,
    "error": payload.get("error"),
    "route_owner": resp.headers.get("X-AICRM-Route-Owner"),
}, ensure_ascii=False))
"""
    completed = subprocess.run(
        ["python3", "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert result["status_code"] != 410
    assert result["error"] != "legacy_route_retired"


def test_legacy_app_factory_registers_lockdown_and_next_default_remains() -> None:
    legacy_source = _read("legacy_flask/app_factory.py")
    shim_source = _read("wecom_ability_service/__init__.py")
    assert "from legacy_flask.legacy_lockdown import register_legacy_lockdown" in legacy_source
    assert "register_legacy_lockdown(app)" in legacy_source
    assert "LEGACY_COMPATIBILITY_SHIM" in shim_source
    app_source = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in app_source
    assert 'command = args.command or "run"' in app_source
    assert "run_next()" in app_source


def test_legacy_shell_and_openclaw_still_exist() -> None:
    assert (PROJECT_ROOT / "legacy_flask_app.py").exists()
    assert (PROJECT_ROOT / "wecom_ability_service").exists()
    assert (PROJECT_ROOT / "wecom_ability_service/http/__init__.py").exists()
    assert (PROJECT_ROOT / "openclaw_service").exists()


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d8_2_legacy_fallback_route_lockdown_enforcement.md",
        "docs/d8_2_legacy_fallback_route_lockdown_report.md",
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
        "docs/d8_1_legacy_fallback_route_matrix.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_retirement_plan.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_production_config_not_modified(monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d8_2_legacy_lockdown_enforcement")
    monkeypatch.setattr(checker, "_changed_paths", lambda: ["wecom_ability_service/legacy_lockdown.py"])
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
    assert blockers == []


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d8_2_legacy_lockdown_enforcement")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["lockdown_registered"] is True
    assert result["legacy_fallback_exists"] is True
    assert result["allowed_fallback_routes_blocked"] == []
    assert result["production_config_modified"] is False
    assert result["recommendation"] == "READY_FOR_D8_2_LOCKDOWN_ENFORCEMENT_ACCEPTANCE"
