#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools.check_phase4aq_task_groups_fixture_native_implementation_owner_decision import load_yaml

DOC = ROOT / "docs/development/phase_4at_workflows_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/workflows*"
REQUIRED_FIELDS = {
    "id",
    "program_id",
    "workflow_code",
    "workflow_name",
    "description",
    "review_status",
    "created_by_agent",
    "status",
    "segmentation_basis",
    "generation_mode",
    "profile_segment_template_id",
    "behavior_tier_scheme",
    "fallback_to_standard_content",
    "enabled",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
}
AUTH_FALSE_FIELDS = {
    "runtime_implementation_authorized",
    "staging_smoke_execution_authorized",
    "production_dry_run_execution_authorized",
    "production_data_connection_authorized",
    "production_write_authorized",
    "production_repository_route_enablement_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "real_external_call_authorized",
    "workflow_execution_authorized",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
SIDE_EFFECT_FALSE_FIELDS = {
    "real_external_call_allowed",
    "workflow_execution_allowed",
    "automation_execution_allowed",
    "outbound_send_allowed",
    "wecom_call_allowed",
    "openclaw_call_allowed",
    "mcp_call_allowed",
    "timer_execution_allowed",
    "production_data_allowed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4at_workflows_fixture_native_contract_plan.md",
    "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml",
    "docs/development/phase_4as_workflows_schema_route_surface_confirmation.md",
    "docs/development/phase_4as_workflows_schema_route_surface_confirmation.yaml",
    "docs/development/phase_4ar_workflows_metadata_plan.md",
    "docs/development/phase_4ar_workflows_metadata_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4at_workflows_fixture_native_contract_plan.py",
    "tools/check_phase4as_workflows_schema_route_surface_confirmation.py",
    "tools/check_phase4ar_workflows_metadata_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4at_workflows_fixture_native_contract_plan.py",
    "tests/test_phase4as_workflows_schema_route_surface_confirmation.py",
    "tests/test_phase4ar_workflows_metadata_plan.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
PROTECTED_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_DOC_CLAIMS = {
    "production_ready",
    "delete_ready true",
    "delete_ready: true",
    "canary_approved",
    "canary approved",
    "route_switch_ready=true",
}


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (["diff", "--name-only", "origin/main...HEAD"], ["diff", "--name-only"], ["diff", "--name-only", "--cached"]):
        ok, stdout, stderr = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
        else:
            warnings.append(f"git {' '.join(args)} unavailable: {(stderr or stdout).strip()}")
    ok, stdout, stderr = _run_git(["ls-files", "--others", "--exclude-standard"])
    if ok:
        changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    else:
        warnings.append(f"git ls-files --others unavailable: {(stderr or stdout).strip()}")
    return changed, warnings


def _require_false(mapping: dict[str, Any], fields: set[str], blockers: list[str], prefix: str) -> None:
    for field in sorted(fields):
        if mapping.get(field) is not False:
            blockers.append(f"{prefix}.{field} must be false")


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    for path in (DOC, PLAN_YAML, STATE, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")

    if data.get("status") != "phase_4at_workflows_fixture_native_contract_planning_no_runtime_change":
        blockers.append("status must be phase_4at_workflows_fixture_native_contract_planning_no_runtime_change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be workflows wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("workflows route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("merged_pr") != "#650" or previous.get("completed") is not True:
        blockers.append("previous_phase must record Phase 4AS merged in #650")

    routes = data.get("planned_fixture_routes") or []
    route_scopes = {(item.get("method"), item.get("scope")) for item in routes if isinstance(item, dict)}
    if route_scopes != {("GET", "fixture_local_list"), ("POST", "fixture_local_metadata_create")}:
        blockers.append("planned_fixture_routes must be GET list and POST metadata create only")

    excluded_paths = {str(item.get("path")) for item in data.get("excluded_routes") or [] if isinstance(item, dict)}
    required_excluded = {
        "/api/admin/automation-conversion/workflows/{workflow_id}",
        "/api/admin/automation-conversion/workflow-nodes*",
        "/api/admin/automation-conversion/tasks*",
        "/api/admin/automation-conversion/tasks/run-due",
        "/api/admin/automation-conversion/executions*",
    }
    if not required_excluded <= excluded_paths:
        blockers.append("excluded_routes must include detail/update/delete, workflow nodes, tasks, run-due, and executions")

    seed = data.get("fixture_seed") if isinstance(data.get("fixture_seed"), dict) else {}
    if seed.get("deterministic") is not True or seed.get("production_data_allowed") is not False:
        blockers.append("fixture_seed must be deterministic and forbid production data")
    if not {"phase4at_default_workflow", "phase4at_followup_workflow"} <= set(seed.get("workflow_codes") or []):
        blockers.append("fixture_seed.workflow_codes must include deterministic Phase 4AT seed codes")
    if not REQUIRED_FIELDS <= set(seed.get("required_fields") or []):
        blockers.append("fixture_seed.required_fields incomplete")

    list_contract = data.get("list_contract") if isinstance(data.get("list_contract"), dict) else {}
    required_list_keys = {"ok", "source_status", "route_owner", "workflows", "total", "count", "filters", "side_effect_safety"}
    if not required_list_keys <= set(list_contract.get("response_keys") or []):
        blockers.append("list_contract.response_keys incomplete")
    if list_contract.get("archived_workflows_excluded_by_default") is not True:
        blockers.append("list_contract must exclude archived workflows by default")
    if list_contract.get("ordering") != "updated_at_desc_id_desc":
        blockers.append("list_contract ordering must be updated_at_desc_id_desc")

    create_contract = data.get("create_contract") if isinstance(data.get("create_contract"), dict) else {}
    if not {"workflow_name", "idempotency_key"} <= set(create_contract.get("required_payload") or []):
        blockers.append("create_contract must require workflow_name and idempotency_key")
    required_create_keys = {"ok", "workflow", "audit_event", "rollback_payload", "idempotent_replay", "side_effect_safety"}
    if not required_create_keys <= set(create_contract.get("response_keys") or []):
        blockers.append("create_contract.response_keys incomplete")
    for field in ("missing_name_rejected", "duplicate_workflow_code_rejected", "invalid_status_rejected", "dangerous_fields_rejected"):
        if create_contract.get(field) is not True:
            blockers.append(f"create_contract.{field} must be true")

    idempotency = data.get("idempotency") if isinstance(data.get("idempotency"), dict) else {}
    for field in ("route_family_scope_required", "operation_scope_required", "operator_scope_required", "idempotency_key_required", "replay_same_hash", "conflict_different_hash"):
        if idempotency.get(field) is not True:
            blockers.append(f"idempotency.{field} must be true")

    audit = data.get("audit") if isinstance(data.get("audit"), dict) else {}
    for field in ("audit_event_required", "after_snapshot_required", "rollback_payload_required", "side_effect_safety_required"):
        if audit.get(field) is not True:
            blockers.append(f"audit.{field} must be true")
    if audit.get("before_snapshot_for_create") != "empty_object":
        blockers.append("audit.before_snapshot_for_create must be empty_object")

    side_effect = data.get("side_effect_safety") if isinstance(data.get("side_effect_safety"), dict) else {}
    _require_false(side_effect, SIDE_EFFECT_FALSE_FIELDS, blockers, "side_effect_safety")
    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    _require_false(authorizations, AUTH_FALSE_FIELDS, blockers, "authorizations")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    for field in ("active_candidate", "last_merged_pr", "last_attempted_action", "recommended_next_pr", "owner_approval_required"):
        if state.get(field) != state_update.get(field):
            blockers.append(f"phase_execution_state.{field} must match Phase 4AT plan")
    if state_update.get("phase_4at_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AT completed step")
    if set(state.get("next_allowed_actions") or []) != {"phase_4au_workflows_fixture_native_implementation_owner_decision"}:
        blockers.append("next_allowed_actions must advance to Phase 4AU owner decision")
    readiness = state.get("workflows_readiness") if isinstance(state.get("workflows_readiness"), dict) else {}
    for field in ("fixture_native_contract_planning_ready", "fixture_native_contract_planning_completed", "fixture_native_implementation_requires_owner_decision"):
        if readiness.get(field) is not True:
            blockers.append(f"workflows_readiness.{field} must be true")
    for field in ("runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"workflows_readiness.{field} must be false")

    rec = data.get("phase_4au_recommendation") if isinstance(data.get("phase_4au_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "workflows_fixture_native_implementation_owner_decision":
        blockers.append("phase_4au_recommendation must recommend workflows fixture/native implementation owner decision")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4au_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AT package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4AT Workflows Fixture Native Contract Plan Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Warnings",
            *(f"- {item}" for item in report["warnings"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(f"overall: {report['overall']}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
