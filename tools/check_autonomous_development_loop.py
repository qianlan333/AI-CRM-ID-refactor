#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/autonomous_development_loop.md"
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
MANIFEST = ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml"
BACKLOG = ROOT / "docs/development/legacy_replacement_backlog.yaml"

REQUIRED_STATE_FIELDS = {
    "version",
    "status",
    "autopilot",
    "current_phase",
    "active_candidate",
    "capability_owner",
    "last_merged_pr",
    "completed_steps",
    "next_allowed_actions",
    "forbidden_without_owner_approval",
    "action_templates_readiness",
    "paused_candidates",
    "task_groups_readiness",
    "workflows_readiness",
    "workflow_nodes_readiness",
    "tasks_readiness",
    "agents_readiness",
    "agent_outputs_readiness",
    "work_package_policy",
}
ALLOWED_NEXT_ACTIONS = {
    "phase_4bi_agent_outputs_metadata_planning",
}
REQUIRED_COMPLETED_STEPS = {
    "phase_4al_staging_execution_readiness_gate_completed",
    "action_templates_staging_approval_config_closure_package_created",
    "action_templates_staging_owner_decision_package_created",
    "phase_4an_task_groups_native_contract_planning_completed",
    "phase_4ao_task_groups_schema_route_surface_confirmation_completed",
    "phase_4ap_task_groups_fixture_native_contract_planning_completed",
    "phase_4aq_task_groups_fixture_native_implementation_owner_decision_completed",
    "phase_4ar_workflows_metadata_planning_completed",
    "phase_4as_workflows_schema_route_surface_confirmation_completed",
    "phase_4at_workflows_fixture_native_contract_planning_completed",
    "phase_4au_workflows_fixture_native_implementation_owner_decision_completed",
    "phase_4av_workflow_nodes_metadata_planning_completed",
    "phase_4aw_workflow_nodes_schema_route_surface_confirmation_completed",
    "phase_4ax_workflow_nodes_fixture_native_contract_planning_completed",
    "phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision_completed",
    "phase_4az_next_internal_write_candidate_selection_completed",
    "phase_4ba_tasks_metadata_planning_completed",
    "phase_4bb_tasks_schema_route_surface_confirmation_completed",
    "phase_4bc_tasks_fixture_native_contract_planning_completed",
    "phase_4bd_tasks_fixture_native_implementation_owner_decision_completed",
    "phase_4be_agents_metadata_planning_completed",
    "phase_4bf_agents_schema_route_surface_confirmation_completed",
    "phase_4bg_agents_fixture_native_contract_planning_completed",
    "phase_4bh_agents_fixture_native_implementation_owner_decision_completed",
}
REQUIRED_FORBIDDEN = {
    "production owner switch",
    "fallback removal",
    "production write",
    "real external call",
    "timer",
    "outbound send",
    "deploy config",
    "destructive migration",
    "delete_ready",
    "canary approval",
}
STOP_IDS = {
    "production_owner_switch",
    "fallback_removal",
    "production_write",
    "real_external_call",
    "timer_or_execution",
    "outbound_send",
    "deploy_config",
    "destructive_migration",
    "delete_ready",
    "canary_approval",
}
REQUIRED_WORK_PACKAGE_POLICY_TRUE = {
    "state_only_pr_requires_explanation",
    "avoid_repeated_blocked_evidence_review",
    "low_risk_admin_merge_allowed",
    "admin_merge_requires_eligible_true",
    "admin_merge_requires_required_checks_green",
}


def _parse_scalar(value: str) -> Any:
    value = value.strip()
    if value in {"true", "false"}:
        return value == "true"
    if value == "[]":
        return []
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value


def _strip_yaml_comments(line: str) -> str:
    in_single = False
    in_double = False
    for index, char in enumerate(line):
        if char == "'" and not in_double:
            in_single = not in_single
        elif char == '"' and not in_single:
            in_double = not in_double
        elif char == "#" and not in_single and not in_double:
            return line[:index].rstrip()
    return line.rstrip()


