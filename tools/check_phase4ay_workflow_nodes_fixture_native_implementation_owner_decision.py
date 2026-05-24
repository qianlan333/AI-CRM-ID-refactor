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

DOC = ROOT / "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.md"
PLAN_YAML = ROOT / "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/workflow-nodes*"
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
    "node_transition_runtime_authorized",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
REQUIRED_DECISIONS = {
    "approve_or_decline_workflow_nodes_fixture_native_runtime_implementation",
    "confirm_list_create_metadata_only_scope",
    "confirm_no_update_delete_detail_route_expansion",
    "confirm_no_node_transition_runtime",
    "confirm_workflow_execution_timer_run_due_outbound_send_forbidden",
    "confirm_idempotency_audit_rollback_required",
    "confirm_dangerous_field_rejection_required",
    "confirm_rollback_owner",
}
REQUIRED_SAFE_OPTIONS = {
    "pause_workflow_nodes_and_select_next_internal_write_candidate",
    "owner_approves_phase_4az_fixture_native_runtime_implementation_package",
    "owner_defers_workflow_nodes_until_transition_runtime_plan_exists",
}
REJECTED_TRUE_FIELDS = {
    "production_route_owner_switch",
    "production_write",
    "fallback_removal",
    "production_compat_change",
    "staging_smoke_execution",
    "workflow_execution",
    "node_transition_runtime",
    "timer_execution",
    "outbound_send",
    "real_external_call",
    "update_delete_detail_route_expansion",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.md",
    "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.yaml",
    "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.md",
    "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
    "tools/check_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
    "tests/test_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
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

    if data.get("status") != "phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision_no_runtime_change":
        blockers.append("status must be Phase 4AY workflow-nodes owner decision no runtime change")
    decision = data.get("decision_package") if isinstance(data.get("decision_package"), dict) else {}
    if decision.get("type") != "owner_decision_and_candidate_deferral":
        blockers.append("decision_package.type must be owner_decision_and_candidate_deferral")
    if decision.get("auto_merge_under_throughput_allowed") is not True:
        blockers.append("decision_package must allow throughput auto-merge for docs-only deferral")
    if decision.get("docs_tools_tests_state_only") is not True or decision.get("runtime_implementation_included") is not False:
        blockers.append("decision_package must be docs/tools/tests/state only with no runtime implementation")

    paused = data.get("paused_candidate") if isinstance(data.get("paused_candidate"), dict) else {}
    if paused.get("route_family") != ROUTE:
        blockers.append("paused_candidate must be workflow-nodes")
    if paused.get("current_runtime_owner") != "production_compat" or paused.get("production_behavior") != "legacy_forward":
        blockers.append("workflow-nodes production owner must remain production_compat legacy_forward")
    if paused.get("owner_approval_required") is not True:
        blockers.append("paused_candidate.owner_approval_required must be true")
    if not str(paused.get("paused_by_pr", "")).strip():
        blockers.append("paused_candidate.paused_by_pr must be recorded or pending")
    required_assets = {
        "phase_4av_workflow_nodes_metadata_planning_completed",
        "phase_4aw_workflow_nodes_schema_route_surface_confirmation_completed",
        "phase_4ax_workflow_nodes_fixture_native_contract_planning_completed",
    }
    if not required_assets <= set(paused.get("completed_assets") or []):
        blockers.append("paused_candidate.completed_assets incomplete")
    if not REQUIRED_DECISIONS <= set(data.get("owner_decision_required") or []):
        blockers.append("owner_decision_required list incomplete")
    if not REQUIRED_SAFE_OPTIONS <= set(data.get("safe_next_options") or []):
        blockers.append("safe_next_options list incomplete")

    rejected = data.get("rejected_actions") if isinstance(data.get("rejected_actions"), dict) else {}
    for field in sorted(REJECTED_TRUE_FIELDS):
        if rejected.get(field) is not True:
            blockers.append(f"rejected_actions.{field} must be true")
    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("workflow-nodes route must exist in manifest and backlog")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("last_merged_pr") != "#655":
        blockers.append("phase_execution_state.last_merged_pr must record #655")
    if state.get("last_attempted_action") != "phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4AY")
    if state_update.get("phase_4ay_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AY completed step")
    if state.get("recommended_next_pr") != "phase_4az_next_internal_write_candidate_selection":
        blockers.append("phase_execution_state.recommended_next_pr must be Phase 4AZ candidate selection")
    if set(state.get("next_allowed_actions") or []) != {"phase_4az_next_internal_write_candidate_selection"}:
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4AZ candidate selection")

    state_paused = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(isinstance(item, dict) and item.get("route_family") == ROUTE and item.get("owner_approval_required") is True for item in state_paused):
        blockers.append("phase_execution_state.paused_candidates must include workflow-nodes owner decision pause")
    readiness = state.get("workflow_nodes_readiness") if isinstance(state.get("workflow_nodes_readiness"), dict) else {}
    for field in ("fixture_native_implementation_requires_owner_decision", "owner_decision_required", "paused"):
        if readiness.get(field) is not True:
            blockers.append(f"workflow_nodes_readiness.{field} must be true")
    if not str(readiness.get("paused_by_pr", "")).strip():
        blockers.append("workflow_nodes_readiness.paused_by_pr must be recorded or pending")
    for field in ("runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"workflow_nodes_readiness.{field} must be false")

    rec = data.get("phase_4az_recommendation") if isinstance(data.get("phase_4az_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "select_next_low_risk_internal_write_candidate":
        blockers.append("phase_4az_recommendation must recommend next candidate selection")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4az_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AY package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = ["# Phase 4AY Workflow Nodes Owner Decision Check", "", f"- overall: {report['overall']}", f"- ok: {str(report['ok']).lower()}", "", "## Blockers", *(f"- {item}" for item in report["blockers"]), "", "## Warnings", *(f"- {item}" for item in report["warnings"])]
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
