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

DOC = ROOT / "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

ROUTE = "/api/admin/automation-conversion/agent-outputs*"
REQUIRED_FIELDS = {
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
    "created_at",
}
REQUIRED_LIST_QUERY = {
    "page",
    "page_size",
    "request_id",
    "external_contact_id",
    "userid",
    "agent_code",
    "output_type",
    "applied_status",
    "min_confidence",
    "max_confidence",
    "has_error",
}
REQUIRED_LIST_RESPONSE_KEYS = {"ok", "source_status", "route_owner", "page", "page_size", "total", "rows", "filters", "side_effect_safety"}
REQUIRED_DETAIL_RESPONSE_KEYS = {"ok", "output", "run", "side_effect_safety"}
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
SIDE_EFFECT_FALSE_FIELDS = {
    "real_external_call_allowed",
    "export_job_creation_allowed",
    "file_download_allowed",
    "agent_run_execution_allowed",
    "llm_generation_allowed",
    "deepseek_adapter_allowed",
    "openclaw_call_allowed",
    "mcp_call_allowed",
    "workflow_execution_allowed",
    "timer_execution_allowed",
    "outbound_send_allowed",
    "production_data_allowed",
}
ALLOWED_CHANGED_FILES = {
    "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md",
    "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml",
    "docs/development/phase_4bi_agent_outputs_metadata_plan.md",
    "docs/development/phase_4bi_agent_outputs_metadata_plan.yaml",
    "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md",
    "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml",
    "docs/development/phase_execution_state.yaml",
    "tools/check_phase4bk_agent_outputs_fixture_native_contract_plan.py",
    "tools/check_phase4bi_agent_outputs_metadata_plan.py",
    "tools/check_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
    "tools/check_autonomous_development_loop.py",
    "tools/check_automerge_eligibility.py",
    "tools/run_codex_autopilot_tick.py",
    "tests/test_phase4bk_agent_outputs_fixture_native_contract_plan.py",
    "tests/test_phase4bi_agent_outputs_metadata_plan.py",
    "tests/test_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
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

    if data.get("status") != "phase_4bk_agent_outputs_fixture_native_contract_planning_no_runtime_change":
        blockers.append("status must be Phase 4BK agent outputs fixture native contract planning no runtime change")
    if data.get("route_family") != ROUTE:
        blockers.append("route_family must be agent-outputs wildcard")
    if ROUTE not in manifest_text or ROUTE not in backlog_text:
        blockers.append("agent-outputs route must exist in manifest and backlog")
    if data.get("current_runtime_owner") != "production_compat" or data.get("production_behavior") != "legacy_forward":
        blockers.append("production owner must remain production_compat legacy_forward")
    if data.get("legacy_fallback_retained") is not True or data.get("fixture_allowed_in_production") is not False:
        blockers.append("legacy fallback must be retained and fixture production use must be false")

    previous = data.get("previous_phase") if isinstance(data.get("previous_phase"), dict) else {}
    if previous.get("phase") != "phase_4bj_agent_outputs_schema_route_surface_confirmation" or previous.get("merged_pr") != "#667":
        blockers.append("previous_phase must record Phase 4BJ merged as #667")
    if previous.get("completed") is not True:
        blockers.append("previous_phase.completed must be true")

    route_scopes = {(item.get("method"), item.get("scope")) for item in data.get("planned_fixture_routes") or [] if isinstance(item, dict)}
    if route_scopes != {("GET", "fixture_local_metadata_list"), ("GET", "fixture_local_metadata_detail")}:
        blockers.append("planned_fixture_routes must be GET list/detail only")

    excluded_paths = {str(item.get("path")) for item in data.get("excluded_routes") or [] if isinstance(item, dict)}
    if not {
        "/api/admin/automation-conversion/agent-outputs/export",
        "/api/admin/automation-conversion/agent-outputs/export/{job_id}",
        "/api/admin/automation-conversion/agent-runs*",
        "/api/admin/automation-conversion/agent-replay",
        "/api/admin/automation-conversion/agent-orchestration*",
    } <= excluded_paths:
        blockers.append("excluded_routes must include export, file download, runs, replay, and orchestration")

    seed = data.get("fixture_seed") if isinstance(data.get("fixture_seed"), dict) else {}
    if seed.get("deterministic") is not True or seed.get("production_data_allowed") is not False:
        blockers.append("fixture_seed must be deterministic and forbid production data")
    if not {"phase4bk_output_reply_draft", "phase4bk_output_route_decision"} <= set(seed.get("output_ids") or []):
        blockers.append("fixture_seed.output_ids incomplete")
    if not REQUIRED_FIELDS <= set(seed.get("required_fields") or []):
        blockers.append("fixture_seed.required_fields incomplete")

    list_contract = data.get("list_contract") if isinstance(data.get("list_contract"), dict) else {}
    if not REQUIRED_LIST_QUERY <= set(list_contract.get("query") or []):
        blockers.append("list_contract.query incomplete")
    if not REQUIRED_LIST_RESPONSE_KEYS <= set(list_contract.get("response_keys") or []):
        blockers.append("list_contract.response_keys incomplete")
    if list_contract.get("ordering") != "created_at_desc_id_desc":
        blockers.append("list_contract.ordering must be created_at_desc_id_desc")
    if list_contract.get("export_rows_excluded") is not True:
        blockers.append("list_contract.export_rows_excluded must be true")

    detail_contract = data.get("detail_contract") if isinstance(data.get("detail_contract"), dict) else {}
    if "output_id" not in set(detail_contract.get("path_params") or []):
        blockers.append("detail_contract.path_params must include output_id")
    if not REQUIRED_DETAIL_RESPONSE_KEYS <= set(detail_contract.get("response_keys") or []):
        blockers.append("detail_contract.response_keys incomplete")
    if detail_contract.get("not_found_status") != 404:
        blockers.append("detail_contract.not_found_status must be 404")
    if detail_contract.get("missing_output_rejected_without_side_effect") is not True:
        blockers.append("detail_contract.missing_output_rejected_without_side_effect must be true")

    visibility = data.get("visibility_contract") if isinstance(data.get("visibility_contract"), dict) else {}
    for field in ("masked_visibility_required", "console_visibility_fixture_mode_allowed", "raw_output_not_production_evidence", "normalized_payload_not_production_evidence"):
        if visibility.get(field) is not True:
            blockers.append(f"visibility_contract.{field} must be true")
    if visibility.get("production_data_allowed") is not False:
        blockers.append("visibility_contract.production_data_allowed must be false")

    side_effect = data.get("side_effect_safety") if isinstance(data.get("side_effect_safety"), dict) else {}
    for field in SIDE_EFFECT_FALSE_FIELDS:
        if side_effect.get(field) is not False:
            blockers.append(f"side_effect_safety.{field} must be false")

    authorizations = data.get("authorizations") if isinstance(data.get("authorizations"), dict) else {}
    for field in sorted(AUTH_FALSE_FIELDS):
        if authorizations.get(field) is not False:
            blockers.append(f"authorizations.{field} must be false")

    state_update = data.get("phase_execution_state_update") if isinstance(data.get("phase_execution_state_update"), dict) else {}
    if state.get("active_candidate") != ROUTE:
        blockers.append("phase_execution_state.active_candidate must remain agent-outputs")
    if state.get("last_merged_pr") != "#667":
        blockers.append("phase_execution_state.last_merged_pr must record #667")
    if state.get("last_attempted_action") != "phase_4bk_agent_outputs_fixture_native_contract_planning":
        blockers.append("phase_execution_state.last_attempted_action must be Phase 4BK")
    if state.get("last_created_pr") != "#668":
        blockers.append("phase_execution_state.last_created_pr must be #668")
    if state.get("recommended_next_pr") != "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision":
        blockers.append("phase_execution_state.recommended_next_pr must be Phase 4BL")
    if set(state.get("next_allowed_actions") or []) != {"phase_4bl_agent_outputs_fixture_native_implementation_owner_decision"}:
        blockers.append("phase_execution_state.next_allowed_actions must be Phase 4BL")
    if state.get("owner_approval_required") is not True:
        blockers.append("phase_execution_state.owner_approval_required must be true after fixture/native contract planning")
    if state_update.get("phase_4bk_completed_step") not in set(state.get("completed_steps") or []):
        blockers.append("phase_execution_state.completed_steps must include Phase 4BK completed step")

    readiness = state.get("agent_outputs_readiness") if isinstance(state.get("agent_outputs_readiness"), dict) else {}
    for field in (
        "fixture_native_contract_planning_completed",
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
    ):
        if readiness.get(field) is not True:
            blockers.append(f"agent_outputs_readiness.{field} must be true")
    for field in ("runtime_implementation_ready", "production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready", "delete_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")

    rec = data.get("phase_4bl_recommendation") if isinstance(data.get("phase_4bl_recommendation"), dict) else {}
    if rec.get("recommended_next_step") != "agent_outputs_fixture_native_implementation_owner_decision":
        blockers.append("phase_4bl_recommendation must recommend owner decision before runtime implementation")
    for field in ("production_write_allowed", "production_route_switch_allowed", "fallback_removal_allowed", "production_write_canary_allowed"):
        if rec.get(field) is not False:
            blockers.append(f"phase_4bl_recommendation.{field} must be false")

    doc_text = DOC.read_text(encoding="utf-8").lower()
    for phrase in sorted(FORBIDDEN_DOC_CLAIMS):
        if phrase in doc_text:
            blockers.append(f"doc contains forbidden claim: {phrase}")

    changed, git_warnings = _changed_files()
    warnings.extend(git_warnings)
    unexpected = sorted(path for path in changed if path not in ALLOWED_CHANGED_FILES)
    if unexpected:
        blockers.append(f"unexpected changed files for Phase 4BK package: {unexpected}")
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
            "changed_files": sorted(changed),
        },
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4BK Agent Outputs Fixture Native Contract Planning Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- route_family: {report['details'].get('route_family')}",
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
