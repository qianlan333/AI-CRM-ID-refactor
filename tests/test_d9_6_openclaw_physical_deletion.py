from __future__ import annotations

import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_d9_6_report_exists() -> None:
    assert (PROJECT_ROOT / "docs/d9_6_openclaw_physical_deletion_report.md").exists()


def test_openclaw_paths_are_deleted_from_repo() -> None:
    assert not (PROJECT_ROOT / "openclaw_service").exists()
    assert not (PROJECT_ROOT / "legacy_flask/openclaw_legacy").exists()


def test_next_runtime_has_no_deleted_openclaw_import() -> None:
    checker = importlib.import_module("tools.check_d9_6_openclaw_physical_deletion")
    assert checker._scan_next_imports() == []


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_6_openclaw_physical_deletion")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["report_exists"] is True
    assert result["openclaw_service_exists"] is False
    assert result["legacy_flask_openclaw_legacy_exists"] is False
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert result["local_production_config_modified"] is False
