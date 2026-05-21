from __future__ import annotations

import pytest
import importlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    (PROJECT_ROOT / "docs/d9_6_openclaw_physical_deletion_report.md").exists()
    and not (PROJECT_ROOT / "openclaw_service").exists(),
    reason="Superseded by D9.6 physical deletion state",
)



def _read(relpath: str) -> str:
    return (PROJECT_ROOT / relpath).read_text(encoding="utf-8")


def test_d9_5_required_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs/d9_5_openclaw_service_shim_removal_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d9_5_openclaw_final_reference_scan_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d9_5_openclaw_shim_removal_readiness_checklist.md").exists()


def test_openclaw_shim_and_archive_are_retained() -> None:
    assert (PROJECT_ROOT / "openclaw_service").is_dir()
    assert (PROJECT_ROOT / "openclaw_service/__init__.py").exists()
    assert (PROJECT_ROOT / "openclaw_service/LEGACY_FROZEN.md").exists()
    assert (PROJECT_ROOT / "openclaw_service/README.md").exists()
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy").is_dir()


def test_aicrm_next_has_no_openclaw_service_import() -> None:
    checker = importlib.import_module("tools.check_d9_5_openclaw_shim_removal_readiness")
    blockers: list[dict] = []
    result = checker._check_aicrm_next_imports(blockers)
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert blockers == []


def test_readiness_checklist_uses_allowed_status_values_only() -> None:
    text = _read("docs/d9_5_openclaw_shim_removal_readiness_checklist.md")
    for marker in ["delete_ready", "production_ready", "production_approved"]:
        assert marker not in text
    allowed = {"pending", "available", "needs_manual_review", "blocked"}
    lines = [line for line in text.splitlines() if line.startswith("|") and "`" not in line]
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if len(cells) >= 3:
            assert cells[2] in allowed


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_5_openclaw_shim_removal_readiness")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["plan_exists"] is True
    assert result["reference_scan_plan_exists"] is True
    assert result["readiness_checklist_exists"] is True
    assert result["openclaw_service_still_exists"] is True
    assert result["shim_still_exists"] is True
    assert result["legacy_flask_openclaw_legacy_exists"] is True
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert result["production_config_modified"] is False


def test_checker_fails_if_shim_is_missing(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d9_5_openclaw_shim_removal_readiness")
    monkeypatch.setattr(checker, "PROJECT_ROOT", tmp_path)
    (tmp_path / "openclaw_service").mkdir()
    (tmp_path / "openclaw_service/LEGACY_FROZEN.md").write_text("frozen", encoding="utf-8")
    (tmp_path / "legacy_flask/openclaw_legacy").mkdir(parents=True)
    blockers: list[dict] = []
    result = checker._check_retained_paths(blockers)
    assert result["shim_still_exists"] is False
    assert any(item["reason"] == "openclaw_service_shim_missing" for item in blockers)


def test_production_config_not_modified() -> None:
    checker = importlib.import_module("tools.check_d9_5_openclaw_shim_removal_readiness")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
