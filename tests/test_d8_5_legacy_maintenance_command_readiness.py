from __future__ import annotations

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def test_d8_5_required_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs/d8_5_legacy_db_maintenance_command_inventory.md").exists()
    assert (PROJECT_ROOT / "docs/d8_5_legacy_db_maintenance_command_retirement_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d8_5_maintenance_command_replacement_matrix.md").exists()


def test_inventory_covers_legacy_db_and_cleanup_commands() -> None:
    text = _read("docs/d8_5_legacy_db_maintenance_command_inventory.md")
    for expected in [
        "python3 app.py init-db-legacy",
        "python3 legacy_flask_app.py init-db",
        "delete-questionnaire-submissions",
        "wecom_ability_service.db.init_db()",
        "wecom_ability_service/schema_postgres.sql",
        "migrations/env.py",
    ]:
        assert expected in text


def test_replacement_matrix_has_no_forbidden_status_and_guards_destructive_commands() -> None:
    checker = importlib.import_module("tools.check_d8_5_legacy_maintenance_command_readiness")
    rows = checker._parse_markdown_table("docs/d8_5_maintenance_command_replacement_matrix.md")
    assert rows
    allowed = {"available", "planned", "needs_manual_review", "blocked"}
    for row in rows:
        assert row["replacement_status"] in allowed
        assert "delete_ready" not in row["replacement_status"]
        assert row["can_run_in_production"] == "false"
        haystack = " ".join(row.values()).lower()
        if any(word in haystack for word in ["delete", "cleanup", "destructive", "backfill", "seed"]):
            assert row["requires_human_signoff"] == "true"


def test_production_auto_run_defaults_false() -> None:
    checker = importlib.import_module("tools.check_d8_5_legacy_maintenance_command_readiness")
    result = checker.run_check()
    assert result["production_auto_run_disabled"] is True
    assert result["destructive_commands_guarded"] is True


def test_app_default_next_and_legacy_commands_retained() -> None:
    app_source = _read("app.py")
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in app_source
    assert 'command = args.command or "run"' in app_source
    assert "run_next()" in app_source
    assert "init-db-legacy" in app_source
    assert "delete-questionnaire-submissions-legacy" in app_source
    legacy_source = _read("legacy_flask_app.py")
    assert 'subparsers.add_parser("init-db"' in legacy_source
    assert "delete-questionnaire-submissions" in legacy_source


def test_legacy_fallback_and_shims_still_exist() -> None:
    assert (PROJECT_ROOT / "legacy_flask_app.py").exists()
    assert (PROJECT_ROOT / "legacy_flask").is_dir()
    assert (PROJECT_ROOT / "wecom_ability_service").is_dir()
    assert (PROJECT_ROOT / "wecom_ability_service/__init__.py").exists()
    assert (PROJECT_ROOT / "openclaw_service").is_dir()


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d8_5_legacy_db_maintenance_command_inventory.md",
        "docs/d8_5_legacy_db_maintenance_command_retirement_plan.md",
        "docs/d8_5_maintenance_command_replacement_matrix.md",
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/legacy_retirement_plan.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_route_owner_cutover_matrix.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
        "docs/production_replacement_route.md",
    ]:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d8_5_legacy_maintenance_command_readiness")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["inventory_exists"] is True
    assert result["retirement_plan_exists"] is True
    assert result["replacement_matrix_exists"] is True
    assert result["legacy_commands_retained"] is True
    assert result["destructive_commands_guarded"] is True
    assert result["production_auto_run_disabled"] is True
    assert result["default_runtime"] == "ai_crm_next"
    assert result["legacy_fallback_exists"] is True
    assert result["production_config_modified"] is False


def test_checker_fails_if_destructive_command_lacks_human_signoff(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d8_5_legacy_maintenance_command_readiness")
    original = PROJECT_ROOT / "docs/d8_5_maintenance_command_replacement_matrix.md"
    fake_root = tmp_path
    fake_docs = fake_root / "docs"
    fake_docs.mkdir()
    fake_matrix = fake_docs / "d8_5_maintenance_command_replacement_matrix.md"
    fake_matrix.write_text(
        original.read_text(encoding="utf-8").replace(
            "| `python3 app.py delete-questionnaire-submissions-legacy <slug>` | `app.py` | reviewed Next operator cleanup command | needs_manual_review | false | false | false | true | true |",
            "| `python3 app.py delete-questionnaire-submissions-legacy <slug>` | `app.py` | reviewed Next operator cleanup command | needs_manual_review | false | false | false | true | false |",
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "PROJECT_ROOT", fake_root)
    blockers: list[dict] = []
    result = checker._check_replacement_matrix(blockers)
    assert result["destructive_without_signoff"]
    assert any(item["reason"] == "destructive_command_without_human_signoff" for item in blockers)


def test_production_config_not_modified() -> None:
    checker = importlib.import_module("tools.check_d8_5_legacy_maintenance_command_readiness")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
