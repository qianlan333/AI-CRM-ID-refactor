from __future__ import annotations

import ast
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def test_d8_required_files_exist() -> None:
    for relpath in [
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/d8_legacy_shell_dependency_inventory.md",
        "docs/d8_legacy_shell_allowed_fallback_matrix.md",
        "tools/check_d8_legacy_shell_retirement_readiness.py",
        "tests/test_d8_legacy_shell_retirement_readiness.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists(), relpath


def test_app_py_default_remains_next() -> None:
    content = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in content
    assert 'command = args.command or "run"' in content
    assert 'if command == "run":' in content
    assert "run_next()" in content


def test_legacy_shell_core_still_exists() -> None:
    for relpath in [
        "legacy_flask_app.py",
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/routes.py",
        "wecom_ability_service/http/__init__.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists(), relpath
    assert (PROJECT_ROOT / "openclaw_service").exists()


def test_default_next_entrypoint_has_no_top_level_legacy_imports() -> None:
    tree = ast.parse(_read("app.py"))
    imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            imports.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert "wecom_ability_service" not in imports
    assert "openclaw_service" not in imports


def test_next_runtime_source_does_not_import_legacy_backends() -> None:
    for path in (PROJECT_ROOT / "aicrm_next").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in text, path
        assert "openclaw_service" not in text, path


def test_d8_docs_do_not_mark_forbidden_statuses() -> None:
    forbidden = ["production_ready", "delete_ready", "production_approved"]
    for relpath in [
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/d8_legacy_shell_dependency_inventory.md",
        "docs/d8_legacy_shell_allowed_fallback_matrix.md",
    ]:
        text = _read(relpath)
        for marker in forbidden:
            assert marker not in text


def test_d7_matrix_still_has_no_forbidden_statuses() -> None:
    text = _read("docs/d7_capability_readiness_matrix.md")
    for marker in ["production_ready", "delete_ready", "production_approved"]:
        assert marker not in text


def test_d8_plan_has_required_sections() -> None:
    text = _read("docs/d8_legacy_flask_shell_retirement_plan.md")
    for section in [
        "Current State",
        "Why Not Delete The Shell Immediately",
        "D8 Retirement Phases",
        "Delete Gate",
        "Rollback",
        "D8.0 only",
    ]:
        assert section in text


def test_dependency_inventory_has_required_columns_and_core_rows() -> None:
    text = _read("docs/d8_legacy_shell_dependency_inventory.md")
    for column in [
        "file_or_directory",
        "role",
        "runtime_imported_by_default_next",
        "runtime_imported_by_legacy_fallback",
        "still_needed_for",
        "replacement_in_next",
        "delete_blocker",
        "future_retirement_phase",
        "notes",
    ]:
        assert column in text
    for relpath in [
        "app.py",
        "legacy_flask_app.py",
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/routes.py",
        "wecom_ability_service/http/__init__.py",
        "wecom_ability_service/http/*",
        "wecom_ability_service/domains/*",
        "wecom_ability_service/templates/*",
        "wecom_ability_service/static/*",
        "openclaw_service/*",
    ]:
        assert relpath in text


def test_allowed_fallback_matrix_has_required_rows() -> None:
    text = _read("docs/d8_legacy_shell_allowed_fallback_matrix.md")
    for row in [
        "legacy run command",
        "legacy init-db command",
        "emergency rollback app factory",
        "old external write fallback",
        "old payment fallback",
        "old OAuth fallback",
        "old OpenClaw fallback",
        "archive sync fallback",
        "operational diagnostics",
    ]:
        assert row in text
    assert "Allowed fallback is not production ownership" in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d8_legacy_shell_retirement_readiness")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["default_runtime"] == "ai_crm_next"
    assert result["legacy_fallback_exists"] is True
    assert result["shell_core_exists"] is True
    assert result["forbidden_imports"] == []
    assert result["production_config_modified"] is False
    assert result["recommendation"] == "READY_FOR_D8_PLANNING_ACCEPTANCE_NOT_DELETE"


def test_checker_fails_if_legacy_shell_core_is_missing(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d8_legacy_shell_retirement_readiness")
    monkeypatch.setattr(checker, "PROJECT_ROOT", tmp_path)
    blockers: list[dict] = []
    result = checker._check_legacy_shell_core(blockers)
    assert result["shell_core_exists"] is False
    assert any(item["reason"] == "missing_legacy_shell_core" for item in blockers)


def test_deploy_and_production_config_not_modified(monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d8_legacy_shell_retirement_readiness")
    monkeypatch.setattr(checker, "_changed_paths", lambda: ["docs/d8_legacy_flask_shell_retirement_plan.md"])
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
    assert blockers == []
