from __future__ import annotations

import re
import subprocess
from pathlib import Path

from tools import check_phase4h_profile_segment_template_companion_migration as checker


ROOT = Path(__file__).resolve().parents[1]


def test_phase4h_checker_passes_current_repo() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report.get("blockers")


def test_yaml_authorization_flags_are_false() -> None:
    data = checker.load_yaml()
    for field in checker.AUTH_FALSE_FIELDS:
        assert data[field] is False


def test_migration_scope_is_additive_only() -> None:
    scope = checker.load_yaml()["migration_scope"]
    for field in checker.REQUIRED_SCOPE_TRUE:
        assert scope[field] is True


def test_companion_tables_and_required_fields_are_documented() -> None:
    data = checker.load_yaml()
    idempotency = checker._table_by_name(data, checker.IDEMPOTENCY_TABLE)
    audit = checker._table_by_name(data, checker.AUDIT_TABLE)
    assert idempotency
    assert audit
    assert checker.REQUIRED_IDEMPOTENCY_FIELDS <= checker._field_names(idempotency)
    assert checker.REQUIRED_AUDIT_FIELDS <= checker._field_names(audit)


def test_idempotency_unique_constraint_present() -> None:
    data = checker.load_yaml()
    idempotency = checker._table_by_name(data, checker.IDEMPOTENCY_TABLE)
    assert any(
        checker.REQUIRED_IDEMPOTENCY_UNIQUE_FIELDS <= field_set
        for field_set in checker._constraint_field_sets(idempotency)
    )


def test_actual_migration_artifact_contains_both_tables() -> None:
    text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in checker.MIGRATION_ARTIFACTS
    )
    assert checker.IDEMPOTENCY_TABLE in text
    assert checker.AUDIT_TABLE in text
    assert "UNIQUE (route_family, operation, operator, idempotency_key)" in text


def test_no_destructive_sql_added() -> None:
    report = checker.check_no_destructive_sql()
    assert report["ok"], report.get("blockers")


def test_no_unapproved_runtime_files_changed_if_git_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    forbidden = [
        path
        for path in changed
        if checker._is_protected_runtime_file(path)
        and path not in checker.ALLOWED_CHANGED_FILES
    ]
    assert not forbidden


def test_docs_do_not_claim_cutover_or_approval() -> None:
    text = checker.PLAN_MD.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"production repository implemented",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]
    for pattern in forbidden_patterns:
        assert not re.search(pattern, text)
