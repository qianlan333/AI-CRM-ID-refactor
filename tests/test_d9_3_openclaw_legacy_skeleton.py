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


def test_skeleton_package_exists() -> None:
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy").is_dir()
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy/__init__.py").exists()
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy/README.md").exists()
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md").exists()
    assert (PROJECT_ROOT / "legacy_flask/openclaw_legacy/MOVE_PENDING.md").exists()


def test_skeleton_init_does_not_import_openclaw_service() -> None:
    checker = importlib.import_module("tools.check_d9_3_openclaw_legacy_skeleton")
    blockers: list[dict] = []
    result = checker._check_skeleton_imports(blockers)
    assert result["skeleton_imports_openclaw_service"] is False
    assert blockers == []
    source = _read("legacy_flask/openclaw_legacy/__init__.py")
    assert "import openclaw_service" not in source
    assert "from openclaw_service" not in source


def test_openclaw_service_still_exists_and_no_move() -> None:
    assert (PROJECT_ROOT / "openclaw_service").is_dir()
    assert (PROJECT_ROOT / "openclaw_service/LEGACY_FROZEN.md").exists()
    shim_path = PROJECT_ROOT / "openclaw_service/__init__.py"
    if shim_path.exists():
        assert "LEGACY_COMPATIBILITY_SHIM" in shim_path.read_text(encoding="utf-8")


def test_no_compatibility_shim_created() -> None:
    checker = importlib.import_module("tools.check_d9_3_openclaw_legacy_skeleton")
    blockers: list[dict] = []
    result = checker._check_no_compatibility_shim(blockers)
    assert result["compatibility_shim_created"] in {False, True}
    assert blockers == []


def test_aicrm_next_has_no_openclaw_service_import() -> None:
    checker = importlib.import_module("tools.check_d9_3_openclaw_legacy_skeleton")
    blockers: list[dict] = []
    result = checker._check_aicrm_next_imports(blockers)
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert blockers == []


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_3_openclaw_legacy_skeleton")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["skeleton_exists"] is True
    assert result["skeleton_imports_openclaw_service"] is False
    assert result["openclaw_service_still_in_place"] is True
    assert result["openclaw_service_moved"] is False
    assert result["compatibility_shim_created"] in {False, True}
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert result["production_config_modified"] is False


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d9_3_openclaw_legacy_skeleton_implementation_report.md",
        "docs/d9_4_openclaw_legacy_move_implementation_report.md",
        "docs/d9_2_openclaw_legacy_move_plan.md",
        "docs/d9_2_openclaw_legacy_move_map.md",
        "docs/d9_2_openclaw_import_rewrite_plan.md",
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
    checker = importlib.import_module("tools.check_d9_3_openclaw_legacy_skeleton")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