def _yaml_lines(text: str) -> list[tuple[int, str]]:
    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        stripped = _strip_yaml_comments(raw)
        if stripped.strip():
            lines.append((len(stripped) - len(stripped.lstrip(" ")), stripped.strip()))
    return lines


def _parse_yaml_block(lines: list[tuple[int, str]], index: int, indent: int) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, current_text = lines[index]
    if current_indent < indent:
        return {}, index
    if current_text.startswith("- "):
        result: list[Any] = []
        while index < len(lines):
            line_indent, text = lines[index]
            if line_indent != indent or not text.startswith("- "):
                break
            item_text = text[2:].strip()
            index += 1
            if not item_text:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                result.append(value)
                continue
            if ":" not in item_text:
                result.append(_parse_scalar(item_text))
                continue
            key, raw_value = item_text.split(":", 1)
            item: dict[str, Any] = {}
            raw_value = raw_value.strip()
            if raw_value:
                item[key.strip()] = _parse_scalar(raw_value)
            else:
                value, index = _parse_yaml_block(lines, index, indent + 2)
                item[key.strip()] = value
            while index < len(lines) and lines[index][0] > indent:
                nested_value, index = _parse_yaml_block(lines, index, indent + 2)
                if isinstance(nested_value, dict):
                    item.update(nested_value)
            result.append(item)
        return result, index
    result: dict[str, Any] = {}
    while index < len(lines):
        line_indent, text = lines[index]
        if line_indent != indent or text.startswith("- "):
            break
        if ":" not in text:
            index += 1
            continue
        key, raw_value = text.split(":", 1)
        raw_value = raw_value.strip()
        index += 1
        if raw_value:
            result[key.strip()] = _parse_scalar(raw_value)
        else:
            value, index = _parse_yaml_block(lines, index, indent + 2)
            result[key.strip()] = value
    return result, index


def _load_yaml_without_dependency(path: Path) -> dict[str, Any]:
    data, _ = _parse_yaml_block(_yaml_lines(path.read_text(encoding="utf-8")), 0, 0)
    return data if isinstance(data, dict) else {}


def load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore

        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except ModuleNotFoundError:
        return _load_yaml_without_dependency(path)


