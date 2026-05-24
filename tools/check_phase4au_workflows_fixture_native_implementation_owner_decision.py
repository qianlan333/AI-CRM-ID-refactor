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

DOC = ROOT / "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md"
PLAN_YAML = ROOT / "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

WORKFLOWS = "/api/admin/automation-conversion/workflows*"
WORKFLOW_NODES = "/api/admin/automation-conversion/workflow-nodes*"
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
REQUIRED_DECISIONS = {
    "approve_or_decline_workflows_fixture_native_runtime_implementation",
    "confirm_list_create_metadata_only_scope",
    "confirm_workflow_activation_deferred",
    "confirm_workflow_nodes_deferred",
    "confirm_execution_timer_run_due_outbound_send_forbidden",
    "confirm_idempotency_audit_rollback_required",
    "confirm_dangerous_field_rejection_required",
}
REQUIRED_GUARDRAILS = {
    "planning_only",
    "metadata_only_subset",
    "no_runtime_implementation",
    "no_workflow_execution",
    "no_timer_execution",
    "no_outbound_send",
    "no_external_calls",
    "keep_legacy_fallback",
    "no_production_owner_switch",
    "no_production_write",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md",
    "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml",
    "docs/development/phase_4av_workflow_nodes_metadata_plan.md",
    "docs/development/phase_4av_workflow_nodes_metadata_plan.yaml",
    "docs/development/phase_4at_workflows_fixture_native_contract_plan.md",
    "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4au_workflows_fixture_native_implementation_owner_decision.py",
    "tools/check_phase4av_workflow_nodes_metadata_plan.py",
    "tools/check_phase4at_workflows_fixture_native_contract_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4au_workflows_fixture_native_implementation_owner_decision.py",
    "tests/test_phase4av_workflow_nodes_metadata_plan.py",
    "tests/test_phase4at_workflows_fixture_native_contract_plan.py",
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

    if data.get("status") != "phase_4au_workflows_fixture_native_implementation_owner_decision_no_runtime_change":
        blockers.append("status must be Phase 4AU workflows owner decision no runtime change")
    decision = data.get("decision_package") if isinstance(data.get("decision_package"), dict) else {}
    if decision.get("type") != "owner_decision_and_candidate_deferral":
        blockers.append("decision_package.type must be owner_decision_and_candidate_deferral")
    if decision.get("auto_merge_under_throughput_allowed") is not True:
        blockers.append("decision_package must allow throughput auto-merge for docs-only deferral")
    if decision.get("docs_tools_tests_state_only") is not True or decision.get("runtime_implementation_included") is not False:
        blockers.append("decision_package must be docs/tools/tests/state only with no runtime implementation")

    paused = data.get("paused_candidate") if isinstance(data.get("paused_candidate"), dict) else {}
    if paused.get("route_family") != WORKFLOWS:
        blockers.append("paused_candidate must be workflows")
    if paused.get("current_runtime_owner") != "production_compat" or paused.get("production_behavior") != "legacy_forward":
        blockers.append("workflows production owner must remain production_compat legacy_forward")
    if paused.get("owner_approval_required") is not True:
        blockers.append("paused_candidate.owner_approval_required must be true")
    required_assets = {
        "phase_4ar_workflows_metadata_planning_completed",
        "phase_4as_workflows_schema_route_surface_confirmation_completed",
        "phase_4at_workflows_fixture_native_contract_planning_completed",
    }
    if not required_assets <= set(paused.get("completed_assets") or []):
        blockers.append("paused_candidate.completed_assets incomplete")
    if not REQUIRED_DECISIONS <= set(data.get("owner_decision_required") or []):
        blockers.append("owner_decision_required list incomplete")

    next_candidate = data.get("next_candidate") if isinstance(data.get("next_candidate"), dict) else {}
    if next_candidate.get("selected_route_family") != WORKFLOW_NODES:
        blockers.append("next_candidate must be workflow-nodes")
    if next_candidate.get("replacement_phase") != "phase_4_internal_write" or next_candidate.get("replacement_category") != "internal_write":
        blockers.append("next_candidate must be Phase 4 internal_write")
    if next_candidate.get("current_runtime_owner") != "production_compat" or next_candidate.get("production_behavior") != "legacy_forward":
        blockers.append("workflow-nodes production owner must remain production_compat legacy_forward")
    if not REQUIRED_GUARDRAILS <= set(next_candidate.get("required_guardrails") or []):
        blockers.append("next_candidate.required_guardrails incomplete")
    for route in (WORKFLOWS, WORKFLOW_NODES):
        if route not in manifest_text or route not in backlog_text:
            blockers.append(f"{route} must exist in manifest and backlog")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state_update.get("phase_4au_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4AU completed step")
    state_paused = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(isinstance(item, dict) and item.get("route_family") == WORKFLOWS and item.get("owner_approval_required") is True for item in state_paused):
        blockers.append("phase_execution_state.paused_candidates must include workflows owner decision pause")
    workflows = state.get("workflows_readiness") if isinstance(state.get("workflows_readiness"), dict) else {}
    for field in ("fixture_native_implementation_requires_owner_decision", "owner_decision_required", "paused"):
        if workflows.get(field) is not True:
            blockers.append(f"workflows_readiness.{field} must be true")
    for field in ("runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if workflows.get(field) is not False:
            blockers.append(f"workflows_readiness.{field} must be false")
    nodes = state.get("workflow_nodes_readiness") if isinstance(state.get("workflow_nodes_readiness"), dict) else {}
    if nodes.get("metadata_planning_ready") is not True:
        blockers.append("workflow_nodes_readiness.metadata_planning_ready must be true")
    for field in ("fixture_native_contract_planning_ready", "runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if nodes.get(field) is not False:
            blockers.append(f"workflow_nodes_readiness.{field} must be false")

    rec = data.get("phase_4av_recommendation") if isinstance(data.get("phase_4av_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "workflow_nodes_metadata_planning":
        blockers.append("phase_4av_recommendation must recommend workflow-nodes metadata planning")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4av_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4AU package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": {"changed_files": sorted(changed)}}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = ["# Phase 4AU Workflows Owner Decision Check", "", f"- overall: {report['overall']}", f"- ok: {str(report['ok']).lower()}", "", "## Blockers", *(f"- {item}" for item in report["blockers"]), "", "## Warnings", *(f"- {item}" for item in report["warnings"])]
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
