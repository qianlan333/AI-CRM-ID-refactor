from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import tools.check_phase4ag_action_templates_repository_adapter_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ag_action_templates_repository_adapter_plan.md"
YAML = ROOT / "docs/development/phase_4ag_action_templates_repository_adapter_plan.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report.get("blockers", []), ensure_ascii=False, indent=2)


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_repository_flags_correct() -> None:
    repo = checker.load_yaml(YAML)["planned_repository"]
    assert repo["backend_flag"] == "AICRM_ACTION_TEMPLATES_REPO_BACKEND"
    assert repo["database_url_flag"] == "AICRM_ACTION_TEMPLATES_DATABASE_URL"
    assert repo["default_backend"] == "fixture"
    assert repo["database_url_fallback_allowed"] is False
    assert repo["production_route_owner_unchanged"] is True


def test_tables_mapped() -> None:
    tables = checker.load_yaml(YAML)["tables"]
    assert tables["main"] == "automation_operation_templates"
    assert tables["idempotency"] == "automation_operation_template_idempotency"
    assert tables["audit"] == "automation_operation_template_audit_log"


def test_planned_methods_complete() -> None:
    methods = {item["name"]: item for item in checker.load_yaml(YAML)["planned_methods"]}
    assert checker.REQUIRED_METHODS <= set(methods)
    assert all(method["external_side_effect_allowed"] is False for method in methods.values())


def test_create_method_requires_transaction_idempotency_audit_rollback() -> None:
    methods = {item["name"]: item for item in checker.load_yaml(YAML)["planned_methods"]}
    create = methods["create_action_template"]
    assert create["transaction_required"] is True
    assert create["idempotency_required"] is True
    assert create["audit_required"] is True
    assert create["rollback_required"] is True


def test_excluded_methods_complete() -> None:
    excluded = set(checker.load_yaml(YAML)["excluded_methods"])
    assert checker.REQUIRED_EXCLUDED_METHODS <= excluded


def test_enablement_strategy_prevents_fixture_production_success_and_requires_flag() -> None:
    enablement = checker.load_yaml(YAML)["enablement_strategy"]
    assert enablement["explicit_flag_required"] is True
    assert enablement["fixture_default_retained"] is True
    assert enablement["production_fixture_success_blocked"] is True
    assert enablement["production_route_owner_switch_separate_pr"] is True
    assert enablement["production_compat_change_separate_pr"] is True


def test_parity_smoke_readiness_complete() -> None:
    readiness = checker.load_yaml(YAML)["parity_smoke_readiness"]
    assert readiness["local_test_db_harness_required"] is True
    assert readiness["staging_smoke_required"] is True
    assert readiness["production_readonly_dry_run_required"] is True
    assert readiness["production_write_dry_run_requires_separate_approval"] is True
    assert readiness["route_switch_requires_separate_approval"] is True


def test_no_runtime_files_changed_if_git_diff_available() -> None:
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
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden_patterns = [
        r"repository implemented",
        r"production repository enabled",
        r"production write authorized",
        r"route switch authorized",
        r"fallback removal authorized",
        r"production approved",
        r"canary approved",
        r"delete_ready\s+true",
    ]
    for pattern in forbidden_patterns:
        assert re.search(pattern, text) is None, pattern
