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

DOC = ROOT / "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/tasks*"
MAIN_TABLE = "automation_operation_task"
REQUIRED_LEGACY_ROUTES = {
    ("GET", "/api/admin/automation-conversion/tasks"),
    ("POST", "/api/admin/automation-conversion/tasks"),
    ("GET", "/api/admin/automation-conversion/tasks/<task_id>"),
    ("PUT", "/api/admin/automation-conversion/tasks/<task_id>"),
    ("POST", "/api/admin/automation-conversion/tasks/<task_id>/copy"),
    ("POST", "/api/admin/automation-conversion/tasks/<task_id>/activate"),
    ("POST", "/api/admin/automation-conversion/tasks/<task_id>/pause"),
    ("DELETE", "/api/admin/automation-conversion/tasks/<task_id>"),
    ("POST", "/api/admin/automation-conversion/tasks/<task_id>/preview-audience"),
    ("POST", "/api/admin/automation-conversion/tasks/run-due"),
}
REQUIRED_COLUMNS = {
    "id",
    "program_id",
    "group_id",
    "task_name",
    "description",
    "status",
    "trigger_type",
    "send_time",
    "timezone",
    "target_audience_code",
    "target_stage_code",
    "audience_day_offset",
    "behavior_filter",
    "content_mode",
    "profile_segment_template_id",
    "unified_content_json",
    "segment_contents_json",
    "agent_config_json",
    "created_by",
    "updated_by",
    "created_at",
    "updated_at",
    "published_at",
}
REQUIRED_INDEXES = {
    "idx_automation_operation_task_program",
    "idx_automation_operation_task_group",
}
REQUIRED_RELATED_TABLES = {
    "automation_operation_task_group",
    "automation_operation_task_execution",
    "automation_operation_task_execution_item",
    "automation_profile_segment_template",
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
    "task_execution_authorized",
    "workflow_execution_authorized",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
EXCLUDED_TRUE_FIELDS = {
    "task_detail",
    "task_update",
    "task_copy",
    "task_activate_pause",
    "task_delete_archive",
    "preview_audience",
    "run_due",
    "task_execution",
    "workflow_execution",
    "timer_execution",
    "outbound_send",
    "real_external_call",
    "production_write",
    "production_route_switch",
    "fallback_removal",
    "production_compat_change",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.md",
    "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.yaml",
    "docs/development/phase_4ba_tasks_metadata_plan.md",
    "docs/development/phase_4ba_tasks_metadata_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4bb_tasks_schema_route_surface_confirmation.py",
    "tools/check_phase4ba_tasks_metadata_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4bb_tasks_schema_route_surface_confirmation.py",
    "tests/test_phase4ba_tasks_metadata_plan.py",
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

    if data.get("status") != "phase_4bb_tasks_schema_route_surface_confirmation_no_runtime_change":
        blockers.append("status must be Phase 4BB tasks schema route surface confirmation no runtime change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be tasks wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("tasks route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True:
        blockers.append("legacy fallback must be retained")
    if data.get("fixture_allowed_in_production") is not False:
        blockers.append("fixture_allowed_in_production must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("phase") != "phase_4ba_tasks_metadata_planning" or previous.get("merged_pr") != "#658":
        blockers.append("previous_phase must record Phase 4BA merged as #658")
    if previous.get("completed") is not True:
        blockers.append("previous_phase.completed must be true")

    surface = data.get("confirmed_route_surface") if isinstance(data.get("confirmed_route_surface"), dict) else {}
    patterns = set(surface.get("production_compat_patterns") or [])
    if "/api/admin/automation-conversion/tasks" not in patterns:
        blockers.append("production_compat tasks base pattern missing")
    if "/api/admin/automation-conversion/tasks/wildcard_path" not in patterns:
        blockers.append("production_compat tasks wildcard pattern missing")
    routes = {
        (str(item.get("method")), str(item.get("path")))
        for item in surface.get("legacy_registered_routes") or []
        if isinstance(item, dict)
    }
    if routes != REQUIRED_LEGACY_ROUTES:
        blockers.append("legacy registered route surface must include base, detail, actions, preview, and run-due")

    schema = data.get("confirmed_schema") if isinstance(data.get("confirmed_schema"), dict) else {}
    if schema.get("main_table") != MAIN_TABLE:
        blockers.append("confirmed_schema.main_table must be automation_operation_task")
    if not REQUIRED_COLUMNS <= set(schema.get("columns") or []):
        blockers.append("confirmed_schema.columns incomplete")
    if not REQUIRED_INDEXES <= set(schema.get("indexes") or []):
        blockers.append("confirmed_schema.indexes incomplete")
    if not REQUIRED_RELATED_TABLES <= set(schema.get("related_tables") or []):
        blockers.append("confirmed_schema.related_tables incomplete")
    relationship = schema.get("relationship_behavior") if isinstance(schema.get("relationship_behavior"), dict) else {}
    if relationship.get("execution_tables_excluded_from_metadata_subset") is not True:
        blockers.append("execution tables must be confirmed as excluded from metadata subset")

    contract = data.get("confirmed_contract") if isinstance(data.get("confirmed_contract"), dict) else {}
    if contract.get("list", {}).get("archived_tasks_excluded_by_default") is not True:
        blockers.append("list contract must exclude archived tasks by default")
    if contract.get("create", {}).get("success_status") != 201:
        blockers.append("create.success_status must be 201")
    if "task_name" not in set(contract.get("create", {}).get("required_payload") or []):
        blockers.append("create.required_payload must include task_name")
    if set(data.get("recommended_first_native_subset") or []) != {"list_operation_tasks", "create_operation_task_metadata_only"}:
        blockers.append("recommended_first_native_subset must be list/create metadata only")
    if not {"run_due_operation_tasks", "execution_tables", "outbound_send", "preview_operation_task_audience"} <= set(data.get("deferred_to_separate_pr") or []):
        blockers.append("deferred_to_separate_pr incomplete")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    excluded = data.get("excluded_scope") if isinstance(data.get("excluded_scope"), dict) else {}
    for field in sorted(EXCLUDED_TRUE_FIELDS):
        if excluded.get(field) is not True:
            blockers.append(f"excluded_scope.{field} must be true")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != ROUTE:
        blockers.append("phase_execution_state.active_candidate must remain tasks")
    if state.get("last_merged_pr") != "#658":
        blockers.append("phase_execution_state.last_merged_pr must record #658")
    if state.get("last_attempted_action") != "phase_4bb_tasks_schema_route_surface_confirmation":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4BB")
    if state.get("recommended_next_pr") != "phase_4bc_tasks_fixture_native_contract_planning":
        blockers.append("phase_execution_state.recommended_next_pr must be Phase 4BC fixture/native contract planning")
    if set(state.get("next_allowed_actions") or []) != {"phase_4bc_tasks_fixture_native_contract_planning"}:
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4BC fixture/native contract planning")
    if state.get("owner_approval_required") is not False:
        blockers.append("phase_execution_state.owner_approval_required must remain false")
    if state_update.get("phase_4bb_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4BB completed step")

    readiness = state.get("tasks_readiness") if isinstance(state.get("tasks_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "run_due_excluded",
        "task_execution_excluded",
        "workflow_execution_excluded",
        "timer_execution_excluded",
        "outbound_send_excluded",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
    for field in (
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if readiness.get(field) is not False:
            blockers.append(f"tasks_readiness.{field} must be false")

    rec = data.get("phase_4bc_recommendation") if isinstance(data.get("phase_4bc_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "tasks_fixture_native_contract_planning":
        blockers.append("phase_4bc_recommendation must recommend tasks fixture/native contract planning")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4bc_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4BB package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4BB Tasks Schema Route Surface Check",
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