def _as_list(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _as_strings(value: Any) -> set[str]:
    return {str(item).strip() for item in _as_list(value)}


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files() -> set[str]:
    changed: set[str] = set()
    for args in (
        ["diff", "--name-only", "origin/main...HEAD"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
        ["ls-files", "--others", "--exclude-standard"],
    ):
        ok, stdout, _ = _run_git(args)
        if ok:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed


def build_report() -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    details: dict[str, Any] = {}

    for path in (DOC, STATE, STOP, MANIFEST, BACKLOG):
        if not path.exists():
            blockers.append(f"missing required file: {path.relative_to(ROOT)}")

    if blockers:
        return {"overall": "FAIL", "ok": False, "blockers": blockers, "warnings": warnings, "details": details}

    state = load_yaml(STATE)
    stop = load_yaml(STOP)
    details["state"] = {
        "current_phase": state.get("current_phase"),
        "active_candidate": state.get("active_candidate"),
        "capability_owner": state.get("capability_owner"),
        "last_merged_pr": state.get("last_merged_pr"),
    }

    missing_state_fields = sorted(REQUIRED_STATE_FIELDS - set(state))
    if missing_state_fields:
        blockers.append(f"phase_execution_state missing fields: {missing_state_fields}")

    if state.get("current_phase") != "phase_4_internal_write":
        blockers.append("current_phase must be phase_4_internal_write")
    if state.get("active_candidate") != "/api/admin/automation-conversion/agent-outputs*":
        blockers.append("active_candidate must advance to /api/admin/automation-conversion/agent-outputs* after agents pause")
    if state.get("capability_owner") != "aicrm_next.automation_engine":
        blockers.append("capability_owner must be aicrm_next.automation_engine")
    if state.get("last_merged_pr") != "#664":
        blockers.append("last_merged_pr must record latest completed autopilot PR #664")

    completed = _as_strings(state.get("completed_steps"))
    missing_completed = sorted(REQUIRED_COMPLETED_STEPS - completed)
    if missing_completed:
        blockers.append(f"completed_steps missing required Phase 4AL asset: {missing_completed}")

    next_allowed = _as_strings(state.get("next_allowed_actions"))
    if next_allowed != ALLOWED_NEXT_ACTIONS:
        blockers.append(f"next_allowed_actions must be exactly {sorted(ALLOWED_NEXT_ACTIONS)}")

    forbidden = {item.lower() for item in _as_strings(state.get("forbidden_without_owner_approval"))}
    missing_forbidden = sorted(REQUIRED_FORBIDDEN - forbidden)
    if missing_forbidden:
        blockers.append(f"forbidden_without_owner_approval missing high-risk actions: {missing_forbidden}")

    work_package_policy = state.get("work_package_policy") if isinstance(state.get("work_package_policy"), dict) else {}
    if work_package_policy.get("selection_unit") != "bounded_low_risk_work_package":
        blockers.append("work_package_policy.selection_unit must be bounded_low_risk_work_package")
    if work_package_policy.get("target_duration_minutes_min") != 10:
        blockers.append("work_package_policy.target_duration_minutes_min must be 10")
    if work_package_policy.get("target_duration_minutes_max") != 13:
        blockers.append("work_package_policy.target_duration_minutes_max must be 13")
    for field in sorted(REQUIRED_WORK_PACKAGE_POLICY_TRUE):
        if work_package_policy.get(field) is not True:
            blockers.append(f"work_package_policy.{field} must be true")
    if work_package_policy.get("admin_merge_for_owner_decision_package_allowed") is not False:
        blockers.append("work_package_policy.admin_merge_for_owner_decision_package_allowed must be false")

    stop_conditions = _as_list(stop.get("high_risk_stop_conditions"))
    stop_ids = {str(item.get("id")) for item in stop_conditions if isinstance(item, dict)}
    missing_stop_ids = sorted(STOP_IDS - stop_ids)
    if missing_stop_ids:
        blockers.append(f"autonomous_stop_conditions missing stop ids: {missing_stop_ids}")

    stop_terms: set[str] = set()
    for item in stop_conditions:
        if isinstance(item, dict):
            stop_terms.update(str(term).lower() for term in _as_list(item.get("terms")))
    for action in next_allowed:
        normalized = action.replace("_", " ").lower()
        if any(term and term in normalized for term in stop_terms):
            blockers.append(f"next_allowed_action contains stop condition term: {action}")

    candidate = str(state.get("active_candidate", ""))
    manifest_text = MANIFEST.read_text(encoding="utf-8")
    backlog_text = BACKLOG.read_text(encoding="utf-8")
    if candidate not in manifest_text:
        blockers.append("active_candidate not found in production_route_ownership_manifest.yaml")
    if candidate not in backlog_text:
        blockers.append("active_candidate not found in legacy_replacement_backlog.yaml")

    readiness = state.get("action_templates_readiness") if isinstance(state.get("action_templates_readiness"), dict) else {}
    for field in ("production_owner_switch_ready", "production_write_ready", "fallback_removal_ready", "production_repository_route_enablement_ready"):
        if readiness.get(field) is not False:
            blockers.append(f"action_templates_readiness must not declare {field}")
    if readiness.get("paused") is not True:
        blockers.append("action_templates_readiness.paused must be true after owner decision package #644")
    if readiness.get("paused_by_pr") != "#644":
        blockers.append("action_templates_readiness.paused_by_pr must be #644")
    if readiness.get("owner_decision_required") is not True:
        blockers.append("action_templates_readiness.owner_decision_required must be true")

    paused_candidates = state.get("paused_candidates") if isinstance(state.get("paused_candidates"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/action-templates*"
        and item.get("paused_by_pr") == "#644"
        and item.get("owner_approval_required") is True
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include action-templates awaiting owner decision from #644")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/task-groups*"
        and item.get("owner_approval_required") is True
        and str(item.get("paused_by_pr", "")).strip() not in {"", "false"}
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include task-groups awaiting fixture/native runtime owner decision")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflows*"
        and item.get("owner_approval_required") is True
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include workflows awaiting fixture/native runtime owner decision")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflow-nodes*"
        and item.get("owner_approval_required") is True
        and str(item.get("paused_by_pr", "")).strip() not in {"", "false"}
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include workflow-nodes awaiting fixture/native runtime owner decision")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/tasks*"
        and item.get("owner_approval_required") is True
        and str(item.get("paused_by_pr", "")).strip() not in {"", "false"}
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include tasks awaiting fixture/native runtime owner decision")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agents*"
        and item.get("owner_approval_required") is True
        and str(item.get("paused_by_pr", "")).strip() not in {"", "false"}
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must include agents awaiting fixture/native runtime owner decision")

    task_groups_readiness = state.get("task_groups_readiness") if isinstance(state.get("task_groups_readiness"), dict) else {}
    if task_groups_readiness.get("native_contract_planning_started") is not True:
        blockers.append("task_groups_readiness.native_contract_planning_started must be true")
    if task_groups_readiness.get("native_contract_planning_completed") is not True:
        blockers.append("task_groups_readiness.native_contract_planning_completed must be true")
    if task_groups_readiness.get("schema_route_surface_confirmed") is not True:
        blockers.append("task_groups_readiness.schema_route_surface_confirmed must be true")
    if task_groups_readiness.get("fixture_native_contract_planning_ready") is not True:
        blockers.append("task_groups_readiness.fixture_native_contract_planning_ready must be true")
    if task_groups_readiness.get("fixture_native_contract_planning_completed") is not True:
        blockers.append("task_groups_readiness.fixture_native_contract_planning_completed must be true")
    if task_groups_readiness.get("fixture_native_implementation_requires_owner_decision") is not True:
        blockers.append("task_groups_readiness.fixture_native_implementation_requires_owner_decision must be true")
    for field in (
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if task_groups_readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")

    workflows_readiness = state.get("workflows_readiness") if isinstance(state.get("workflows_readiness"), dict) else {}
    if workflows_readiness.get("metadata_planning_ready") is not True:
        blockers.append("workflows_readiness.metadata_planning_ready must be true")
    if workflows_readiness.get("metadata_planning_completed") is not True:
        blockers.append("workflows_readiness.metadata_planning_completed must be true")
    if workflows_readiness.get("schema_route_surface_confirmation_ready") is not True:
        blockers.append("workflows_readiness.schema_route_surface_confirmation_ready must be true")
    if workflows_readiness.get("schema_route_surface_confirmed") is not True:
        blockers.append("workflows_readiness.schema_route_surface_confirmed must be true")
    if workflows_readiness.get("fixture_native_contract_planning_ready") is not True:
        blockers.append("workflows_readiness.fixture_native_contract_planning_ready must be true")
    if workflows_readiness.get("fixture_native_contract_planning_completed") is not True:
        blockers.append("workflows_readiness.fixture_native_contract_planning_completed must be true")
    if workflows_readiness.get("fixture_native_implementation_requires_owner_decision") is not True:
        blockers.append("workflows_readiness.fixture_native_implementation_requires_owner_decision must be true")
    if workflows_readiness.get("owner_decision_required") is not True:
        blockers.append("workflows_readiness.owner_decision_required must be true")
    if workflows_readiness.get("paused") is not True:
        blockers.append("workflows_readiness.paused must be true")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if workflows_readiness.get(field) is not False:
            blockers.append(f"workflows_readiness.{field} must be false")

    workflow_nodes_readiness = state.get("workflow_nodes_readiness") if isinstance(state.get("workflow_nodes_readiness"), dict) else {}
    if workflow_nodes_readiness.get("metadata_planning_ready") is not True:
        blockers.append("workflow_nodes_readiness.metadata_planning_ready must be true")
    if workflow_nodes_readiness.get("metadata_planning_completed") is not True:
        blockers.append("workflow_nodes_readiness.metadata_planning_completed must be true")
    if workflow_nodes_readiness.get("schema_route_surface_confirmation_ready") is not True:
        blockers.append("workflow_nodes_readiness.schema_route_surface_confirmation_ready must be true")
    if workflow_nodes_readiness.get("schema_route_surface_confirmed") is not True:
        blockers.append("workflow_nodes_readiness.schema_route_surface_confirmed must be true")
    if workflow_nodes_readiness.get("fixture_native_contract_planning_ready") is not True:
        blockers.append("workflow_nodes_readiness.fixture_native_contract_planning_ready must be true")
    if workflow_nodes_readiness.get("fixture_native_contract_planning_completed") is not True:
        blockers.append("workflow_nodes_readiness.fixture_native_contract_planning_completed must be true")
    if workflow_nodes_readiness.get("fixture_native_implementation_requires_owner_decision") is not True:
        blockers.append("workflow_nodes_readiness.fixture_native_implementation_requires_owner_decision must be true")
    if workflow_nodes_readiness.get("owner_decision_required") is not True:
        blockers.append("workflow_nodes_readiness.owner_decision_required must be true")
    if workflow_nodes_readiness.get("paused") is not True:
        blockers.append("workflow_nodes_readiness.paused must be true")
    if not str(workflow_nodes_readiness.get("paused_by_pr", "")).strip():
        blockers.append("workflow_nodes_readiness.paused_by_pr must be recorded or pending")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if workflow_nodes_readiness.get(field) is not False:
            blockers.append(f"workflow_nodes_readiness.{field} must be false")

    tasks_readiness = state.get("tasks_readiness") if isinstance(state.get("tasks_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "run_due_excluded",
        "task_execution_excluded",
        "workflow_execution_excluded",
        "timer_execution_excluded",
        "outbound_send_excluded",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "paused",
    ):
        if tasks_readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
    if not str(tasks_readiness.get("paused_by_pr", "")).strip():
        blockers.append("tasks_readiness.paused_by_pr must be recorded or pending")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if tasks_readiness.get(field) is not False:
            blockers.append(f"tasks_readiness.{field} must be false")

    agents_readiness = state.get("agents_readiness") if isinstance(state.get("agents_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "paused",
        "agent_run_execution_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
    ):
        if agents_readiness.get(field) is not True:
            blockers.append(f"agents_readiness.{field} must be true")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if agents_readiness.get(field) is not False:
            blockers.append(f"agents_readiness.{field} must be false")
    if agents_readiness.get("paused_by_pr") != "#665":
        blockers.append("agents_readiness.paused_by_pr must be #665")

    agent_outputs_readiness = state.get("agent_outputs_readiness") if isinstance(state.get("agent_outputs_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "export_job_creation_excluded",
        "file_download_excluded",
        "agent_run_execution_excluded",
        "llm_generation_excluded",
        "external_call_excluded",
    ):
        if agent_outputs_readiness.get(field) is not True:
            blockers.append(f"agent_outputs_readiness.{field} must be true")
    for field in (
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
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
        if agent_outputs_readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")

    changed = _changed_files()
    runtime_changed = [
        path
        for path in sorted(changed)
        if path.startswith("aicrm_next/")
        or path.startswith("wecom_ability_service/")
        or path.startswith("migrations/")
        or path.startswith("deploy/")
        or path.startswith("systemd/")
        or path.startswith("nginx/")
        or path in {"app.py", "legacy_flask_app.py"}
    ]
    if runtime_changed:
        blockers.append(f"autonomous loop PR must not touch runtime/protected files: {runtime_changed}")

    details["next_allowed_actions"] = sorted(next_allowed)
    details["forbidden_without_owner_approval"] = sorted(forbidden)
    details["work_package_policy"] = work_package_policy
    details["changed_files"] = sorted(changed)
    return {"overall": "PASS" if not blockers else "FAIL", "ok": not blockers, "blockers": blockers, "warnings": warnings, "details": details}


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Autonomous Development Loop Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
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
