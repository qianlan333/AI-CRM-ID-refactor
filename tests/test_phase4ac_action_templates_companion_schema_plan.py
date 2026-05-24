from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4ac_action_templates_companion_schema_plan.py"
DOC = ROOT / "docs/development/phase_4ac_action_templates_companion_schema_plan.md"
YAML = ROOT / "docs/development/phase_4ac_action_templates_companion_schema_plan.yaml"
AUTH_FIELDS = {
    "runtime_change_authorized",
    "migration_authorized",
    "production_repository_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
IDEMPOTENCY_FIELDS = {
    "route_family",
    "operation",
    "operator",
    "idempotency_key",
    "request_hash",
    "response_snapshot",
    "resource_type",
    "resource_id",
    "status",
    "created_at",
    "updated_at",
}
AUDIT_FIELDS = {
    "route_family",
    "operation",
    "operator",
    "resource_type",
    "resource_id",
    "before_snapshot",
    "after_snapshot",
    "request_payload",
    "validation_result",
    "rollback_payload",
    "side_effect_safety",
    "created_at",
}
SCOPE_CONSTRAINTS = {
    "generate_route_excluded",
    "from_workflow_route_deferred",
    "deepseek_llm_adapter_excluded",
    "workflow_execution_excluded",
    "outbound_send_excluded",
    "timer_excluded",
    "openclaw_mcp_excluded",
    "wecom_external_call_excluded",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ac_action_templates_companion_schema_plan.md",
    "docs/development/phase_4ac_action_templates_companion_schema_plan.yaml",
    "tools/check_phase4ac_action_templates_companion_schema_plan.py",
    "tests/test_phase4ac_action_templates_companion_schema_plan.py",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tools/check_phase4aa_action_templates_implementation_plan.py",
    "tools/check_phase4z_profile_segment_template_approval_wait_and_next_candidate.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/",
    "wecom_ability_service/",
    "migrations/",
    "deploy/",
    "systemd/",
    "nginx/",
)
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def _load_yaml(path: Path = YAML) -> dict:
    spec = importlib.util.spec_from_file_location("phase4ac_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(path)


def _field_names(values: list[dict]) -> set[str]:
    return {item["name"] for item in values}


def test_checker_current_repo_passes() -> None:
    proc = _run([sys.executable, str(CHECKER)])
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_authorizations_all_false() -> None:
    auth = _load_yaml()["authorizations"]
    for field in AUTH_FIELDS:
        assert auth[field] is False


def test_schema_need_requires_idempotency_audit_and_snapshots() -> None:
    need = _load_yaml()["schema_need"]
    assert need["idempotency_storage_required"] is True
    assert need["audit_storage_required"] is True
    assert need["before_after_snapshot_required"] is True
    assert need["reason"]


def test_idempotency_plan_has_required_fields_and_unique_constraint() -> None:
    plan = _load_yaml()["idempotency_schema_plan"]
    assert plan["strategy"] == "new_companion_table"
    assert plan["proposed_table"] == "automation_operation_template_idempotency"
    assert IDEMPOTENCY_FIELDS <= _field_names(plan["required_fields"])
    unique_fields = set()
    for constraint in plan["unique_constraints"]:
        unique_fields.update(constraint["fields"])
    assert {"route_family", "operation", "operator", "idempotency_key"} <= unique_fields
    assert plan["conflict_behavior"]
    assert plan["replay_behavior"]
    assert plan["retention_policy"]


def test_audit_plan_has_required_fields_and_policies() -> None:
    plan = _load_yaml()["audit_schema_plan"]
    assert plan["strategy"] == "new_companion_table"
    assert plan["proposed_table"] == "automation_operation_template_audit_log"
    assert AUDIT_FIELDS <= _field_names(plan["required_fields"])
    assert plan["snapshot_policy"]
    assert plan["rollback_payload_policy"]
    assert plan["retention_policy"]


def test_scope_constraints_exclude_high_risk_surfaces() -> None:
    constraints = _load_yaml()["scope_constraints"]
    for field in SCOPE_CONSTRAINTS:
        assert constraints[field] is True


def test_migration_readiness_blocks_migration_now_and_requires_additive_later() -> None:
    readiness = _load_yaml()["migration_readiness"]
    assert readiness["migration_artifact_authorized_now"] is False
    assert readiness["additive_only_required"] is True
    assert readiness["main_table_mutation_forbidden"] is True
    assert readiness["backfill_forbidden"] is True
    assert readiness["destructive_sql_forbidden"] is True
    assert readiness["deployment_requires_owner_approval"] is True


def test_phase_4ad_recommendation_forbids_high_risk_next_steps() -> None:
    rec = _load_yaml()["phase_4ad_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["migration_allowed_without_owner_approval"] is False
    assert rec["runtime_implementation_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed = set()
    for command in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        proc = _run(command)
        if proc.returncode != 0:
            continue
        changed.update(line.strip() for line in proc.stdout.splitlines() if line.strip())
    unexpected = changed - ALLOWED_CHANGED_FILES
    protected = {
        path
        for path in changed
        if path not in ALLOWED_CHANGED_FILES
        and (path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    }
    assert unexpected == set()
    assert protected == set()


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "migration created",
        "runtime implemented",
        "production repository enabled",
        "production write authorized",
        "route switch authorized",
        "fallback removal authorized",
        "production approved",
        "canary approved",
        "delete_ready true",
    ]
    for phrase in forbidden:
        assert phrase not in text
