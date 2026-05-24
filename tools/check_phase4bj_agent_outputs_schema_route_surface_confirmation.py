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

DOC = ROOT / "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/agent-outputs*"
REQUIRED_PRODUCTION_COMPAT_PATTERNS = {
    "/api/admin/automation-conversion/agent-outputs",
    "/api/admin/automation-conversion/agent-outputs/wildcard_path",
}
REQUIRED_LEGACY_ROUTES = {
    ("GET", "/api/admin/automation-conversion/agent-outputs", "metadata_list_surface_only"),
    ("GET", "/api/admin/automation-conversion/agent-outputs/{output_id}", "metadata_detail_surface_only"),
    ("POST", "/api/admin/automation-conversion/agent-outputs/export", "export_job_creation_deferred"),
    ("GET", "/api/admin/automation-conversion/agent-outputs/export/{job_id}", "export_job_status_and_download_deferred"),
}
REQUIRED_READ_MODEL_COLUMNS = {
    "id",
    "output_id",
    "run_id",
    "request_id",
    "userid",
    "external_contact_id",
    "agent_code",
    "output_type",
    "rendered_output_text",
    "target_agent_code",
    "target_pool",
    "confidence",
    "reason",
    "need_human_review",
    "applied_status",
    "applied_at",
    "outcome_status",
    "outcome_value",
    "revision_of_output_id",
    "error_code",
    "error_message",
    "created_at",
}
REQUIRED_LIST_RESPONSE_KEYS = {"ok", "page", "page_size", "total", "rows"}
REQUIRED_DETAIL_RESPONSE_KEYS = {"ok", "output", "run"}
REQUIRED_RELATED_RUNTIME_TABLES = {
    "automation_agent_run",
    "automation_agent_output_export_job",
    "automation_agent_llm_call_log",
}
REQUIRED_FIRST_NATIVE_SUBSET = {
    "list_agent_outputs_metadata",
    "get_agent_output_metadata_detail",
}
REQUIRED_NEXT_REQUIREMENTS = {
    "fixture_contract_for_list_agent_outputs_metadata",
    "fixture_contract_for_get_agent_output_metadata_detail",
    "pagination_required",
    "filter_contract_required",
    "masked_visibility_required",
    "not_found_contract_required",
    "no_export_job_creation",
    "no_file_download",
    "no_agent_run_execution",
    "no_llm_generation",
    "no_external_calls",
}
REQUIRED_DEFERRED_SCOPE = {
    "export_job_creation",
    "export_job_status_lookup",
    "file_download",
    "agent_runs",
    "agent_replay",
    "agent_orchestration",
    "llm_generation",
    "deepseek_adapter",
    "openclaw_mcp_call",
    "workflow_execution",
    "timer_execution",
    "outbound_send",
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
    "export_job_creation_authorized",
    "file_download_authorized",
    "agent_run_execution_authorized",
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
    "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md",
    "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml",
    "docs/development/phase_4bi_agent_outputs_metadata_plan.md",
    "docs/development/phase_4bi_agent_outputs_metadata_plan.yaml",
    "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md",
    "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
    "tools/check_phase4bi_agent_outputs_metadata_plan.py",
    "tools/check_phase4bk_agent_outputs_fixture_native_contract_plan.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
    "tests/test_phase4bi_agent_outputs_metadata_plan.py",
    "tests/test_phase4bk_agent_outputs_fixture_native_contract_plan.py",
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


def _legacy_route_pairs(routes: list[dict[str, Any]]) -> set[tuple[str, str, str]]:
    return {
        (str(item.get("method")), str(item.get("path")), str(item.get("status")))
        for item in routes
        if isinstance(item, dict)
    }


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

    if data.get("status") != "phase_4bj_agent_outputs_schema_route_surface_confirmation_no_runtime_change":
        blockers.append("status must be Phase 4BJ agent outputs schema/route surface confirmation no runtime change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be agent-outputs wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("agent-outputs route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("phase") != "phase_4bi_agent_outputs_metadata_planning" or previous.get("merged_pr") != "#666":
        blockers.append("previous_phase must record Phase 4BI merged as #666")
    if previous.get("completed") is not True:
        blockers.append("previous_phase.completed must be true")

    surface = data.get("confirmed_route_surface") if isinstance(data.get("confirmed_route_surface"), dict) else {}
    if not REQUIRED_PRODUCTION_COMPAT_PATTERNS <= set(surface.get("production_compat_patterns") or []):
        blockers.append("confirmed_route_surface.production_compat_patterns incomplete")
    if not REQUIRED_LEGACY_ROUTES <= _legacy_route_pairs(surface.get("legacy_api_routes") or []):
        blockers.append("confirmed_route_surface.legacy_api_routes incomplete")

    schema = data.get("confirmed_schema_surface") if isinstance(data.get("confirmed_schema_surface"), dict) else {}
    if schema.get("metadata_table") != "automation_agent_output":
        blockers.append("metadata_table must be automation_agent_output")
    if not REQUIRED_READ_MODEL_COLUMNS <= set(schema.get("read_model_columns") or []):
        blockers.append("read_model_columns incomplete")
    response_keys = schema.get("legacy_response_keys") if isinstance(schema.get("legacy_response_keys"), dict) else {}
    if not REQUIRED_LIST_RESPONSE_KEYS <= set(response_keys.get("list") or []):
        blockers.append("legacy_response_keys.list incomplete")
    if not REQUIRED_DETAIL_RESPONSE_KEYS <= set(response_keys.get("detail") or []):
        blockers.append("legacy_response_keys.detail incomplete")
    if not REQUIRED_RELATED_RUNTIME_TABLES <= set(schema.get("related_runtime_tables_deferred") or []):
        blockers.append("related runtime/export tables must be deferred")
    relationships = schema.get("relationship_boundaries") if isinstance(schema.get("relationship_boundaries"), dict) else {}
    for field in (
        "agent_run_execution_excluded_from_metadata_subset",
        "export_job_tables_excluded_from_metadata_subset",
        "llm_call_log_excluded_from_metadata_subset",
    ):
        if relationships.get(field) is not True:
            blockers.append(f"relationship_boundaries.{field} must be true")

    boundary = data.get("native_contract_boundary") if isinstance(data.get("native_contract_boundary"), dict) else {}
    if not REQUIRED_FIRST_NATIVE_SUBSET <= set(boundary.get("first_native_subset") or []):
        blockers.append("first native subset must be agent-outputs metadata list/detail only")
    if not REQUIRED_NEXT_REQUIREMENTS <= set(boundary.get("next_contract_planning_requirements") or []):
        blockers.append("next_contract_planning_requirements incomplete")
    if not REQUIRED_DEFERRED_SCOPE <= set(boundary.get("deferred_to_separate_pr") or []):
        blockers.append("deferred_to_separate_pr incomplete")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != ROUTE:
        blockers.append("phase_execution_state.active_candidate must remain agent-outputs")
    if state.get("last_merged_pr") not in {"#666", "#667"}:
        blockers.append("phase_execution_state.last_merged_pr must record #666 or later Phase 4BK state #667")
    if state.get("last_attempted_action") not in {
        "phase_4bj_agent_outputs_schema_route_surface_confirmation",
        "phase_4bk_agent_outputs_fixture_native_contract_planning",
    }:
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4BJ or later Phase 4BK")
    if state.get("last_created_pr") not in {"#667", "#668"}:
        blockers.append("phase_execution_state.last_created_pr must be #667 or later Phase 4BK PR #668")
    if state.get("recommended_next_pr") not in {
        "phase_4bk_agent_outputs_fixture_native_contract_planning",
        "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision",
    }:
        blockers.append("phase_execution_state.recommended_next_pr must be Phase 4BK or later Phase 4BL")
    if set(state.get("next_allowed_actions") or []) not in (
        {"phase_4bk_agent_outputs_fixture_native_contract_planning"},
        {"phase_4bl_agent_outputs_fixture_native_implementation_owner_decision"},
    ):
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4BK or later Phase 4BL")
    if state.get("owner_approval_required") not in {False, True}:
        blockers.append("phase_execution_state.owner_approval_required must be boolean")
    if state_update.get("phase_4bj_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4BJ completed step")

    readiness = state.get("agent_outputs_readiness") if isinstance(state.get("agent_outputs_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "export_job_creation_excluded",
        "file_download_excluded",
        "agent_run_execution_excluded",
        "llm_generation_excluded",
        "external_call_excluded",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"agent_outputs_readiness.{field} must be true")
    for field in (
        "fixture_native_contract_planning_completed",
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
    ):
        if readiness.get(field) not in {False, True}:
            blockers.append(f"agent_outputs_readiness.{field} must be boolean")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")

    rec = data.get("phase_4bk_recommendation") if isinstance(data.get("phase_4bk_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "agent_outputs_fixture_native_contract_planning":
        blockers.append("phase_4bk_recommendation must recommend fixture/native contract planning")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4bk_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4BJ package: {unexpected}")
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
            "metadata_table": schema.get("metadata_table"),
            "changed_files": sorted(changed),
        },
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4BJ Agent Outputs Schema Route Surface Confirmation Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- route_family: {report['details'].get('route_family')}",
            f"- metadata_table: {report['details'].get('metadata_table')}",
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
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
