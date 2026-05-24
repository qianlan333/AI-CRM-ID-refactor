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

DOC = ROOT / "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"
SCHEMA = ROOT / "wecom_ability_service/schema_postgres.sql"
PRODUCTION_COMPAT = ROOT / "aicrm_next/production_compat/api.py"

ROUTE = "/api/admin/automation-conversion/workflow-nodes*"
MAIN_TABLE = "automation_workflow_node"
REQUIRED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"}
REQUIRED_COLUMNS = {
    "id",
    "workflow_id",
    "node_code",
    "node_name",
    "target_audience_code",
    "trigger_mode",
    "day_offset",
    "send_time",
    "timezone",
    "position_index",
    "enabled",
    "created_at",
    "updated_at",
}
REQUIRED_INDEXES = {
    "uq_automation_workflow_node_code",
    "idx_automation_workflow_node_position",
    "idx_automation_workflow_node_schedule",
}
DEFERRED_TABLES = {
    "automation_workflow_node_content",
    "automation_workflow_node_content_variant",
    "automation_workflow_node_transition",
    "automation_workflow_execution",
    "automation_workflow_execution_item",
    "automation_frequency_budget",
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
BOUNDARY_TRUE_FIELDS = {
    "list_create_metadata_planning_allowed",
    "update_delete_deferred",
    "workflow_activation_deferred",
    "workflow_execution_deferred",
    "node_transition_runtime_deferred",
    "timer_execution_deferred",
    "outbound_send_deferred",
    "execution_records_deferred",
}
EXCLUDED_TRUE_FIELDS = {
    "workflows_route_family",
    "tasks_route_family",
    "run_due",
    "workflow_activation",
    "workflow_execution",
    "node_transition_runtime",
    "timer_execution",
    "automation_execution",
    "outbound_send",
    "real_external_call",
    "production_write",
    "production_route_switch",
    "fallback_removal",
    "production_compat_change",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.md",
    "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.yaml",
    "docs/development/phase_4av_workflow_nodes_metadata_plan.md",
    "docs/development/phase_4av_workflow_nodes_metadata_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
    "tools/check_phase4av_workflow_nodes_metadata_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
    "tests/test_phase4av_workflow_nodes_metadata_plan.py",
    "tests/test_autonomous_development_loop.py",
    "tests/test_automerge_eligibility.py",
    "tests/test_codex_autopilot_runtime_contract.py",
}
PROTECTED_PREFIXES = ("aicrm_next/", "wecom_ability_service/", "migrations/", "deploy/", "systemd/", "nginx/")
PROTECTED_EXACT = {"app.py", "legacy_flask_app.py"}
FORBIDDEN_DOC_CLAIMS = {"production_ready", "delete_ready true", "delete_ready: true", "canary_approved", "canary approved", "route_switch_ready=true"}


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
    for path in (DOC, PLAN_YAML, STATE, MANIFEST, BACKLOG, SCHEMA, PRODUCTION_COMPAT):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    schema_text = SCHEMA.read_text(encoding="utf-8")
    compat_text = PRODUCTION_COMPAT.read_text(encoding="utf-8")

    if data.get("status") != "phase_4aw_workflow_nodes_schema_route_surface_confirmation_no_runtime_change":
        blockers.append("status must be Phase 4AW workflow-nodes schema route surface confirmation no runtime change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be workflow-nodes wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("workflow-nodes route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")
    if "@router.api_route(\"/api/admin/automation-conversion/workflow-nodes/{path:path}\"" not in compat_text:
        blockers.append("production_compat must still register workflow-nodes wildcard legacy route")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("merged_pr") != "#653" or previous.get("completed") is not True:
        blockers.append("previous_phase must record Phase 4AV merged in #653")

    route_surface = data.get("confirmed_legacy_route_surface") if isinstance(data.get("confirmed_legacy_route_surface"), list) else []
    paths = {str(item.get("path")) for item in route_surface if isinstance(item, dict)}
    if paths != {"/api/admin/automation-conversion/workflow-nodes/{path:path}"}:
        blockers.append("confirmed_legacy_route_surface must include workflow-nodes wildcard route")
    for item in route_surface:
        if isinstance(item, dict) and set(item.get("methods") or []) != REQUIRED_METHODS:
            blockers.append(f"legacy route methods incomplete for {item.get('path')}")
        if isinstance(item, dict) and item.get("production_behavior") != "legacy_forward":
            blockers.append(f"legacy route production behavior must be legacy_forward for {item.get('path')}")

    table = data.get("primary_table") if isinstance(data.get("primary_table"), dict) else {}
    if table.get("name") != MAIN_TABLE:
        blockers.append("primary_table.name must be automation_workflow_node")
    if f"CREATE TABLE IF NOT EXISTS {MAIN_TABLE}" not in schema_text:
        blockers.append("schema_postgres.sql must define automation_workflow_node")
    if not REQUIRED_COLUMNS <= set(table.get("required_columns") or []):
        blockers.append("primary_table.required_columns incomplete")
    if not REQUIRED_INDEXES <= set(table.get("required_indexes") or []):
        blockers.append("primary_table.required_indexes incomplete")
    for item in sorted(REQUIRED_COLUMNS | REQUIRED_INDEXES | DEFERRED_TABLES):
        if item not in schema_text:
            blockers.append(f"schema_postgres.sql missing referenced workflow-node artifact: {item}")
    if not DEFERRED_TABLES <= set(data.get("deferred_related_tables") or []):
        blockers.append("deferred_related_tables incomplete")

    boundary = data.get("metadata_only_boundary") if isinstance(data.get("metadata_only_boundary"), dict) else {}
    for field in sorted(BOUNDARY_TRUE_FIELDS):
        if boundary.get(field) is not True:
            blockers.append(f"metadata_only_boundary.{field} must be true")

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
        blockers.append("phase_execution_state.active_candidate must remain workflow-nodes while Phase 4AX advances")
    if state.get("last_merged_pr") != "#653":
        blockers.append("phase_execution_state.last_merged_pr must record #653")
    if state_update.get("phase_4aw_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AW completed step")
    if set(state.get("next_allowed_actions") or []) != {"phase_4ax_workflow_nodes_fixture_native_contract_planning"}:
        blockers.append("phase_execution_state.next_allowed_actions must advance to Phase 4AX")
    readiness = state.get("workflow_nodes_readiness") if isinstance(state.get("workflow_nodes_readiness"), dict) else {}
    if readiness.get("schema_route_surface_confirmed") is not True or readiness.get("fixture_native_contract_planning_ready") is not True:
        blockers.append("workflow_nodes_readiness must confirm schema surface and mark fixture planning ready")
    for field in ("runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"workflow_nodes_readiness.{field} must be false")

    rec = data.get("phase_4ax_recommendation") if isinstance(data.get("phase_4ax_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "workflow_nodes_fixture_native_contract_planning":
        blockers.append("phase_4ax_recommendation must recommend workflow-nodes fixture/native contract planning")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4ax_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AW package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = ["# Phase 4AW Workflow Nodes Schema Route Surface Check", "", f"- overall: {report['overall']}", f"- ok: {str(report['ok']).lower()}", "", "## Blockers", *(f"- {item}" for item in report["blockers"]), "", "## Warnings", *(f"- {item}" for item in report["warnings"])]
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
