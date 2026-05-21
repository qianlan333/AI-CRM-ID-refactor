from __future__ import annotations

import importlib.util
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
INVENTORY = REPO_ROOT / "docs" / "legacy_dead_code_inventory.md"
CLEANUP_REPORT = REPO_ROOT / "docs" / "legacy_d6_5_dead_cleanup_report.md"
BLOCKER_MATRIX = REPO_ROOT / "docs" / "d7_write_external_blocker_matrix.md"
CHECKER_PATH = REPO_ROOT / "tools" / "check_legacy_dead_cleanup.py"


def _load_checker():
    spec = importlib.util.spec_from_file_location("check_legacy_dead_cleanup", CHECKER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _parse_table(path: Path) -> list[dict[str, str]]:
    checker = _load_checker()
    return checker.parse_markdown_table(path)


def test_required_d6_5_documents_exist() -> None:
    assert INVENTORY.exists()
    assert CLEANUP_REPORT.exists()
    assert BLOCKER_MATRIX.exists()
    assert CHECKER_PATH.exists()


def test_inventory_has_non_empty_rows_for_d1_to_d6() -> None:
    rows = _parse_table(INVENTORY)
    assert rows
    batches = {row["retirement_batch"] for row in rows}
    for batch in ("D1", "D2", "D3", "D4", "D5", "D6"):
        assert any(item.startswith(batch) or batch in item for item in batches)


def test_every_delete_row_has_reason_and_scan_evidence() -> None:
    rows = _parse_table(INVENTORY)
    delete_rows = [row for row in rows if row["decision"] == "delete"]
    assert delete_rows
    for row in delete_rows:
        assert row["retirement_batch"]
        assert row["reason"]
        assert row["scan_evidence"]


def test_write_external_runtime_capabilities_are_not_marked_delete() -> None:
    rows = _parse_table(INVENTORY)
    protected_rows = [
        row
        for row in rows
        if row["write_external_runtime_dependency"].lower() not in {"no", "none", "false"}
    ]
    assert protected_rows
    assert all(row["decision"] != "delete" for row in protected_rows)


def test_d7_blocker_matrix_covers_required_capabilities_and_has_no_forbidden_markers() -> None:
    checker = _load_checker()
    source = BLOCKER_MATRIX.read_text(encoding="utf-8")
    for capability in checker.REQUIRED_CAPABILITIES:
        assert capability in source
    assert "delete_ready" not in source
    assert "production_ready" not in source
    assert "production_approved" not in source


def test_checker_runs_and_returns_ok_with_current_files() -> None:
    checker = _load_checker()
    report = checker.build_report(INVENTORY, BLOCKER_MATRIX)
    assert report["ok"], report
    assert report["production_config_modified"] is False
    assert report["d7_blockers_verified"] is True
    assert report["stale_imports"] == []
    assert report["protected_files_missing"] == []


def test_checker_fails_if_protected_file_is_missing(monkeypatch) -> None:
    checker = _load_checker()
    monkeypatch.setattr(checker, "PROTECTED_FILES", ["missing/protected_file.py"])
    report = checker.build_report(INVENTORY, BLOCKER_MATRIX)
    assert report["ok"] is False
    assert "missing/protected_file.py" in report["protected_files_missing"]


def test_checker_fails_if_deleted_file_is_still_imported(tmp_path: Path) -> None:
    checker = _load_checker()
    inventory = tmp_path / "inventory.md"
    inventory.write_text(
        "\n".join(
            [
                "| file_or_directory | retirement_batch | current_reference_status | route_registered | legacy_imported | test_referenced | docs_referenced | write_external_runtime_dependency | decision | reason | scan_evidence |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
                "| wecom_ability_service/http/automation_conversion.py | D6 Automation | fake deleted row | no | no | no | no | no | delete | fake stale import check | fake scan |",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    report = checker.build_report(inventory, BLOCKER_MATRIX)
    assert report["ok"] is False
    assert "wecom_ability_service/http/automation_conversion.py" in report["stale_imports"]


def test_checker_verifies_production_config_not_modified() -> None:
    checker = _load_checker()
    report = checker.build_report(INVENTORY, BLOCKER_MATRIX)
    assert report["production_config_modified"] is False


def test_app_py_default_remains_next() -> None:
    source = (REPO_ROOT / "app.py").read_text(encoding="utf-8")
    assert "Run AI-CRM Next FastAPI app (default runtime)." in source
    assert 'NEXT_APP_IMPORT = "aicrm_next.main:app"' in source
    assert "uvicorn.run(NEXT_APP_IMPORT" in source


def test_legacy_flask_app_exists() -> None:
    assert (REPO_ROOT / "legacy_flask_app.py").exists()


def test_no_old_backend_imports_in_aicrm_next() -> None:
    for path in (REPO_ROOT / "aicrm_next").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        assert "wecom_ability_service" not in source
        assert "openclaw_service" not in source
