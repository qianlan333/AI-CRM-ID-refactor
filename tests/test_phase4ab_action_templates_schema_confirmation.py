from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "tools/check_phase4ab_action_templates_schema_confirmation.py"
DOC = ROOT / "docs/development/phase_4ab_action_templates_schema_confirmation.md"
YAML = ROOT / "docs/development/phase_4ab_action_templates_schema_confirmation.yaml"
AUTH_FIELDS = {
    "runtime_change_authorized",
    "production_repository_authorized",
    "migration_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "automation_execution_authorized",
    "outbound_send_authorized",
    "delete_ready",
}
REQUIRED_SERVICES = {
    "list_action_templates",
    "create_action_template",
    "generate_action_template",
    "create_action_template_from_workflow",
}
REQUIRED_FIELDS = {
    "id",
    "template_code",
    "template_name",
    "template_source",
    "category",
    "description",
    "status",
    "default_config_json",
    "ui_schema_json",
    "workflow_blueprint_json",
    "node_blueprints_json",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "archived_at",
}
REQUIRED_MAPPINGS = {
    "id",
    "code",
    "name",
    "template_source",
    "category",
    "description",
    "status",
    "default_config",
    "ui_schema",
    "workflow_blueprint",
    "node_blueprints",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "archived_at",
}
READINESS_DECISIONS = {
    "ready_for_fixture_native_contract",
    "needs_companion_idempotency_audit_planning",
    "needs_more_legacy_confirmation",
    "defer_due_to_external_side_effect_risk",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ab_action_templates_schema_confirmation.md",
    "docs/development/phase_4ab_action_templates_schema_confirmation.yaml",
    "tools/check_phase4ab_action_templates_schema_confirmation.py",
    "tests/test_phase4ab_action_templates_schema_confirmation.py",
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
    spec = importlib.util.spec_from_file_location("phase4ab_checker", CHECKER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_yaml(path)


def test_checker_current_repo_passes() -> None:
    proc = _run([sys.executable, str(CHECKER)])
    assert proc.returncode == 0, proc.stdout
    assert "overall: PASS" in proc.stdout


def test_authorizations_all_false() -> None:
    auth = _load_yaml()["authorizations"]
    for field in AUTH_FIELDS:
        assert auth[field] is False


def test_route_surface_confirms_list_create_and_excludes_generate() -> None:
    surface = _load_yaml()["route_surface"]
    routes = {
        (route["method"], route["path"]): route
        for route in surface["confirmed_routes"]
    }
    assert ("GET", "/api/admin/automation-conversion/action-templates") in routes
    assert ("POST", "/api/admin/automation-conversion/action-templates") in routes
    generate = routes[("POST", "/api/admin/automation-conversion/action-templates/generate")]
    assert generate["phase_4ac_scope_decision"] == "out_of_scope"
    from_workflow = routes[("POST", "/api/admin/automation-conversion/action-templates/from-workflow")]
    assert from_workflow["phase_4ac_scope_decision"] in {"defer", "out_of_scope", "in_scope"}
    assert from_workflow["reason"]


def test_services_include_required_functions() -> None:
    functions = {service["function"] for service in _load_yaml()["services"]}
    assert REQUIRED_SERVICES <= functions


def test_schema_table_and_fields_documented() -> None:
    schema = _load_yaml()["schema_confirmation"]
    assert schema["table"] == "automation_operation_templates"
    fields = {field["name"] for field in schema["fields"]}
    assert REQUIRED_FIELDS <= fields
    assert schema["timestamp_behavior"]
    assert schema["status_archive_behavior"]


def test_field_mapping_complete() -> None:
    mappings = {item["next_field"] for item in _load_yaml()["field_mapping_confirmation"]}
    assert REQUIRED_MAPPINGS <= mappings


def test_idempotency_audit_confirmation_explicit() -> None:
    section = _load_yaml()["idempotency_audit_confirmation"]
    assert section["dedicated_idempotency_storage_confirmed"] is False
    assert section["dedicated_audit_storage_confirmed"] is False
    assert section["before_after_snapshot_storage_confirmed"] is False
    assert section["operator_snapshot_confirmed"] is True
    assert section["companion_schema_may_be_required"] is True
    assert section["notes"]


def test_phase_4ac_readiness_decision_valid() -> None:
    decision = _load_yaml()["phase_4ac_readiness"]["decision"]
    assert decision in READINESS_DECISIONS


def test_phase_4ac_recommendation_forbids_high_risk_next_steps() -> None:
    rec = _load_yaml()["phase_4ac_recommendation"]
    assert rec["recommended_next_step"]
    assert rec["production_write_allowed"] is False
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
