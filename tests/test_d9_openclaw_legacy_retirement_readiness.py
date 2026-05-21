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


def test_d9_required_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs/d9_openclaw_legacy_adapter_retirement_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d9_openclaw_legacy_dependency_inventory.md").exists()
    assert (PROJECT_ROOT / "docs/d9_openclaw_mcp_compatibility_matrix.md").exists()


def test_openclaw_service_and_frozen_marker_exist() -> None:
    assert (PROJECT_ROOT / "openclaw_service").is_dir()
    assert (PROJECT_ROOT / "openclaw_service/LEGACY_FROZEN.md").exists()


def test_default_next_does_not_import_openclaw_service() -> None:
    checker = importlib.import_module("tools.check_d9_openclaw_legacy_retirement_readiness")
    blockers: list[dict] = []
    result = checker._check_default_next_imports_openclaw_service(blockers)
    assert result["default_next_imports_openclaw_service"] is False
    assert blockers == []


def test_d7_7_adapter_artifacts_exist() -> None:
    for relpath in [
        "docs/d7_7_mcp_openclaw_legacy_adapter_contract.md",
        "docs/d7_7_mcp_openclaw_legacy_retirement_report.md",
        "tools/check_d7_7_mcp_openclaw_adapter_contract.py",
        "tests/test_d7_7_mcp_openclaw_adapter_contract.py",
    ]:
        assert (PROJECT_ROOT / relpath).exists()


def test_compatibility_matrix_covers_required_capabilities_and_statuses() -> None:
    checker = importlib.import_module("tools.check_d9_openclaw_legacy_retirement_readiness")
    rows = checker._parse_markdown_table("docs/d9_openclaw_mcp_compatibility_matrix.md")
    assert rows
    covered = {row["capability"] for row in rows}
    for capability in checker.REQUIRED_CAPABILITIES:
        assert capability in covered
    for row in rows:
        assert row["compatibility_status"] in checker.ALLOWED_COMPATIBILITY_STATUSES
        for marker in ["production_ready", "delete_ready", "production_approved"]:
            assert marker not in " ".join(row.values())


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
        "docs/d9_openclaw_legacy_dependency_inventory.md",
        "docs/d9_openclaw_mcp_compatibility_matrix.md",
        "docs/legacy_retirement_plan.md",
        "docs/legacy_delete_batches.md",
        "docs/legacy_route_owner_cutover_matrix.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
        "docs/d7_capability_readiness_matrix.md",
    ]:
        text = _read(relpath)
        for marker in ["production_ready", "delete_ready", "production_approved"]:
            assert marker not in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_openclaw_legacy_retirement_readiness")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["plan_exists"] is True
    assert result["dependency_inventory_exists"] is True
    assert result["compatibility_matrix_exists"] is True
    assert result["openclaw_service_exists"] is True
    assert result["legacy_frozen_exists"] is True
    assert result["default_next_imports_openclaw_service"] is False
    assert result["production_config_modified"] is False


def test_checker_fails_if_openclaw_service_missing(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d9_openclaw_legacy_retirement_readiness")
    fake_root = tmp_path
    monkeypatch.setattr(checker, "PROJECT_ROOT", fake_root)
    blockers: list[dict] = []
    result = checker._check_openclaw_retained(blockers)
    assert result["openclaw_service_exists"] is False
    assert any(item["reason"] == "openclaw_service_missing" for item in blockers)


def test_no_physical_move_or_delete_has_occurred() -> None:
    checker = importlib.import_module("tools.check_d9_openclaw_legacy_retirement_readiness")
    blockers: list[dict] = []
    result = checker._check_openclaw_retained(blockers)
    assert result["openclaw_service_exists"] is True
    assert result["legacy_frozen_exists"] is True
    assert result["openclaw_service_moved"] is False


def test_production_config_not_modified() -> None:
    checker = importlib.import_module("tools.check_d9_openclaw_legacy_retirement_readiness")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
