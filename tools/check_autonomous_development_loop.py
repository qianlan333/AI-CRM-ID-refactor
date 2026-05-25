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
    "agent_runs_readiness",
    "agent_replay_readiness",
    "work_package_policy",
    "implemented_runtime_slices",
    "guarded_disabled_runtime_slices",
    "repository_adapter_parity_slices",
    "staging_readiness_slices",
    "production_dry_run_readiness_slices",
}
ALLOWED_NEXT_ACTIONS = {
    "phase_5i_wecom_customer_contact_fake_stub_adapter_bundle",
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
    "phase_4bi_agent_outputs_metadata_planning_completed",
    "phase_4bj_agent_outputs_schema_route_surface_confirmation_completed",
    "phase_4bk_agent_outputs_fixture_native_contract_planning_completed",
    "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision_completed",
    "phase_4bm_agent_runs_metadata_planning_completed",
    "phase_4bn_agent_runs_schema_route_surface_confirmation_completed",
    "phase_4bo_agent_runs_fixture_native_contract_planning_completed",
    "phase_4bp_agent_runs_fixture_native_implementation_owner_decision_completed",
    "phase_4bq_agent_replay_metadata_planning_completed",
    "phase_4br_task_groups_fixture_native_list_create_runtime_completed",
    "phase_4bs_workflows_fixture_native_list_create_runtime_completed",
    "phase_4bt_workflow_nodes_fixture_native_list_create_runtime_completed",
    "phase_4bu_tasks_fixture_native_list_create_runtime_completed",
    "phase_4bv_agents_fixture_native_list_create_runtime_completed",
    "phase_4bw_agent_outputs_fixture_native_list_detail_runtime_completed",
    "phase_4bx_agent_runs_fixture_native_list_detail_runtime_completed",
    "phase_4by_agent_replay_discovery_contract_bundle_completed",
    "phase_4ca_task_groups_repository_adapter_parity_completed",
    "phase_4cb_workflows_repository_adapter_parity_completed",
    "phase_4cc_workflow_nodes_repository_adapter_parity_completed",
    "phase_4cd_tasks_repository_adapter_parity_completed",
    "phase_4ce_agents_repository_adapter_parity_completed",
    "phase_4cf_agent_outputs_repository_adapter_parity_completed",
    "phase_4cg_agent_runs_repository_adapter_parity_completed",
    "phase_4ch_task_groups_staging_readiness_completed",
    "phase_4ci_workflows_staging_readiness_completed",
    "phase_4cj_workflow_nodes_staging_readiness_completed",
    "phase_4ck_tasks_staging_readiness_completed",
    "phase_4cl_agents_staging_readiness_completed",
    "phase_4cm_agent_outputs_staging_readiness_completed",
    "phase_4cn_agent_runs_staging_readiness_completed",
    "phase_4co_task_groups_production_dry_run_readiness_completed",
    "phase_4cp_workflows_production_dry_run_readiness_completed",
    "phase_4cq_workflow_nodes_production_dry_run_readiness_completed",
    "phase_4cr_tasks_production_dry_run_readiness_completed",
    "phase_4cs_agent_runs_production_dry_run_readiness_completed",
    "phase_4ct_agent_outputs_production_dry_run_readiness_completed",
    "phase_4cu_internal_write_acceptance_review_completed",
    "phase_4cv_phase5_readiness_entry_completed",
    "phase_5a_wecom_tag_adapter_contract_completed",
    "phase_5b_wecom_tag_fake_stub_adapter_completed",
    "phase_5c_wecom_tag_live_adapter_behind_flag_completed",
    "phase_5d_wecom_tag_staging_live_canary_evidence_completed",
    "phase_5e_wecom_tag_production_canary_readiness_completed",
    "phase_5f_wecom_tag_production_live_canary_execution_completed",
    "phase_5g_wecom_tag_family_acceptance_completed",
    "phase_5h_wecom_customer_contact_adapter_contract_completed",
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
PHASE4_ALLOWED_RUNTIME_FILES = {
    "aicrm_next/automation_engine/api.py",
    "aicrm_next/automation_engine/application.py",
    "aicrm_next/automation_engine/dto.py",
    "aicrm_next/automation_engine/repo.py",
    "aicrm_next/automation_engine/task_group_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/workflow_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/workflow_node_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/task_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/agent_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/agent_output_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/agent_run_sqlalchemy_repository.py",
    "aicrm_next/automation_engine/task_groups.py",
    "aicrm_next/automation_engine/tasks.py",
    "aicrm_next/automation_engine/agents.py",
    "aicrm_next/automation_engine/agent_outputs.py",
    "aicrm_next/automation_engine/agent_runs.py",
    "aicrm_next/automation_engine/workflows.py",
    "aicrm_next/automation_engine/workflow_nodes.py",
    "aicrm_next/customer_tags/api.py",
    "aicrm_next/customer_tags/application.py",
    "aicrm_next/customer_tags/dto.py",
    "aicrm_next/customer_tags/wecom_tag_adapter.py",
    "aicrm_next/customer_tags/wecom_tag_contract.py",
    "aicrm_next/customer_tags/wecom_tag_live_adapter.py",
    "aicrm_next/integration_gateway/wecom_tag_live_gateway.py",
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

    if state.get("current_phase") != "phase_5_external_adapter":
        blockers.append("current_phase must be phase_5_external_adapter")
    if state.get("active_candidate") != "/wecom/external-contact/callback":
        blockers.append("active_candidate must select the Phase 5H WeCom customer contact callback contract candidate")
    if state.get("capability_owner") != "aicrm_next.integration_gateway":
        blockers.append("capability_owner must be aicrm_next.integration_gateway")
    if state.get("last_merged_pr") != "#718":
        blockers.append("last_merged_pr must record latest completed merged PR #718")

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
    if work_package_policy.get("selection_unit") != "compressed_bounded_bundle":
        blockers.append("work_package_policy.selection_unit must be compressed_bounded_bundle")
    if work_package_policy.get("target_duration_minutes_min") != 15:
        blockers.append("work_package_policy.target_duration_minutes_min must be 15")
    if work_package_policy.get("target_duration_minutes_max") != 20:
        blockers.append("work_package_policy.target_duration_minutes_max must be 20")
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
    if candidate not in {"phase_4_internal_write_aggregate", "phase_5_external_adapter_entry"} and candidate not in manifest_text:
        blockers.append("active_candidate not found in production_route_ownership_manifest.yaml")
    if candidate not in {"phase_4_internal_write_aggregate", "phase_5_external_adapter_entry"} and candidate not in backlog_text:
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
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_create_runtime_completed"
        and str(item.get("paused_by_pr", "")).strip() not in {"", "false"}
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record task-groups fixture/native list/create runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/task-groups*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#686"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record task-groups repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflows*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_create_runtime_completed"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record workflows fixture/native list/create runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflows*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#687"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record workflows repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflow-nodes*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_create_runtime_completed"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record workflow-nodes fixture/native list/create runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflow-nodes*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#688"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record workflow-nodes repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/tasks*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_create_runtime_completed"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record tasks fixture/native list/create runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/tasks*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#689"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record tasks repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agents*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_create_runtime_completed"
        and item.get("paused_by_pr") == "#681"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agents fixture/native list/create runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agents*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#690"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agents repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-outputs*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_detail_runtime_completed"
        and item.get("paused_by_pr") == "#683"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agent-outputs fixture/native list/detail runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-outputs*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#691"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agent-outputs repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-runs*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "fixture_native_list_detail_runtime_completed"
        and item.get("paused_by_pr") == "#684"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agent-runs fixture/native list/detail runtime completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-runs*"
        and item.get("owner_approval_required") is False
        and item.get("status") == "repository_adapter_parity_completed"
        and item.get("paused_by_pr") == "#692"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agent-runs repository adapter parity completion")
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-replay"
        and item.get("owner_approval_required") is True
        and item.get("status") == "discovery_contract_completed_replay_runtime_deferred"
        and item.get("paused_by_pr") == "#685"
        for item in paused_candidates
    ):
        blockers.append("paused_candidates must record agent-replay discovery contract completion and runtime deferral")

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
    if task_groups_readiness.get("fixture_native_implementation_requires_owner_decision") is not False:
        blockers.append("task_groups_readiness.fixture_native_implementation_requires_owner_decision must be false after safe fixture runtime")
    if task_groups_readiness.get("owner_decision_required") is not False:
        blockers.append("task_groups_readiness.owner_decision_required must be false after safe fixture runtime")
    if task_groups_readiness.get("fixture_native_list_create_runtime_completed") is not True:
        blockers.append("task_groups_readiness.fixture_native_list_create_runtime_completed must be true")
    if task_groups_readiness.get("production_guard_blocks_fixture_success") is not True:
        blockers.append("task_groups_readiness.production_guard_blocks_fixture_success must be true")
    for field in (
        "repository_adapter_parity_completed",
        "no_database_url_fallback",
        "default_backend_fixture_local",
        "test_db_parity_harness_completed",
        "idempotency_audit_rollback_scaffold_completed",
        "staging_readiness_bundle_completed",
        "staging_readiness_preflight_completed",
        "staging_evidence_gate_completed",
        "staging_blocked_evidence_output_completed",
    ):
        if task_groups_readiness.get(field) is not True:
            blockers.append(f"task_groups_readiness.{field} must be true")
    if task_groups_readiness.get("staging_database_url_flag") != "AICRM_TASK_GROUPS_STAGING_DATABASE_URL":
        blockers.append("task_groups_readiness.staging_database_url_flag must be AICRM_TASK_GROUPS_STAGING_DATABASE_URL")
    if task_groups_readiness.get("staging_backend_flag") != "AICRM_TASK_GROUPS_REPO_BACKEND":
        blockers.append("task_groups_readiness.staging_backend_flag must be AICRM_TASK_GROUPS_REPO_BACKEND")
    if task_groups_readiness.get("staging_approval_flag") != "AICRM_PHASE4CH_STAGING_SMOKE_APPROVED":
        blockers.append("task_groups_readiness.staging_approval_flag must be AICRM_PHASE4CH_STAGING_SMOKE_APPROVED")
    if task_groups_readiness.get("staging_write_approval_flag") != "AICRM_PHASE4CH_STAGING_WRITE_APPROVED":
        blockers.append("task_groups_readiness.staging_write_approval_flag must be AICRM_PHASE4CH_STAGING_WRITE_APPROVED")
    for field in ("staging_smoke_executed", "staging_write_executed", "staging_db_connection_attempted_by_default"):
        if task_groups_readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")
    staging_slices = state.get("staging_readiness_slices") if isinstance(state.get("staging_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/task-groups*"
        and item.get("slice") == "task_groups_staging_readiness_preflight"
        for item in staging_slices
    ):
        blockers.append("staging_readiness_slices must record task-groups staging readiness preflight")
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/task-groups*"
        and item.get("slice") == "task_groups_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record task-groups readonly dry-run readiness")
    if set(task_groups_readiness.get("implemented_runtime_slices") or []) != {
        "task_groups_fixture_local_list",
        "task_groups_fixture_local_metadata_create",
    }:
        blockers.append("task_groups_readiness.implemented_runtime_slices must record fixture local list/create")
    for field in (
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if task_groups_readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if task_groups_readiness.get(field) is not True:
            blockers.append(f"task_groups_readiness.{field} must be true")
    for field in ("production_readonly_dry_run_executed", "production_readonly_db_connection_attempted_by_default"):
        if task_groups_readiness.get(field) is not False:
            blockers.append(f"task_groups_readiness.{field} must be false")
    if task_groups_readiness.get("production_readonly_db_url_flag") != "AICRM_TASK_GROUPS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("task_groups_readiness.production_readonly_db_url_flag must be AICRM_TASK_GROUPS_READONLY_DRY_RUN_DATABASE_URL")
    if task_groups_readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CO_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("task_groups_readiness.production_readonly_approval_flag must be AICRM_PHASE4CO_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if task_groups_readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CO_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("task_groups_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CO_PRODUCTION_CONFIG_REVIEWED")

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
    if workflows_readiness.get("fixture_native_implementation_requires_owner_decision") is not False:
        blockers.append("workflows_readiness.fixture_native_implementation_requires_owner_decision must be false after safe fixture runtime")
    if workflows_readiness.get("owner_decision_required") is not False:
        blockers.append("workflows_readiness.owner_decision_required must be false after safe fixture runtime")
    if workflows_readiness.get("fixture_native_list_create_runtime_completed") is not True:
        blockers.append("workflows_readiness.fixture_native_list_create_runtime_completed must be true")
    if workflows_readiness.get("production_guard_blocks_fixture_success") is not True:
        blockers.append("workflows_readiness.production_guard_blocks_fixture_success must be true")
    for field in (
        "repository_adapter_parity_completed",
        "no_database_url_fallback",
        "default_backend_fixture_local",
        "test_db_parity_harness_completed",
        "idempotency_audit_rollback_scaffold_completed",
    ):
        if workflows_readiness.get(field) is not True:
            blockers.append(f"workflows_readiness.{field} must be true")
    if set(workflows_readiness.get("implemented_runtime_slices") or []) != {
        "workflows_fixture_local_list",
        "workflows_fixture_local_metadata_create",
    }:
        blockers.append("workflows_readiness.implemented_runtime_slices must record fixture local list/create")
    if workflows_readiness.get("paused") is not False:
        blockers.append("workflows_readiness.paused must be false after safe fixture runtime")
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
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflows*"
        and item.get("slice") == "workflows_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record workflows readonly dry-run readiness")
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if workflows_readiness.get(field) is not True:
            blockers.append(f"workflows_readiness.{field} must be true")
    for field in ("production_readonly_dry_run_executed", "production_readonly_db_connection_attempted_by_default"):
        if workflows_readiness.get(field) is not False:
            blockers.append(f"workflows_readiness.{field} must be false")
    if workflows_readiness.get("production_readonly_db_url_flag") != "AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("workflows_readiness.production_readonly_db_url_flag must be AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL")
    if workflows_readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("workflows_readiness.production_readonly_approval_flag must be AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if workflows_readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("workflows_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED")

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
    if workflow_nodes_readiness.get("fixture_native_implementation_requires_owner_decision") is not False:
        blockers.append("workflow_nodes_readiness.fixture_native_implementation_requires_owner_decision must be false after safe fixture runtime")
    if workflow_nodes_readiness.get("owner_decision_required") is not False:
        blockers.append("workflow_nodes_readiness.owner_decision_required must be false after safe fixture runtime")
    if workflow_nodes_readiness.get("fixture_native_list_create_runtime_completed") is not True:
        blockers.append("workflow_nodes_readiness.fixture_native_list_create_runtime_completed must be true")
    if workflow_nodes_readiness.get("production_guard_blocks_fixture_success") is not True:
        blockers.append("workflow_nodes_readiness.production_guard_blocks_fixture_success must be true")
    for field in (
        "repository_adapter_parity_completed",
        "no_database_url_fallback",
        "default_backend_fixture_local",
        "test_db_parity_harness_completed",
        "idempotency_audit_rollback_scaffold_completed",
    ):
        if workflow_nodes_readiness.get(field) is not True:
            blockers.append(f"workflow_nodes_readiness.{field} must be true")
    if set(workflow_nodes_readiness.get("implemented_runtime_slices") or []) != {
        "workflow_nodes_fixture_local_list",
        "workflow_nodes_fixture_local_metadata_create",
    }:
        blockers.append("workflow_nodes_readiness.implemented_runtime_slices must record fixture local list/create")
    if workflow_nodes_readiness.get("paused") is not False:
        blockers.append("workflow_nodes_readiness.paused must be false after safe fixture runtime")
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
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/workflow-nodes*"
        and item.get("slice") == "workflow_nodes_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record workflow-nodes readonly dry-run readiness")
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if workflow_nodes_readiness.get(field) is not True:
            blockers.append(f"workflow_nodes_readiness.{field} must be true")
    for field in ("production_readonly_dry_run_executed", "production_readonly_db_connection_attempted_by_default"):
        if workflow_nodes_readiness.get(field) is not False:
            blockers.append(f"workflow_nodes_readiness.{field} must be false")
    if workflow_nodes_readiness.get("production_readonly_db_url_flag") != "AICRM_WORKFLOW_NODES_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("workflow_nodes_readiness.production_readonly_db_url_flag must be AICRM_WORKFLOW_NODES_READONLY_DRY_RUN_DATABASE_URL")
    if workflow_nodes_readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CQ_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("workflow_nodes_readiness.production_readonly_approval_flag must be AICRM_PHASE4CQ_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if workflow_nodes_readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CQ_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("workflow_nodes_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CQ_PRODUCTION_CONFIG_REVIEWED")

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
        "fixture_native_list_create_runtime_completed",
        "production_guard_blocks_fixture_success",
    ):
        if tasks_readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
    if tasks_readiness.get("fixture_native_implementation_requires_owner_decision") is not False:
        blockers.append("tasks_readiness.fixture_native_implementation_requires_owner_decision must be false after safe fixture runtime")
    if tasks_readiness.get("owner_decision_required") is not False:
        blockers.append("tasks_readiness.owner_decision_required must be false after safe fixture runtime")
    if tasks_readiness.get("paused") is not False:
        blockers.append("tasks_readiness.paused must be false after safe fixture runtime")
    if set(tasks_readiness.get("implemented_runtime_slices") or []) != {
        "tasks_fixture_local_list",
        "tasks_fixture_local_metadata_create",
    }:
        blockers.append("tasks_readiness.implemented_runtime_slices must record fixture local list/create")
    if str(tasks_readiness.get("paused_by_pr", "")).strip() != "#680":
        blockers.append("tasks_readiness.paused_by_pr must be #680")
    for field in (
        "repository_adapter_parity_completed",
        "no_database_url_fallback",
        "default_backend_fixture_local",
        "test_db_parity_harness_completed",
        "idempotency_audit_rollback_scaffold_completed",
    ):
        if tasks_readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
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
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/tasks*"
        and item.get("slice") == "tasks_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record tasks readonly dry-run readiness")
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if tasks_readiness.get(field) is not True:
            blockers.append(f"tasks_readiness.{field} must be true")
    for field in ("production_readonly_dry_run_executed", "production_readonly_db_connection_attempted_by_default"):
        if tasks_readiness.get(field) is not False:
            blockers.append(f"tasks_readiness.{field} must be false")
    if tasks_readiness.get("production_readonly_db_url_flag") != "AICRM_TASKS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("tasks_readiness.production_readonly_db_url_flag must be AICRM_TASKS_READONLY_DRY_RUN_DATABASE_URL")
    if tasks_readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CR_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("tasks_readiness.production_readonly_approval_flag must be AICRM_PHASE4CR_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if tasks_readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CR_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("tasks_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CR_PRODUCTION_CONFIG_REVIEWED")

    agents_readiness = state.get("agents_readiness") if isinstance(state.get("agents_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_list_create_runtime_completed",
        "production_guard_blocks_fixture_success",
        "agent_run_execution_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
    ):
        if agents_readiness.get(field) is not True:
            blockers.append(f"agents_readiness.{field} must be true")
    for field in (
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "paused",
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if agents_readiness.get(field) is not False:
            blockers.append(f"agents_readiness.{field} must be false")
    if agents_readiness.get("paused_by_pr") != "#681":
        blockers.append("agents_readiness.paused_by_pr must be #681")
    if set(agents_readiness.get("implemented_runtime_slices") or []) != {
        "agents_fixture_local_list",
        "agents_fixture_local_metadata_create",
    }:
        blockers.append("agents_readiness.implemented_runtime_slices must record fixture local list/create")
    for field in (
        "repository_adapter_parity_completed",
        "no_database_url_fallback",
        "default_backend_fixture_local",
        "test_db_parity_harness_completed",
        "idempotency_audit_rollback_scaffold_completed",
        "staging_readiness_bundle_completed",
        "staging_readiness_preflight_completed",
        "staging_evidence_gate_completed",
        "staging_blocked_evidence_output_completed",
    ):
        if agents_readiness.get(field) is not True:
            blockers.append(f"agents_readiness.{field} must be true")
    if agents_readiness.get("staging_database_url_flag") != "AICRM_AGENTS_STAGING_DATABASE_URL":
        blockers.append("agents_readiness.staging_database_url_flag must be AICRM_AGENTS_STAGING_DATABASE_URL")
    if agents_readiness.get("staging_backend_flag") != "AICRM_AGENTS_REPO_BACKEND":
        blockers.append("agents_readiness.staging_backend_flag must be AICRM_AGENTS_REPO_BACKEND")
    if agents_readiness.get("staging_approval_flag") != "AICRM_PHASE4CL_STAGING_SMOKE_APPROVED":
        blockers.append("agents_readiness.staging_approval_flag must be AICRM_PHASE4CL_STAGING_SMOKE_APPROVED")
    if agents_readiness.get("staging_write_approval_flag") != "AICRM_PHASE4CL_STAGING_WRITE_APPROVED":
        blockers.append("agents_readiness.staging_write_approval_flag must be AICRM_PHASE4CL_STAGING_WRITE_APPROVED")
    for field in ("staging_smoke_executed", "staging_write_executed", "staging_db_connection_attempted_by_default"):
        if agents_readiness.get(field) is not False:
            blockers.append(f"agents_readiness.{field} must be false")

    agent_outputs_readiness = state.get("agent_outputs_readiness") if isinstance(state.get("agent_outputs_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_list_detail_runtime_completed",
        "repository_adapter_parity_completed",
        "no_database_url_fallback",
        "default_backend_fixture_local",
        "test_db_parity_harness_completed",
        "production_guard_blocks_fixture_success",
        "export_job_creation_excluded",
        "file_download_excluded",
        "agent_run_execution_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
        "staging_readiness_bundle_completed",
        "staging_readiness_preflight_completed",
        "staging_evidence_gate_completed",
        "staging_blocked_evidence_output_completed",
    ):
        if agent_outputs_readiness.get(field) is not True:
            blockers.append(f"agent_outputs_readiness.{field} must be true")
    if agent_outputs_readiness.get("staging_database_url_flag") != "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL":
        blockers.append("agent_outputs_readiness.staging_database_url_flag must be AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL")
    if agent_outputs_readiness.get("staging_backend_flag") != "AICRM_AGENT_OUTPUTS_REPO_BACKEND":
        blockers.append("agent_outputs_readiness.staging_backend_flag must be AICRM_AGENT_OUTPUTS_REPO_BACKEND")
    if agent_outputs_readiness.get("staging_approval_flag") != "AICRM_PHASE4CM_STAGING_SMOKE_APPROVED":
        blockers.append("agent_outputs_readiness.staging_approval_flag must be AICRM_PHASE4CM_STAGING_SMOKE_APPROVED")
    if agent_outputs_readiness.get("staging_write_approval_flag") != "AICRM_PHASE4CM_STAGING_WRITE_APPROVED":
        blockers.append("agent_outputs_readiness.staging_write_approval_flag must be AICRM_PHASE4CM_STAGING_WRITE_APPROVED")
    for field in ("staging_smoke_executed", "staging_write_executed", "staging_db_connection_attempted_by_default"):
        if agent_outputs_readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-outputs*"
        and item.get("slice") == "agent_outputs_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record agent-outputs readonly dry-run readiness")
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if agent_outputs_readiness.get(field) is not True:
            blockers.append(f"agent_outputs_readiness.{field} must be true")
    for field in ("production_readonly_dry_run_executed", "production_readonly_db_connection_attempted_by_default"):
        if agent_outputs_readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")
    if agent_outputs_readiness.get("production_readonly_db_url_flag") != "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("agent_outputs_readiness.production_readonly_db_url_flag must be AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL")
    if agent_outputs_readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("agent_outputs_readiness.production_readonly_approval_flag must be AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if agent_outputs_readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("agent_outputs_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED")
    if agent_outputs_readiness.get("idempotency_audit_rollback_scaffold_completed") is not False:
        blockers.append("agent_outputs_readiness.idempotency_audit_rollback_scaffold_completed must be false for read/detail-only scope")
    if agent_outputs_readiness.get("paused_by_pr") != "#683":
        blockers.append("agent_outputs_readiness.paused_by_pr must be #683")
    if set(agent_outputs_readiness.get("implemented_runtime_slices") or []) != {
        "agent_outputs_fixture_local_list",
        "agent_outputs_fixture_local_detail",
    }:
        blockers.append("agent_outputs_readiness.implemented_runtime_slices must record fixture local list/detail")
    for field in (
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "paused",
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if agent_outputs_readiness.get(field) is not False:
            blockers.append(f"agent_outputs_readiness.{field} must be false")

    agent_runs_readiness = state.get("agent_runs_readiness") if isinstance(state.get("agent_runs_readiness"), dict) else {}
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_list_detail_runtime_completed",
        "production_guard_blocks_fixture_success",
        "run_creation_excluded",
        "run_execution_excluded",
        "replay_execution_excluded",
        "orchestration_execution_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
    ):
        if agent_runs_readiness.get(field) is not True:
            blockers.append(f"agent_runs_readiness.{field} must be true")
    if agent_runs_readiness.get("paused_by_pr") != "#684":
        blockers.append("agent_runs_readiness.paused_by_pr must be #684")
    if set(agent_runs_readiness.get("implemented_runtime_slices") or []) != {
        "agent_runs_fixture_local_list",
        "agent_runs_fixture_local_detail",
    }:
        blockers.append("agent_runs_readiness.implemented_runtime_slices must record fixture local list/detail")
    if agent_runs_readiness.get("repository_adapter_backend_flag") != "AICRM_AGENT_RUNS_REPO_BACKEND":
        blockers.append("agent_runs_readiness.repository_adapter_backend_flag must be AICRM_AGENT_RUNS_REPO_BACKEND")
    if agent_runs_readiness.get("repository_adapter_test_db_url_flag") != "AICRM_AGENT_RUNS_TEST_DATABASE_URL":
        blockers.append("agent_runs_readiness.repository_adapter_test_db_url_flag must be AICRM_AGENT_RUNS_TEST_DATABASE_URL")
    if agent_runs_readiness.get("repository_adapter_staging_db_url_flag") != "AICRM_AGENT_RUNS_STAGING_DATABASE_URL":
        blockers.append("agent_runs_readiness.repository_adapter_staging_db_url_flag must be AICRM_AGENT_RUNS_STAGING_DATABASE_URL")
    if agent_runs_readiness.get("idempotency_audit_rollback_scaffold_completed") is not False:
        blockers.append("agent_runs_readiness.idempotency_audit_rollback_scaffold_completed must be false for read/detail-only scope")
    for field in (
        "staging_readiness_bundle_completed",
        "staging_readiness_preflight_completed",
        "staging_evidence_gate_completed",
        "staging_blocked_evidence_output_completed",
    ):
        if agent_runs_readiness.get(field) is not True:
            blockers.append(f"agent_runs_readiness.{field} must be true")
    if agent_runs_readiness.get("staging_database_url_flag") != "AICRM_AGENT_RUNS_STAGING_DATABASE_URL":
        blockers.append("agent_runs_readiness.staging_database_url_flag must be AICRM_AGENT_RUNS_STAGING_DATABASE_URL")
    if agent_runs_readiness.get("staging_backend_flag") != "AICRM_AGENT_RUNS_REPO_BACKEND":
        blockers.append("agent_runs_readiness.staging_backend_flag must be AICRM_AGENT_RUNS_REPO_BACKEND")
    if agent_runs_readiness.get("staging_approval_flag") != "AICRM_PHASE4CN_STAGING_SMOKE_APPROVED":
        blockers.append("agent_runs_readiness.staging_approval_flag must be AICRM_PHASE4CN_STAGING_SMOKE_APPROVED")
    if agent_runs_readiness.get("staging_write_approval_flag") != "AICRM_PHASE4CN_STAGING_WRITE_APPROVED":
        blockers.append("agent_runs_readiness.staging_write_approval_flag must be AICRM_PHASE4CN_STAGING_WRITE_APPROVED")
    for field in ("staging_smoke_executed", "staging_write_executed", "staging_db_connection_attempted_by_default"):
        if agent_runs_readiness.get(field) is not False:
            blockers.append(f"agent_runs_readiness.{field} must be false")
    for field in (
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
        "paused",
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if agent_runs_readiness.get(field) is not False:
            blockers.append(f"agent_runs_readiness.{field} must be false")
    dry_run_slices = state.get("production_dry_run_readiness_slices") if isinstance(state.get("production_dry_run_readiness_slices"), list) else []
    if not any(
        isinstance(item, dict)
        and item.get("route_family") == "/api/admin/automation-conversion/agent-runs*"
        and item.get("slice") == "agent_runs_production_readonly_dry_run_readiness"
        and item.get("scope") == "blocked_by_default_readonly_dry_run_evidence"
        for item in dry_run_slices
    ):
        blockers.append("production_dry_run_readiness_slices must record agent-runs readonly dry-run readiness")
    for field in (
        "production_dry_run_readiness_bundle_completed",
        "production_readonly_dry_run_runner_completed",
        "production_readonly_evidence_gate_completed",
        "production_readonly_blocked_evidence_output_completed",
    ):
        if agent_runs_readiness.get(field) is not True:
            blockers.append(f"agent_runs_readiness.{field} must be true")
    for field in ("production_readonly_dry_run_executed", "production_readonly_db_connection_attempted_by_default"):
        if agent_runs_readiness.get(field) is not False:
            blockers.append(f"agent_runs_readiness.{field} must be false")
    if agent_runs_readiness.get("production_readonly_db_url_flag") != "AICRM_AGENT_RUNS_READONLY_DRY_RUN_DATABASE_URL":
        blockers.append("agent_runs_readiness.production_readonly_db_url_flag must be AICRM_AGENT_RUNS_READONLY_DRY_RUN_DATABASE_URL")
    if agent_runs_readiness.get("production_readonly_approval_flag") != "AICRM_PHASE4CS_PRODUCTION_READONLY_DRY_RUN_APPROVED":
        blockers.append("agent_runs_readiness.production_readonly_approval_flag must be AICRM_PHASE4CS_PRODUCTION_READONLY_DRY_RUN_APPROVED")
    if agent_runs_readiness.get("production_readonly_config_review_flag") != "AICRM_PHASE4CS_PRODUCTION_CONFIG_REVIEWED":
        blockers.append("agent_runs_readiness.production_readonly_config_review_flag must be AICRM_PHASE4CS_PRODUCTION_CONFIG_REVIEWED")

    agent_replay_readiness = state.get("agent_replay_readiness") if isinstance(state.get("agent_replay_readiness"), dict) else {}
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
    ):
        if agent_replay_readiness.get(field) is not True:
            blockers.append(f"agent_replay_readiness.{field} must be true")
    if agent_replay_readiness.get("paused_by_pr") != "#685":
        blockers.append("agent_replay_readiness.paused_by_pr must be #685")
    for field in (
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
    ):
        if agent_replay_readiness.get(field) is not True:
            blockers.append(f"agent_replay_readiness.{field} must be true after replay runtime deferral")
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        if agent_replay_readiness.get(field) is not False:
            blockers.append(f"agent_replay_readiness.{field} must be false")

    changed = _changed_files()
    runtime_changed = [
        path
        for path in sorted(changed)
        if path not in PHASE4_ALLOWED_RUNTIME_FILES
        and (path.startswith("aicrm_next/")
        or path.startswith("wecom_ability_service/")
        or path.startswith("migrations/")
        or path.startswith("deploy/")
        or path.startswith("systemd/")
        or path.startswith("nginx/")
        or path in {"app.py", "legacy_flask_app.py"})
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
