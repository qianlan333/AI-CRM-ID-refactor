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

DOC = ROOT / "docs/development/phase_4by_agent_replay_discovery_contract_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4by_agent_replay_discovery_contract_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

AGENT_REPLAY = "/api/admin/automation-conversion/agent-replay"
TASK_GROUPS = "/api/admin/automation-conversion/task-groups*"
NEXT_BUNDLE = "phase_4ca_task_groups_repository_adapter_parity_bundle"
COMPLETED_STEP = "phase_4by_agent_replay_discovery_contract_bundle_completed"
REQUIRED_INCLUDED_STAGES = {
    "metadata_planning_carry_forward",
    "legacy_route_schema_surface_confirmation",
    "fixture_native_contract_planning",
    "machine_readable_yaml",
    "checker",
    "tests",
    "phase_execution_state_update",
    "replay_runtime_deferral_record",
}
REQUIRED_EXCLUDED_STAGES = {
    "runtime_implementation",
    "production_repository_enablement",
    "production_route_owner_switch",
    "production_write",
    "production_db_connection",
    "production_compat_change",
    "fallback_removal",
    "replay_creation",
    "replay_execution",
    "run_creation",
    "run_execution",
    "orchestration_execution",
    "agent_output_generation",
    "llm_generation",
    "deepseek_adapter_call",
    "openclaw_mcp_call",
    "real_external_call",
    "workflow_execution",
    "task_execution",
    "timer_execution",
    "run_due_execution",
    "outbound_send",
    "destructive_migration",
    "canary_approval",
    "delete_ready",
}
REQUIRED_RESPONSE_KEYS = {"ok", "source_status", "route_owner", "rows", "total", "filters", "side_effect_safety"}
REQUIRED_ROW_FIELDS = {
    "replay_request_id",
    "source_run_id",
    "request_id",
    "agent_code",
    "trigger_source",
    "replay_status",
    "replay_mode",
    "requested_by",
    "requested_at",
    "updated_at",
    "blocked_reason",
    "side_effects_enabled",
}
REQUIRED_DEFERRED_TABLES = {
    "automation_agent_run",
    "automation_agent_output",
    "automation_agent_orchestration_event",
    "automation_workflow_execution",
}
REQUIRED_SAFETY_TRUE = {
    "masked_visibility_required",
    "side_effect_safety_required",
    "fixture_data_not_production_evidence",
    "legacy_fallback_required",
    "production_guard_required_for_future_runtime",
}
REQUIRED_AUTH_FALSE = {
    "replay_creation_authorized",
    "replay_execution_authorized",
    "run_creation_authorized",
    "run_execution_authorized",
    "orchestration_execution_authorized",
    "agent_output_generation_authorized",
    "llm_generation_authorized",
    "deepseek_adapter_authorized",
    "openclaw_mcp_authorized",
    "real_external_call_authorized",
    "timer_execution_authorized",
    "outbound_send_authorized",
    "production_write_authorized",
    "production_route_ownership_switch_authorized",
    "fallback_removal_authorized",
    "production_compat_change_authorized",
    "canary_approval_authorized",
    "delete_ready",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4by_agent_replay_discovery_contract_bundle.md",
    "docs/development/phase_4by_agent_replay_discovery_contract_bundle.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4by_agent_replay_discovery_contract_bundle.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4by_agent_replay_discovery_contract_bundle.py",
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


def _list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _strings(value: Any) -> set[str]:
    return {str(item) for item in _list(value)}


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, PLAN_YAML, STATE, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")
    if blockers:
        return {"overall": "FAIL", "ok": False, "autopilot_deliverable": False, "blockers": blockers, "warnings": warnings, "details": details}

    data = load_yaml(PLAN_YAML)
    state = load_yaml(STATE)
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    doc_text = DOC.read_text(encoding="utf-8")

    bundle = data.get("bundle") if isinstance(data.get("bundle"), dict) else {}
    if data.get("status") != "phase_4by_agent_replay_discovery_contract_bundle_no_runtime_change":
        blockers.append("status must be Phase 4BY discovery contract bundle without runtime change")
    if bundle.get("type") != "discovery_contract_bundle":
        blockers.append("bundle.type must be discovery_contract_bundle")
    if bundle.get("route_family") != AGENT_REPLAY or data.get("route_family") != AGENT_REPLAY:
        blockers.append("bundle and top-level route_family must be agent-replay")
    if int(bundle.get("estimated_pr_count_reduction_percent", 0)) < 40:
        blockers.append("bundle must estimate at least 40 percent PR count reduction")
    if AGENT_REPLAY not in manifest_text or AGENT_REPLAY not in backlog_text:
        blockers.append("agent-replay route must exist in manifest and backlog")
    if TASK_GROUPS not in manifest_text or TASK_GROUPS not in backlog_text:
        blockers.append("next task-groups route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("phase") != "phase_4bx_agent_runs_fixture_native_list_detail_runtime" or previous.get("merged_pr") != "#684" or previous.get("completed") is not True:
        blockers.append("previous_phase must record Phase 4BX merged as #684")

    if not REQUIRED_INCLUDED_STAGES <= _strings(data.get("included_stages")):
        blockers.append("included_stages missing bundled discovery steps")
    if not REQUIRED_EXCLUDED_STAGES <= _strings(data.get("excluded_stages")):
        blockers.append("excluded_stages missing unsafe boundaries")

    route_surface = data.get("route_surface_confirmation") if isinstance(data.get("route_surface_confirmation"), dict) else {}
    if route_surface.get("manifest_route_pattern") != AGENT_REPLAY:
        blockers.append("route_surface_confirmation.manifest_route_pattern must be agent-replay")
    if set(route_surface.get("manifest_methods") or []) != {"GET", "OPTIONS", "HEAD"}:
        blockers.append("manifest_methods must match GET/OPTIONS/HEAD")
    if set(route_surface.get("contract_methods_for_future_fixture_native") or []) != {"GET"}:
        blockers.append("future fixture/native contract must be GET only")
    included_routes = {
        (str(item.get("method")), str(item.get("path")), str(item.get("status")))
        for item in route_surface.get("included_routes", [])
        if isinstance(item, dict)
    }
    if ("GET", AGENT_REPLAY, "fixture_native_readonly_metadata_contract_planned") not in included_routes:
        blockers.append("included_routes must include GET replay metadata contract")
    if route_surface.get("delete_ready") is not False:
        blockers.append("route_surface_confirmation.delete_ready must be false")

    contract = data.get("fixture_native_contract") if isinstance(data.get("fixture_native_contract"), dict) else {}
    if contract.get("selected_subset") != "agent_replay_readonly_metadata":
        blockers.append("fixture_native_contract.selected_subset must be agent_replay_readonly_metadata")
    if contract.get("production_mode_returns_fixture_success") is not False:
        blockers.append("future production mode must not return fixture success")
    if not REQUIRED_RESPONSE_KEYS <= set(contract.get("required_response_keys") or []):
        blockers.append("fixture_native_contract.required_response_keys incomplete")
    if not REQUIRED_ROW_FIELDS <= set(contract.get("required_row_fields") or []):
        blockers.append("fixture_native_contract.required_row_fields incomplete")
    if not REQUIRED_DEFERRED_TABLES <= set(contract.get("related_tables_deferred") or []):
        blockers.append("fixture_native_contract.related_tables_deferred incomplete")
    seed_rows = contract.get("fixture_seed_rows") if isinstance(contract.get("fixture_seed_rows"), list) else []
    if not seed_rows or any(item.get("side_effects_enabled") is not False for item in seed_rows if isinstance(item, dict)):
        blockers.append("fixture seed rows must exist with side_effects_enabled false")

    safety = data.get("safety_guards") if isinstance(data.get("safety_guards"), dict) else {}
    for field in sorted(REQUIRED_SAFETY_TRUE):
        if safety.get(field) is not True:
            blockers.append(f"safety_guards.{field} must be true")
    for field in sorted(REQUIRED_AUTH_FALSE):
        if safety.get(field) is not False:
            blockers.append(f"safety_guards.{field} must be false")

    deferral = data.get("deferral_record") if isinstance(data.get("deferral_record"), dict) else {}
    if deferral.get("route_family") != AGENT_REPLAY or deferral.get("paused_by_pr") != "#685":
        blockers.append("deferral_record must pause agent-replay by #685")
    if deferral.get("owner_approval_required") is not True:
        blockers.append("deferral_record.owner_approval_required must be true")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != TASK_GROUPS or state_update.get("active_candidate") != TASK_GROUPS:
        blockers.append("phase_execution_state.active_candidate must move to task-groups for the next safe bundle")
    if state.get("last_merged_pr") != "#684" or state_update.get("last_merged_pr") != "#684":
        blockers.append("phase_execution_state.last_merged_pr must record #684")
    if state.get("last_attempted_action") != "phase_4by_agent_replay_discovery_contract_bundle":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4BY")
    if state.get("last_created_pr") != "#685":
        blockers.append("phase_execution_state.last_created_pr must be #685")
    if state.get("recommended_next_pr") != NEXT_BUNDLE:
        blockers.append("phase_execution_state.recommended_next_pr must be Phase 4CA")
    if set(state.get("next_allowed_actions") or []) != {NEXT_BUNDLE}:
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4CA")
    if COMPLETED_STEP not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4BY")

    paused_candidates = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == AGENT_REPLAY
        and item.get("status") == "discovery_contract_completed_replay_runtime_deferred"
        and item.get("paused_by_pr") == "#685"
        and item.get("owner_approval_required") is True
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include agent-replay runtime deferral")

    readiness = state.get("agent_replay_readiness") if isinstance(state.get("agent_replay_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_runtime_deferred",
        "discovery_contract_bundle_completed",
        "paused",
        "replay_execution_excluded",
        "run_creation_excluded",
        "run_execution_excluded",
        "orchestration_execution_excluded",
        "agent_output_generation_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"agent_replay_readiness.{field} must be true")
    if readiness.get("paused_by_pr") != "#685":
        blockers.append("agent_replay_readiness.paused_by_pr must be #685")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if readiness.get(field) is not False:
            blockers.append(f"agent_replay_readiness.{field} must be false")

    next_rec = data.get("next_bundle_recommendation") if isinstance(data.get("next_bundle_recommendation"), dict) else {}
    if next_rec.get("recommended_next_step") != NEXT_BUNDLE or next_rec.get("route_family") != TASK_GROUPS:
        blockers.append("next_bundle_recommendation must point to task-groups Phase 4CA")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "live_external_call_allowed"):
        if next_rec.get(field) is not False:
            blockers.append(f"next_bundle_recommendation.{field} must be false")

    for phrase in FORBIDDEN_DOC_CLAIMS:
        if phrase in doc_text.lower():
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(changed - ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4BY bundle: {unexpected}")
    protected = [
        path
        for path in sorted(changed)
        if path in PROTECTED_EXACT or any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES)
    ]
    if protected:
        blockers.append(f"Phase 4BY discovery bundle must not touch protected runtime/deploy files: {protected}")

    details["changed_files"] = sorted(changed)
    details["bundle_type"] = bundle.get("type")
    details["route_family"] = data.get("route_family")
    details["next_bundle"] = next_rec.get("recommended_next_step")
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "autopilot_deliverable": not blockers,
        "blockers": blockers,
        "warnings": warnings,
        "details": details,
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4BY Agent Replay Discovery Contract Bundle Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- autopilot_deliverable: {str(report['autopilot_deliverable']).lower()}",
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
