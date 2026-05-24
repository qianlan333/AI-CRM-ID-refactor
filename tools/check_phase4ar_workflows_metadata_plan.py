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

DOC = ROOT / "docs/development/phase_4ar_workflows_metadata_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4ar_workflows_metadata_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/workflows*"
TASK_GROUPS = "/api/admin/automation-conversion/task-groups*"
REQUIRED_SCOPE = {
    "route_surface_confirmation",
    "metadata_only_subset_decision",
    "request_response_field_mapping",
    "validation_boundary_plan",
    "idempotency_plan",
    "audit_plan",
    "rollback_payload_plan",
    "fixture_local_contract_plan",
    "checker_and_test_plan",
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
EXCLUDED_TRUE_FIELDS = {
    "payment",
    "oauth",
    "wecom_external_call",
    "openclaw_mcp_real_call",
    "workflow_execution",
    "timer_execution",
    "run_due",
    "automation_execution",
    "outbound_send",
    "workflow_nodes_runtime",
    "task_runtime",
    "media_upload",
    "production_write",
    "production_route_switch",
    "fallback_removal",
    "production_compat_change",
}
REQUIRED_GUARDRAILS = {
    "keep_legacy_fallback",
    "no_production_owner_switch",
    "no_production_write",
    "no_external_calls",
    "no_workflow_execution",
    "no_timer_execution",
    "no_outbound_send",
    "fixture_local_evidence_not_production_success",
    "metadata_contract_before_runtime",
    "staging_and_owner_approval_before_production_use",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ar_workflows_metadata_plan.md",
    "docs/development/phase_4ar_workflows_metadata_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4ar_workflows_metadata_plan.py",
    "tools/check_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4ar_workflows_metadata_plan.py",
    "tests/test_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
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
    for path in (DOC, PLAN_YAML, STATE, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": {}}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")

    if data.get("status") != "phase_4ar_workflows_metadata_planning_no_runtime_change":
        blockers.append("status must be Phase 4AR workflows metadata planning no runtime change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be workflows wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("workflows route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True:
        blockers.append("legacy fallback must be retained")

    previous = data.get("previous_candidate") if isinstance(data.get("previous_candidate"), dict) else {}
    if previous.get("route_family") != TASK_GROUPS or previous.get("paused_by_pr") != "#648":
        blockers.append("previous_candidate must record task-groups paused by #648")
    if previous.get("owner_approval_required") is not True:
        blockers.append("previous_candidate.owner_approval_required must be true")

    selected = data.get("selected_candidate") if isinstance(data.get("selected_candidate"), dict) else {}
    if selected.get("route_family") != ROUTE or selected.get("replacement_phase") != "phase_4_internal_write":
        blockers.append("selected_candidate must be workflows Phase 4 internal_write")
    if selected.get("replacement_category") != "internal_write":
        blockers.append("selected_candidate.replacement_category must be internal_write")

    if not REQUIRED_SCOPE <= set(data.get("planned_contract_scope") or []):
        blockers.append("planned_contract_scope incomplete")
    excluded = data.get("excluded_scope") if isinstance(data.get("excluded_scope"), dict) else {}
    for field in sorted(EXCLUDED_TRUE_FIELDS):
        if excluded.get(field) is not True:
            blockers.append(f"excluded_scope.{field} must be true")
    if not REQUIRED_GUARDRAILS <= set(data.get("required_guardrails") or []):
        blockers.append("required_guardrails incomplete")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    for field in ("active_candidate", "last_merged_pr", "last_attempted_action", "recommended_next_pr", "owner_approval_required"):
        if state.get(field) != state_update.get(field):
            blockers.append(f"phase_execution_state.{field} must match Phase 4AR plan")
    if state_update.get("phase_4ar_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AR completed step")
    if set(state.get("next_allowed_actions") or []) != {"phase_4as_workflows_schema_route_surface_confirmation"}:
        blockers.append("next_allowed_actions must advance to Phase 4AS schema route surface confirmation")

    paused = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(isinstance(item, dict) and item.get("route_family") == TASK_GROUPS and item.get("paused_by_pr") == "#648" for item in paused):
        blockers.append("phase_execution_state.paused_candidates must include task-groups paused by #648")
    readiness = state.get("workflows_readiness") if isinstance(state.get("workflows_readiness"), dict) else {}
    if readiness.get("metadata_planning_completed") is not True or readiness.get("schema_route_surface_confirmation_ready") is not True:
        blockers.append("workflows_readiness must mark metadata planning complete and schema confirmation ready")
    for field in ("runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"workflows_readiness.{field} must be false")

    rec = data.get("phase_4as_recommendation") if isinstance(data.get("phase_4as_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "workflows_schema_route_surface_confirmation":
        blockers.append("phase_4as_recommendation must recommend workflows schema route surface confirmation")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4as_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AR package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = ["# Phase 4AR Workflows Metadata Planning Check", "", f"- overall: {report['overall']}", f"- ok: {str(report['ok']).lower()}", "", "## Blockers", *(f"- {item}" for item in report["blockers"]), "", "## Warnings", *(f"- {item}" for item in report["warnings"])]
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
