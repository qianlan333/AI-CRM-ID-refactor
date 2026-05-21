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


def test_d9_1_required_files_exist() -> None:
    assert (PROJECT_ROOT / "docs/d9_1_openclaw_legacy_import_freeze_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d9_1_openclaw_import_allowlist.md").exists()
    assert (PROJECT_ROOT / "tools/check_d9_1_openclaw_import_freeze.py").exists()


def test_openclaw_service_still_exists() -> None:
    assert (PROJECT_ROOT / "openclaw_service").is_dir()
    assert (PROJECT_ROOT / "openclaw_service/LEGACY_FROZEN.md").exists()


def test_aicrm_next_has_no_openclaw_service_import() -> None:
    checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
    blockers: list[dict] = []
    rows = checker._parse_markdown_table("docs/d9_1_openclaw_import_allowlist.md")
    result = checker._check_import_freeze(blockers, rows)
    assert result["aicrm_next_imports_openclaw_service"] == []
    assert result["forbidden_runtime_imports"] == []
    assert blockers == []


def test_allowlist_does_not_allow_aicrm_next_runtime_import() -> None:
    checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
    rows = checker._parse_markdown_table("docs/d9_1_openclaw_import_allowlist.md")
    for row in rows:
        path = row.get("path", "")
        if "aicrm_next" in path:
            assert row["allowed"] == "false"


def test_docs_tests_and_checkers_static_references_are_allowlisted() -> None:
    checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
    rows = checker._parse_markdown_table("docs/d9_1_openclaw_import_allowlist.md")
    allowed_paths = {row["path"] for row in rows if row["allowed"] == "true"}
    assert "`docs/**`" in allowed_paths
    assert "`tests/test_d9_1_openclaw_import_freeze.py`" in allowed_paths
    assert "`tools/check_d9_1_openclaw_import_freeze.py`" in allowed_paths


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["openclaw_service_exists"] is True
    assert result["legacy_frozen_exists"] is True
    assert result["forbidden_runtime_imports"] == []
    assert result["aicrm_next_imports_openclaw_service"] == []
    assert result["production_config_modified"] is False


def test_checker_fails_if_synthetic_aicrm_next_runtime_import_is_present(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
    fake_root = tmp_path
    runtime_dir = fake_root / "aicrm_next"
    runtime_dir.mkdir(parents=True)
    (runtime_dir / "bad_import.py").write_text("import openclaw_service\n", encoding="utf-8")
    monkeypatch.setattr(checker, "PROJECT_ROOT", fake_root)
    monkeypatch.setattr(checker, "PYTHON_SCAN_ROOTS", ["aicrm_next"])
    blockers: list[dict] = []
    result = checker._check_import_freeze(blockers, [])
    assert result["aicrm_next_imports_openclaw_service"]
    assert any(item["reason"] == "aicrm_next_imports_openclaw_service" for item in blockers)


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d9_1_openclaw_legacy_import_freeze_plan.md",
        "docs/d9_1_openclaw_import_allowlist.md",
        "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
        "docs/d9_openclaw_legacy_dependency_inventory.md",
        "docs/d9_openclaw_mcp_compatibility_matrix.md",
        "docs/legacy_retirement_plan.md",
        "docs/legacy_delete_batches.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_production_config_not_modified() -> None:
    checker = importlib.import_module("tools.check_d9_1_openclaw_import_freeze")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
