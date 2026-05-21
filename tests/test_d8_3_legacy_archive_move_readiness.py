from __future__ import annotations

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def test_d8_3_planning_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs/d8_3_legacy_flask_shell_archive_package_plan.md").exists()
    assert not (PROJECT_ROOT / "docs/d8_3_legacy_shell_archive_package_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d8_3_legacy_package_move_map.md").exists()
    assert (PROJECT_ROOT / "docs/d8_3_legacy_import_rewrite_plan.md").exists()


def test_move_map_covers_core_paths() -> None:
    text = _read("docs/d8_3_legacy_package_move_map.md")
    assert "wecom_ability_service/__init__.py" in text
    assert "wecom_ability_service/http/__init__.py" in text
    assert "wecom_ability_service/legacy_lockdown.py" in text
    assert "openclaw_service/*" in text
    assert "default_next_imported" in text
    assert "shim_required" in text


def test_import_rewrite_plan_mentions_temporary_shim() -> None:
    text = _read("docs/d8_3_legacy_import_rewrite_plan.md")
    assert "temporary compatibility shim" in text
    assert "from wecom_ability_service" in text
    assert "from legacy_flask" in text
    assert "aicrm_next" in text
    assert "must not import" in text


def test_app_py_default_remains_next() -> None:
    source = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source
    assert 'command = args.command or "run"' in source
    assert "run_next()" in source


def test_legacy_shell_still_exists_and_d8_4_archive_package_is_allowed() -> None:
    assert (PROJECT_ROOT / "legacy_flask_app.py").exists()
    assert (PROJECT_ROOT / "wecom_ability_service").exists()
    assert (PROJECT_ROOT / "wecom_ability_service/__init__.py").exists()
    assert (PROJECT_ROOT / "wecom_ability_service/http/__init__.py").exists()
    assert (PROJECT_ROOT / "wecom_ability_service/legacy_lockdown.py").exists()
    assert (PROJECT_ROOT / "openclaw_service").exists()
    if (PROJECT_ROOT / "legacy_flask").exists():
        assert (PROJECT_ROOT / "docs/d8_4_legacy_flask_archive_package_implementation.md").exists()
        assert (PROJECT_ROOT / "tools/check_d8_4_legacy_archive_package.py").exists()


def test_docs_do_not_mark_forbidden_statuses() -> None:
    docs = [
        "docs/d8_3_legacy_flask_shell_archive_package_plan.md",
        "docs/d8_3_legacy_package_move_map.md",
        "docs/d8_3_legacy_import_rewrite_plan.md",
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/legacy_retirement_plan.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_route_owner_cutover_matrix.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]
    for relpath in docs:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d8_3_legacy_archive_move_readiness")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["plan_exists"] is True
    assert result["deprecated_wrong_plan_filename_present"] is False
    assert result["move_map_exists"] is True
    assert result["import_rewrite_plan_exists"] is True
    assert result["legacy_shell_still_in_place"] is True
    assert result["openclaw_service_still_in_place"] is True
    if result["legacy_flask_package_exists"]:
        assert result["d8_4_archive_package_present"] is True
    assert result["default_runtime"] == "ai_crm_next"
    assert result["lockdown_status"]["ok"] is True
    assert result["production_config_modified"] is False
    assert result["recommendation"] == "READY_FOR_D8_3_ARCHIVE_MOVE_PLANNING_ACCEPTANCE_NOT_MOVED"


def test_checker_checks_correct_plan_filename_and_fails_if_missing(monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d8_3_legacy_archive_move_readiness")
    assert checker.D8_3_DOCS[0] == "docs/d8_3_legacy_flask_shell_archive_package_plan.md"

    original_path = checker._path

    def fake_path(relpath: str):
        if relpath == "docs/d8_3_legacy_flask_shell_archive_package_plan.md":
            return PROJECT_ROOT / "__missing_d8_3_correct_plan_name__.md"
        return original_path(relpath)

    monkeypatch.setattr(checker, "_path", fake_path)
    blockers: list[dict] = []
    result = checker._check_required_docs(blockers)
    assert result["plan_exists"] is False
    assert {"reason": "missing_d8_3_doc", "path": "docs/d8_3_legacy_flask_shell_archive_package_plan.md"} in blockers
