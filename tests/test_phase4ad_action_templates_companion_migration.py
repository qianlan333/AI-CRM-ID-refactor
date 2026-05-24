from __future__ import annotations

import re
import subprocess
from pathlib import Path

import tools.check_phase4ad_action_templates_companion_migration as checker


ROOT = Path(__file__).resolve().parents[1]


def test_checker_current_repo_passes() -> None:
    result = subprocess.run(
        [
            "python3",
            "tools/check_phase4ad_action_templates_companion_migration.py",
            "--output-md",
            "/tmp/phase4ad_action_templates_companion_migration_test.md",
            "--output-json",
            "/tmp/phase4ad_action_templates_companion_migration_test.json",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )

    assert result.returncode == 0, result.stdout
    assert "overall: PASS" in result.stdout


def test_authorizations_false() -> None:
    data = checker.load_yaml()

    assert checker.check_authorizations(data)["ok"]
    assert all(value is False for value in data["authorizations"].values())


def test_migration_scope_additive_only() -> None:
    data = checker.load_yaml()
    scope = data["migration_scope"]

    assert scope["additive_only"] is True
    assert scope["no_existing_table_mutation"] is True
    assert scope["no_backfill"] is True
    assert scope["no_runtime_usage"] is True
    assert scope["deployment_authorized"] is False


def test_both_companion_tables_present_in_yaml() -> None:
    data = checker.load_yaml()
    table_names = {table["name"] for table in data["tables"]}

    assert "automation_operation_template_idempotency" in table_names
    assert "automation_operation_template_audit_log" in table_names


def test_required_fields_present() -> None:
    data = checker.load_yaml()

    assert checker.check_tables(data)["ok"]


def test_idempotency_unique_constraint_present() -> None:
    data = checker.load_yaml()
    table = checker._table_by_name(data, "automation_operation_template_idempotency")

    assert any(
        checker.REQUIRED_IDEMPOTENCY_UNIQUE_FIELDS <= set(item["fields"])
        for item in table["unique_constraints"]
    )


def test_actual_migration_artifacts_contain_both_tables() -> None:
    report = checker.check_migration_artifacts()

    assert report["ok"], report["blockers"]


def test_no_destructive_sql_statements_added() -> None:
    report = checker.check_no_destructive_sql()

    assert report["ok"], report["blockers"]


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed, warnings = checker._changed_files_from_git()
    assert not warnings or isinstance(warnings, list)
    forbidden = [
        path
        for path in changed
        if path.startswith("aicrm_next/")
        or path.startswith("wecom_ability_service/http/")
        or path.startswith("wecom_ability_service/domains/")
        or path in {"app.py", "legacy_flask_app.py", "aicrm_next/production_compat/api.py"}
    ]

    assert forbidden == []


def test_docs_do_not_claim_forbidden_states() -> None:
    text = (ROOT / "docs/development/phase_4ad_action_templates_companion_migration.md").read_text(
        encoding="utf-8"
    ).lower()
    forbidden_patterns = [
        r"runtime implemented",
        r"production repository enabled",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]

    for pattern in forbidden_patterns:
        assert re.search(pattern, text) is None, pattern
