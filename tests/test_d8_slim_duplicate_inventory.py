from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY = REPO_ROOT / "docs" / "d8_slim_duplicate_inventory.md"
FORBIDDEN_D8_MARKERS = ("delete_ready", "production_ready", "production_approved")
REQUESTED_D8_PATHS = [
    "docs/d8_legacy_flask_shell_retirement_plan.md",
    "docs/d8_legacy_shell_dependency_inventory.md",
    "docs/d8_legacy_shell_allowed_fallback_matrix.md",
    "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
    "docs/d8_1_legacy_fallback_route_matrix.md",
    "docs/d8_2_legacy_fallback_route_lockdown_preflight.md",
    "docs/d8_3_legacy_flask_shell_archive_package_plan.md",
    "docs/d8_3_legacy_package_move_map.md",
    "docs/d8_3_legacy_import_rewrite_plan.md",
    "docs/d8_4_legacy_flask_archive_package_implementation.md",
    "docs/d8_4_legacy_flask_archive_package_report.md",
    "docs/d8_5_legacy_db_maintenance_command_inventory.md",
    "docs/d8_5_legacy_db_maintenance_command_retirement_plan.md",
    "docs/d8_5_maintenance_command_replacement_matrix.md",
    "tools/check_d8_legacy_shell_retirement_readiness.py",
    "tools/check_d8_1_legacy_fallback_route_lockdown.py",
    "tools/check_d8_2_legacy_lockdown_preflight.py",
    "tools/check_d8_3_legacy_archive_move_readiness.py",
    "tools/check_d8_4_legacy_archive_package.py",
    "tools/check_d8_5_legacy_maintenance_command_readiness.py",
    "tests/test_d8_legacy_shell_retirement_readiness.py",
    "tests/test_d8_1_legacy_fallback_route_lockdown.py",
    "tests/test_d8_2_legacy_lockdown_preflight.py",
    "tests/test_d8_3_legacy_archive_move_readiness.py",
    "tests/test_d8_4_legacy_archive_package.py",
    "tests/test_d8_5_legacy_maintenance_command_readiness.py",
    "legacy_flask/",
    "wecom_ability_service/__init__.py",
    "wecom_ability_service/routes.py",
    "wecom_ability_service/legacy_lockdown.py",
    "wecom_ability_service/http/__init__.py",
    "legacy_flask_app.py",
    "app.py",
    "openclaw_service/",
]


def _inventory_text() -> str:
    return INVENTORY.read_text(encoding="utf-8")


def _inventory_row(path: str) -> str:
    return next(line for line in _inventory_text().splitlines() if line.startswith(f"| `{path}` |"))


def test_d8_slim_inventory_exists_and_covers_requested_paths() -> None:
    assert INVENTORY.exists()
    text = _inventory_text()
    for path in REQUESTED_D8_PATHS:
        assert f"`{path}`" in text


def test_d8_inventory_keeps_existing_fallback_surfaces_and_does_not_restore_archive_package() -> None:
    text = _inventory_text()
    for path in [
        "app.py",
        "legacy_flask_app.py",
        "wecom_ability_service/__init__.py",
        "wecom_ability_service/routes.py",
        "wecom_ability_service/http/__init__.py",
    ]:
        assert (REPO_ROOT / path).exists(), path
        row = _inventory_row(path)
        assert "| keep |" in row

    assert not (REPO_ROOT / "openclaw_service").exists()
    openclaw_row = _inventory_row("openclaw_service/")
    assert "| keep absent |" in openclaw_row
    assert "D9.6 physical deletion" in openclaw_row

    assert not (REPO_ROOT / "legacy_flask").exists()
    legacy_flask_row = _inventory_row("legacy_flask/")
    assert "| needs_manual_review |" in legacy_flask_row
    assert "absent on current main" in legacy_flask_row

    shim_row = _inventory_row("wecom_ability_service/legacy_lockdown.py")
    assert "| needs_manual_review |" in shim_row
    assert "absent on current main" in shim_row


def test_d8_inventory_marks_minimal_d8_0_d8_1_and_d8_2_preflight_as_keep() -> None:
    for path in [
        "docs/d8_legacy_flask_shell_retirement_plan.md",
        "docs/d8_legacy_shell_dependency_inventory.md",
        "docs/d8_legacy_shell_allowed_fallback_matrix.md",
        "docs/d8_1_legacy_fallback_route_lockdown_plan.md",
        "docs/d8_1_legacy_fallback_route_matrix.md",
        "docs/d8_2_legacy_fallback_route_lockdown_preflight.md",
        "tools/check_d8_legacy_shell_retirement_readiness.py",
        "tools/check_d8_1_legacy_fallback_route_lockdown.py",
        "tools/check_d8_2_legacy_lockdown_preflight.py",
        "tests/test_d8_legacy_shell_retirement_readiness.py",
        "tests/test_d8_1_legacy_fallback_route_lockdown.py",
        "tests/test_d8_2_legacy_lockdown_preflight.py",
    ]:
        assert (REPO_ROOT / path).exists(), path
        assert "| keep |" in _inventory_row(path)


def test_d8_docs_do_not_use_forbidden_readiness_markers() -> None:
    for path in (REPO_ROOT / "docs").glob("d8_*.md"):
        text = path.read_text(encoding="utf-8")
        for marker in FORBIDDEN_D8_MARKERS:
            assert marker not in text, path


def test_d8_route_fallback_source_of_truth_status_is_declared() -> None:
    text = _inventory_text()
    assert "Route/fallback lockdown runtime" in text
    assert "Route/fallback lockdown docs" in text
    assert "D8.1 is planning-only" in text
    assert "docs/d8_1_legacy_fallback_route_matrix.md" in text
    assert "one runtime owner" in text
    assert "one docs matrix" in text


def test_d8_checker_and_test_duplicate_candidates_are_inventory_only() -> None:
    text = _inventory_text()
    assert "D8.0/D8.1 planning checkers and D8.2 preflight checker are present" in text
    assert "D8.0/D8.1 planning tests, D8.2 preflight tests, and this slim inventory guard are present" in text
    assert "consider a helper only if more D8 checkers return" in text
    assert "do not recreate old D8 test stacks" in text


def test_duplicate_next_source_is_still_absent() -> None:
    assert not (REPO_ROOT / "experiments/ai_crm_next/src/aicrm_next").exists()
    assert list((REPO_ROOT / "experiments/ai_crm_next").glob("**/src/aicrm_next*")) == []
