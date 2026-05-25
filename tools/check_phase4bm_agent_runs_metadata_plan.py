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

DOC = ROOT / "docs/development/phase_4bm_agent_runs_metadata_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4bm_agent_runs_metadata_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

AGENT_RUNS = "/api/admin/automation-conversion/agent-runs*"
REQUIRED_INCLUDED_ROUTES = {
    ("GET", "/api/admin/automation-conversion/agent-runs", "list_metadata_inventory_only"),
    ("GET", "/api/admin/automation-conversion/agent-runs/{run_id}", "detail_metadata_inventory_only"),
}
REQUIRED_EXCLUDED_ROUTES = {
    "/api/admin/automation-conversion/agent-runs",
    "/api/admin/automation-conversion/agent-runs/{run_id}/execute",
    "/api/admin/automation-conversion/agent-replay",
    "/api/admin/automation-conversion/agent-orchestration*",
    "/api/admin/automation-conversion/agent-outputs*",
}
REQUIRED_EXCLUDED_BEHAVIORS = {
    "run_creation",
    "run_update",
    "run_delete",
    "run_execution",
    "replay_execution",
    "orchestration_execution",
    "agent_output_generation",
    "llm_generation",
    "deepseek_adapter_call",
    "openclaw_mcp_call",
    "wecom_payment_oauth_call",
    "workflow_execution",
    "timer_execution",
    "outbound_send",
    "real_external_call",
    "production_write",
    "production_route_owner_switch",
    "fallback_removal",
}
REQUIRED_METADATA_FIELDS = {
    "id",
    "run_id",
    "request_id",
    "agent_code",
    "run_status",
    "trigger_source",
    "created_at",
}
REQUIRED_DEFERRED_TABLES = {
    "automation_agent_output",
    "automation_agent_llm_call_log",
    "automation_agent_orchestration_event",
    "automation_workflow_execution",
}
REQUIRED_CONTRACT_TRUE = {
    "list_contract_planning_ready",
    "detail_contract_planning_ready",
    "run_creation_excluded",
    "run_execution_excluded",
    "replay_execution_excluded",
    "orchestration_execution_excluded",
    "agent_output_generation_excluded",
    "llm_generation_excluded",
    "external_side_effects_excluded",
    "masked_visibility_required",
    "pagination_required",
    "output_payloads_metadata_only",
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
    "run_creation_authorized",
    "run_execution_authorized",
    "replay_execution_authorized",
    "orchestration_execution_authorized",
    "agent_output_generation_authorized",
    "llm_generation_authorized",
    "deepseek_adapter_authorized",
    "openclaw_mcp_authorized",
    "workflow_execution_authorized",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4bm_agent_runs_metadata_plan.md",
    "docs/development/phase_4bm_agent_runs_metadata_plan.yaml",
    "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.md",
    "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4bm_agent_runs_metadata_plan.py",
    "tools/check_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4bm_agent_runs_metadata_plan.py",
    "tests/test_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
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

    if data.get("status") != "phase_4bm_agent_runs_metadata_planning_no_runtime_change":
        blockers.append("status must be Phase 4BM agent-runs metadata planning no runtime change")
    if data.get("route_family") != AGENT_RUNS:
        blockers.append("route_family must be agent-runs wildcard")
    if AGENT_RUNS not in manifest_text or AGENT_RUNS not in backlog_text:
        blockers.append("agent-runs route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("phase") != "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision" or previous.get("merged_pr") != "#669":
        blockers.append("previous_phase must record Phase 4BL merged as #669")
    if previous.get("completed") is not True:
        blockers.append("previous_phase.completed must be true")

    scope = data.get("planning_scope") if isinstance(data.get("planning_scope"), dict) else {}
    if scope.get("selected_subset") != "agent_runs_metadata_readonly":
        blockers.append("planning_scope.selected_subset must be agent_runs_metadata_readonly")
    if set(scope.get("allowed_methods_for_future_contract_planning") or []) != {"GET"}:
        blockers.append("future contract planning methods must be GET only")
    included_routes = {
        (str(item.get("method")), str(item.get("path")), str(item.get("status")))
        for item in scope.get("included_routes", [])
        if isinstance(item, dict)
    }
    if not REQUIRED_INCLUDED_ROUTES <= included_routes:
        blockers.append("planning_scope.included_routes must cover list/detail metadata inventory")
    if not REQUIRED_EXCLUDED_ROUTES <= set(scope.get("excluded_routes") or []):
        blockers.append("planning_scope.excluded_routes incomplete")
    if not REQUIRED_EXCLUDED_BEHAVIORS <= set(scope.get("excluded_behaviors") or []):
        blockers.append("planning_scope.excluded_behaviors incomplete")

    metadata = data.get("candidate_metadata_model") if isinstance(data.get("candidate_metadata_model"), dict) else {}
    if not REQUIRED_METADATA_FIELDS <= set(metadata.get("required_fields") or []):
        blockers.append("candidate_metadata_model.required_fields incomplete")
    if not REQUIRED_DEFERRED_TABLES <= set(metadata.get("related_tables_deferred") or []):
        blockers.append("candidate_metadata_model.related_tables_deferred incomplete")

    contract = data.get("contract_planning") if isinstance(data.get("contract_planning"), dict) else {}
    for field in sorted(REQUIRED_CONTRACT_TRUE):
        if contract.get(field) is not True:
            blockers.append(f"contract_planning.{field} must be true")
    if contract.get("production_data_allowed") is not False:
        blockers.append("contract_planning.production_data_allowed must be false")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != AGENT_RUNS:
        blockers.append("phase_execution_state.active_candidate must remain agent-runs")
    if state.get("last_merged_pr") != "#669":
        blockers.append("phase_execution_state.last_merged_pr must record #669")
    if state.get("last_attempted_action") != "phase_4bm_agent_runs_metadata_planning":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4BM")
    if state.get("last_created_pr") != "#670":
        blockers.append("phase_execution_state.last_created_pr must be #670")
    if state.get("recommended_next_pr") != "phase_4bn_agent_runs_schema_route_surface_confirmation":
        blockers.append("phase_execution_state.recommended_next_pr must be Phase 4BN")
    if set(state.get("next_allowed_actions") or []) != {"phase_4bn_agent_runs_schema_route_surface_confirmation"}:
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4BN")
    if state.get("owner_approval_required") is not False:
        blockers.append("phase_execution_state.owner_approval_required must remain false for metadata planning")
    if state_update.get("phase_4bm_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4BM completed step")

    readiness = state.get("agent_runs_readiness") if isinstance(state.get("agent_runs_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "run_creation_excluded",
        "run_execution_excluded",
        "replay_execution_excluded",
        "orchestration_execution_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"agent_runs_readiness.{field} must be true")
    for field in (
        "fixture_native_contract_planning_ready",
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
            blockers.append(f"agent_runs_readiness.{field} must be false")

    rec = data.get("phase_4bn_recommendation") if isinstance(data.get("phase_4bn_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "agent_runs_schema_route_surface_confirmation":
        blockers.append("phase_4bn_recommendation must recommend schema/route surface confirmation")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4bn_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4BM package: {unexpected}")
    protected = sorted(path for path in changed if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES))
    if protected:
        blockers.append(f"runtime/protected files changed: {protected}")

    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "route_family": data.get("route_family"),
            "selected_subset": scope.get("selected_subset"),
            "changed_files": sorted(changed),
        },
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4BM Agent Runs Metadata Planning Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- route_family: {report['details'].get('route_family')}",
            f"- selected_subset: {report['details'].get('selected_subset')}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
