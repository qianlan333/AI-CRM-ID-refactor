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


def test_d9_2_required_docs_exist() -> None:
    assert (PROJECT_ROOT / "docs/d9_2_openclaw_legacy_move_plan.md").exists()
    assert (PROJECT_ROOT / "docs/d9_2_openclaw_legacy_move_map.md").exists()
    assert (PROJECT_ROOT / "docs/d9_2_openclaw_import_rewrite_plan.md").exists()


def test_move_map_covers_openclaw_service_paths_and_default_next_false() -> None:
    checker = importlib.import_module("tools.check_d9_2_openclaw_legacy_move_readiness")
    rows = checker._parse_markdown_table("docs/d9_2_openclaw_legacy_move_map.md")
    assert rows
    covered = {row["current_path"].strip("`") for row in rows}
    assert "openclaw_service/" in covered
    assert "openclaw_service/LEGACY_FROZEN.md" in covered
    for row in rows:
        assert row["default_next_imported"] == "false"


def test_import_rewrite_plan_mentions_temporary_shim_and_d7_7_boundary() -> None:
    text = _read("docs/d9_2_openclaw_import_rewrite_plan.md")
    assert "Temporary Shim Strategy" in text
    assert "D7.7" in text
    assert "adapter boundary" in text


def test_openclaw_service_still_exists_and_not_moved() -> None:
    assert (PROJECT_ROOT / "openclaw_service").is_dir()
    assert (PROJECT_ROOT / "openclaw_service/LEGACY_FROZEN.md").exists()
    archive_path = PROJECT_ROOT / "legacy_flask/openclaw_legacy"
    if archive_path.exists():
        files = {str(path.relative_to(PROJECT_ROOT)) for path in archive_path.rglob("*") if path.is_file()}
        assert files == {
            "legacy_flask/openclaw_legacy/__init__.py",
            "legacy_flask/openclaw_legacy/README.md",
            "legacy_flask/openclaw_legacy/LEGACY_FROZEN.md",
            "legacy_flask/openclaw_legacy/MOVE_PENDING.md",
        }


def test_aicrm_next_has_no_openclaw_service_import() -> None:
    checker = importlib.import_module("tools.check_d9_2_openclaw_legacy_move_readiness")
    blockers: list[dict] = []
    result = checker._check_aicrm_next_imports(blockers)
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert blockers == []


def test_docs_do_not_mark_forbidden_statuses() -> None:
    for relpath in [
        "docs/d9_2_openclaw_legacy_move_plan.md",
        "docs/d9_2_openclaw_legacy_move_map.md",
        "docs/d9_2_openclaw_import_rewrite_plan.md",
        "docs/d9_openclaw_legacy_adapter_retirement_plan.md",
        "docs/d9_openclaw_legacy_dependency_inventory.md",
        "docs/d9_openclaw_mcp_compatibility_matrix.md",
        "docs/d9_1_openclaw_legacy_import_freeze_plan.md",
        "docs/d9_1_openclaw_import_allowlist.md",
        "docs/legacy_retirement_plan.md",
        "docs/legacy_delete_batches.md",
        "docs/module_status_matrix.md",
        "docs/remaining_work_queue.md",
        "docs/go_no_go_checklist.md",
    ]:
        text = _read(relpath)
        for marker in ["delete_ready", "production_ready", "production_approved"]:
            assert marker not in text


def test_checker_runs_and_returns_ok() -> None:
    checker = importlib.import_module("tools.check_d9_2_openclaw_legacy_move_readiness")
    result = checker.run_check()
    assert result["ok"] is True
    assert result["blockers"] == []
    assert result["move_plan_exists"] is True
    assert result["move_map_exists"] is True
    assert result["import_rewrite_plan_exists"] is True
    assert result["openclaw_service_still_in_place"] is True
    assert result["legacy_flask_openclaw_legacy_status"]["status"] in {"absent", "skeleton_created", "moved_with_shim"}
    assert result["aicrm_next_imports_openclaw_service"] is False
    assert result["import_freeze_status"]["ok"] is True
    assert result["production_config_modified"] is False


def test_checker_fails_if_openclaw_service_missing(tmp_path, monkeypatch) -> None:
    checker = importlib.import_module("tools.check_d9_2_openclaw_legacy_move_readiness")
    monkeypatch.setattr(checker, "PROJECT_ROOT", tmp_path)
    blockers: list[dict] = []
    result = checker._check_openclaw_still_in_place(blockers)
    assert result["openclaw_service_still_in_place"] is False
    assert any(item["reason"] == "openclaw_service_missing" for item in blockers)


def test_production_config_not_modified() -> None:
    checker = importlib.import_module("tools.check_d9_2_openclaw_legacy_move_readiness")
    blockers: list[dict] = []
    result = checker._check_production_config_modified(blockers)
    assert result["production_config_modified"] is False
