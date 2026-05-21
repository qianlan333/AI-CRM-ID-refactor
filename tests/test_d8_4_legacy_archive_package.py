from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def _run_python(script: str) -> dict:
    completed = subprocess.run(
        ["python3", "-c", script],
        cwd=PROJECT_ROOT,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_legacy_flask_package_exists() -> None:
    assert (PROJECT_ROOT / "legacy_flask/__init__.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/app_factory.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/routes.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/http/__init__.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/legacy_lockdown.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/README.md").exists()


def test_compatibility_shims_still_exist_and_are_marked() -> None:
    for relpath in [
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/routes.py",
        "wecom_ability_service/http/__init__.py",
        "wecom_ability_service/legacy_lockdown.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists()
        assert "LEGACY_COMPATIBILITY_SHIM" in _read(relpath)


def test_legacy_flask_app_imports_archive_package_and_app_default_remains_next() -> None:
    legacy_source = _read("legacy_flask_app.py")
    assert "legacy_flask.app_factory import create_app" in legacy_source
    assert "wecom_ability_service remains a compatibility shim" in legacy_source
    app_source = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in app_source
    assert 'command = args.command or "run"' in app_source
    assert "run_next()" in app_source
    assert "from legacy_flask.app_factory import create_app" in app_source


def test_app_py_has_no_top_level_legacy_imports() -> None:
    checker = importlib.import_module("tools.check_d8_4_legacy_archive_package")
    result = checker._check_default_runtime([])
    assert result["default_runtime"] == "ai_crm_next"
    assert result["top_level_legacy_imports"] == []


def test_archive_and_shim_create_app_imports_work() -> None:
    result = _run_python(
        """
import json
from legacy_flask.app_factory import create_app
from wecom_ability_service import create_app as shim_create_app
print(json.dumps({
    "legacy_flask_create_app": callable(create_app),
    "wecom_ability_service_shim_create_app": callable(shim_create_app),
}, ensure_ascii=False))
"""
    )
    assert result["legacy_flask_create_app"] is True
    assert result["wecom_ability_service_shim_create_app"] is True


def test_lockdown_still_blocks_retired_and_allows_diagnostic() -> None:
    result = _run_python(
        """
import json
from legacy_flask.app_factory import create_app
app = create_app({"TESTING": True, "DATABASE_URL": ""})
client = app.test_client()
retired = client.get("/api/customers")
allowed = client.get("/api/system/health")
print(json.dumps({
    "retired": {
        "status_code": retired.status_code,
        "error": (retired.get_json(silent=True) or {}).get("error"),
        "route_owner": retired.headers.get("X-AICRM-Route-Owner"),
    },
    "allowed": {
        "status_code": allowed.status_code,
        "error": (allowed.get_json(silent=True) or {}).get("error"),
    },
}, ensure_ascii=False))
"""
    )
    assert result["retired"]["status_code"] == 410
    assert result["retired"]["error"] == "legacy_route_retired"
    assert result["retired"]["route_owner"] == "legacy_flask_retired"
    assert result["allowed"]["error"] != "legacy_route_retired"


def test_openclaw_retained_and_docs_do_not_mark_forbidden_statuses() -> None:
    assert (PROJECT_ROOT / "openclaw_service").exists()
    for relpath in [
        "docs/d8_4_legacy_flask_archive_package_implementation.md",
        "docs/d8_4_legacy_flask_archive_package_report.md",
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/legacy_retirement_plan.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_route_owner_cutover_matrix.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d8_4_legacy_archive_package")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["legacy_flask_package_exists"] is True
    assert result["default_runtime"]["default_runtime"] == "ai_crm_next"
    assert result["lockdown_status"]["status_code"] == 410
    assert result["allowed_fallback_status"]["error"] != "legacy_route_retired"
    assert result["openclaw_service_status"]["exists"] is True
    assert result["production_config_modified"] is False
    assert result["recommendation"] == "READY_FOR_D8_4_ARCHIVE_PACKAGE_ACCEPTANCE"
