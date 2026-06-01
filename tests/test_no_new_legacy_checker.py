from __future__ import annotations

from pathlib import Path

from scripts.check_no_new_legacy import check_customer_read_model_legacy_deletion, scan_source_tree


def test_no_new_legacy_checker_flags_disallowed_legacy_import(tmp_path: Path) -> None:
    target = tmp_path / "aicrm_next/new_api.py"
    target.parent.mkdir()
    target.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    violations = scan_source_tree(tmp_path)

    assert [violation.code for violation in violations] == ["legacy_flask_facade_import"]
    payload = violations[0].to_dict()
    assert payload["path"] == "aicrm_next/new_api.py"
    assert "route registry" in payload["remediation"]


def test_no_new_legacy_checker_exempts_tests_and_docs(tmp_path: Path) -> None:
    docs = tmp_path / "docs/note.py"
    tests = tmp_path / "tests/test_note.py"
    docs.parent.mkdir()
    tests.parent.mkdir()
    docs.write_text("from wecom_ability_service.db import get_db\n", encoding="utf-8")
    tests.write_text("from aicrm_next.integration_gateway.legacy_flask_facade import forward_to_legacy_flask\n", encoding="utf-8")

    assert scan_source_tree(tmp_path) == []


def test_customer_read_model_legacy_deletion_guard_flags_deleted_patterns(tmp_path: Path) -> None:
    crm = tmp_path / "aicrm_next/customer_read_model/application.py"
    script = tmp_path / "scripts/backfill_customer_read_model.py"
    crm.parent.mkdir(parents=True)
    script.parent.mkdir(parents=True)
    crm.write_text(
        "from aicrm_next.integration_gateway.legacy_customer_read_facade import get_customer_via_legacy\n"
        "CUSTOMER_READ_MODEL" + "_LEGACY_ROLLBACK_ENABLED = '1'\n"
        "LegacyShadowCustomerReadModelSource\n",
        encoding="utf-8",
    )
    script.write_text("target = get_settings().database_url\nsource = 'legacy-shadow'\n", encoding="utf-8")

    violations = check_customer_read_model_legacy_deletion(tmp_path)
    codes = {violation.code for violation in violations}

    assert "customer_read_legacy_facade_import" in codes
    assert "customer_read_legacy_rollback_flag" in codes
    assert "customer_read_legacy_shadow_source" in codes
    assert "customer_read_backfill_execute_uses_default_database" in codes
    assert "customer_read_backfill_legacy_source" in codes
