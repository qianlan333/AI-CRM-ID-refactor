#!/usr/bin/env python3
from __future__ import annotations

import argparse
import fcntl
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
PROMPT_DEFAULT = Path("/tmp/aicrm_codex_next_prompt.md")
OWNER_DECISION_DEFAULT = Path("/tmp/aicrm_codex_owner_decision_package.md")
LOG_DIR_DEFAULT = ROOT / "logs/codex-autopilot"

REQUIRED_PREFLIGHT_DOCS = [
    "docs/development/codex_architecture_operating_memory.md",
    "docs/development/autonomous_development_loop.md",
    "docs/development/phase_execution_state.yaml",
    "docs/development/autonomous_stop_conditions.yaml",
    "docs/development/ai_crm_next_architecture_skill.md",
    "skills/ai-crm-next-architecture/SKILL.md",
    "docs/route_ownership/production_route_ownership_manifest.yaml",
    "docs/development/legacy_replacement_backlog.yaml",
    "docs/development/codex_autopilot_runtime_runbook.md",
]
ACTION_TEMPLATES_ALLOWED_ACTIONS = {
    "phase_4am_staging_execution",
    "phase_4am_approval_config_closure",
    "phase_4am_blocked_evidence_review",
}
STOP_TERM_EXEMPT_WORK_PACKAGES = {
    "phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub_bundle",
    "phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag_bundle",
    "phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence_bundle",
    "phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness_bundle",
    "phase_5aj_openclaw_mcp_ai_assist_family_acceptance_bundle",
    "phase_5ak_questionnaire_external_submit_contract_fake_stub_bundle",
    "phase_5al_questionnaire_external_submit_live_adapter_behind_flag_bundle",
    "phase_5am_questionnaire_external_submit_staging_canary_evidence_bundle",
    "phase_5an_questionnaire_external_submit_production_canary_readiness_bundle",
    "phase_5ao_questionnaire_external_submit_family_acceptance_bundle",
    "phase_5_aggregate_acceptance_review_bundle",
}
OWNER_DECISION_LABELS = {"owner-decision-required", "automerge-blocked"}
AUTOPILOT_SAFE_LABEL = "autopilot-safe"


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


def load_yaml(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore

        return yaml.safe_load(text) or {}
    except ModuleNotFoundError:
        data, _ = _parse_yaml_block(_yaml_lines(text), 0, 0)
        return data if isinstance(data, dict) else {}


def run_command(args: list[str], timeout: int = 60) -> tuple[int, str, str]:
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def changed_files() -> set[str]:
    changed: set[str] = set()
    for args in (
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        ["git", "diff", "--name-only"],
        ["git", "diff", "--name-only", "--cached"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        code, stdout, _ = run_command(args)
        if code == 0:
            changed.update(line.strip() for line in stdout.splitlines() if line.strip())
    return changed


def stop_terms(stop: dict[str, Any]) -> set[str]:
    terms: set[str] = set()
    for item in stop.get("high_risk_stop_conditions", []):
        if isinstance(item, dict):
            terms.update(str(term).lower() for term in item.get("terms", []))
    return terms


def text_hits_stop_condition(text: str, terms: set[str]) -> list[str]:
    lowered = text.lower()
    return sorted(term for term in terms if term and term in lowered)


def diff_hits_stop_condition(paths: set[str], terms: set[str]) -> list[str]:
    hits: list[str] = []
    policy_paths = {
        "docs/development/autonomous_development_loop.md",
        "docs/development/autonomous_stop_conditions.yaml",
        "docs/development/phase_execution_state.yaml",
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
        "aicrm_next/automation_engine/agents.py",
        "aicrm_next/automation_engine/agent_outputs.py",
        "aicrm_next/automation_engine/agent_runs.py",
        "aicrm_next/automation_engine/task_groups.py",
        "aicrm_next/automation_engine/tasks.py",
        "aicrm_next/automation_engine/workflows.py",
        "aicrm_next/automation_engine/workflow_nodes.py",
        "aicrm_next/customer_tags/api.py",
        "aicrm_next/customer_tags/application.py",
        "aicrm_next/customer_tags/dto.py",
        "aicrm_next/customer_tags/wecom_tag_adapter.py",
        "aicrm_next/customer_tags/wecom_tag_contract.py",
        "aicrm_next/customer_tags/wecom_tag_live_adapter.py",
        "aicrm_next/integration_gateway/wecom_tag_live_gateway.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_adapter.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_contract.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_live_gateway.py",
        "aicrm_next/integration_gateway/oauth_identity_adapter.py",
        "aicrm_next/integration_gateway/oauth_identity_application.py",
        "aicrm_next/integration_gateway/oauth_identity_contract.py",
        "aicrm_next/integration_gateway/oauth_identity_live_adapter.py",
        "aicrm_next/integration_gateway/oauth_identity_live_gateway.py",
        "aicrm_next/integration_gateway/media_live_adapter.py",
        "aicrm_next/integration_gateway/media_live_gateway.py",
        "aicrm_next/integration_gateway/payment_commerce_live_adapter.py",
        "aicrm_next/integration_gateway/payment_commerce_live_gateway.py",
        "aicrm_next/integration_gateway/openclaw_mcp_ai_assist_live_adapter.py",
        "aicrm_next/integration_gateway/openclaw_mcp_ai_assist_live_gateway.py",
        "aicrm_next/questionnaire/external_submit_adapter.py",
        "aicrm_next/questionnaire/external_submit_live_adapter.py",
        "aicrm_next/questionnaire/external_submit_live_gateway.py",
        "tools/check_autonomous_development_loop.py",
        "tools/check_automerge_eligibility.py",
        "tools/run_codex_autopilot_tick.py",
        "docs/development/codex_autopilot_runtime_runbook.md",
        "docs/development/phase_4am_action_templates_owner_decision_package.md",
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.md",
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.yaml",
        "docs/development/phase_4an_task_groups_native_contract_plan.md",
        "docs/development/phase_4an_task_groups_native_contract_plan.yaml",
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.md",
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md",
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml",
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4ar_workflows_metadata_plan.md",
        "docs/development/phase_4ar_workflows_metadata_plan.yaml",
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.md",
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.md",
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml",
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4av_workflow_nodes_metadata_plan.md",
        "docs/development/phase_4av_workflow_nodes_metadata_plan.yaml",
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.md",
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.md",
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.yaml",
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4az_next_internal_write_candidate_selection.md",
        "docs/development/phase_4az_next_internal_write_candidate_selection.yaml",
        "docs/development/phase_4ba_tasks_metadata_plan.md",
        "docs/development/phase_4ba_tasks_metadata_plan.yaml",
        "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.md",
        "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4bc_tasks_fixture_native_contract_plan.md",
        "docs/development/phase_4bc_tasks_fixture_native_contract_plan.yaml",
        "docs/development/phase_4bd_tasks_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bd_tasks_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4be_agents_metadata_plan.md",
        "docs/development/phase_4be_agents_metadata_plan.yaml",
        "docs/development/phase_4bf_agents_schema_route_surface_confirmation.md",
        "docs/development/phase_4bf_agents_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4bg_agents_fixture_native_contract_plan.md",
        "docs/development/phase_4bg_agents_fixture_native_contract_plan.yaml",
        "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4bv_agents_fixture_runtime.md",
        "docs/development/phase_4bw_agent_outputs_fixture_runtime.md",
        "docs/development/phase_4bx_agent_runs_fixture_runtime.md",
        "docs/development/phase_4bi_agent_outputs_metadata_plan.md",
        "docs/development/phase_4bi_agent_outputs_metadata_plan.yaml",
        "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md",
        "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md",
        "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml",
        "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4bm_agent_runs_metadata_plan.md",
        "docs/development/phase_4bm_agent_runs_metadata_plan.yaml",
        "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.md",
        "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.yaml",
        "docs/development/phase_4bo_agent_runs_fixture_native_contract_plan.md",
        "docs/development/phase_4bo_agent_runs_fixture_native_contract_plan.yaml",
        "docs/development/phase_4bp_agent_runs_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bp_agent_runs_fixture_native_implementation_owner_decision.yaml",
        "docs/development/phase_4bq_agent_replay_metadata_plan.md",
        "docs/development/phase_4bq_agent_replay_metadata_plan.yaml",
        "docs/development/phase_4by_agent_replay_discovery_contract_bundle.md",
        "docs/development/phase_4by_agent_replay_discovery_contract_bundle.yaml",
        "docs/development/phase_4ca_task_groups_repository_adapter_parity_bundle.md",
        "docs/development/phase_4ca_task_groups_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4cb_workflows_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cb_workflows_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4ce_agents_repository_adapter_parity_bundle.md",
        "docs/development/phase_4ce_agents_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4cf_agent_outputs_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cf_agent_outputs_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.yaml",
        "docs/development/phase_4ch_task_groups_staging_readiness_bundle.md",
        "docs/development/phase_4ch_task_groups_staging_readiness_bundle.yaml",
        "docs/development/phase_4ci_workflows_staging_readiness_bundle.md",
        "docs/development/phase_4ci_workflows_staging_readiness_bundle.yaml",
        "docs/development/phase_4cj_workflow_nodes_staging_readiness_bundle.md",
        "docs/development/phase_4cj_workflow_nodes_staging_readiness_bundle.yaml",
        "docs/development/phase_4ck_tasks_staging_readiness_bundle.md",
        "docs/development/phase_4ck_tasks_staging_readiness_bundle.yaml",
        "docs/development/phase_4cl_agents_staging_readiness_bundle.md",
        "docs/development/phase_4cl_agents_staging_readiness_bundle.yaml",
        "docs/development/phase_4cm_agent_outputs_staging_readiness_bundle.md",
        "docs/development/phase_4cm_agent_outputs_staging_readiness_bundle.yaml",
        "docs/development/phase_4cn_agent_runs_staging_readiness_bundle.md",
        "docs/development/phase_4cn_agent_runs_staging_readiness_bundle.yaml",
        "docs/development/phase_4co_task_groups_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4co_task_groups_production_dry_run_readiness_bundle.yaml",
        "docs/development/phase_4cp_workflows_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4cp_workflows_production_dry_run_readiness_bundle.yaml",
        "docs/development/phase_4cq_workflow_nodes_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4cq_workflow_nodes_production_dry_run_readiness_bundle.yaml",
        "docs/development/phase_4cr_tasks_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4cr_tasks_production_dry_run_readiness_bundle.yaml",
        "docs/development/phase_4cs_agent_runs_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4cs_agent_runs_production_dry_run_readiness_bundle.yaml",
        "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.yaml",
        "docs/development/phase_4cu_internal_write_acceptance_review.md",
        "docs/development/phase_4cu_internal_write_acceptance_review.yaml",
        "docs/development/phase_4cv_phase5_readiness_entry.md",
        "docs/development/phase_4cv_phase5_readiness_entry.yaml",
        "docs/development/phase_5a_wecom_tag_adapter_contract.md",
        "docs/development/phase_5a_wecom_tag_adapter_contract.yaml",
        "docs/development/phase_5b_wecom_tag_fake_stub_adapter.md",
        "docs/development/phase_5b_wecom_tag_fake_stub_adapter.yaml",
        "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.md",
        "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.yaml",
        "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.md",
        "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.yaml",
        "docs/development/phase_5e_wecom_tag_production_canary_readiness.md",
        "docs/development/phase_5e_wecom_tag_production_canary_readiness.yaml",
        "docs/development/phase_5f_wecom_tag_production_live_canary_execution.md",
        "docs/development/phase_5f_wecom_tag_production_live_canary_execution.yaml",
        "docs/development/phase_5g_wecom_tag_family_acceptance.md",
        "docs/development/phase_5g_wecom_tag_family_acceptance.yaml",
        "docs/development/phase_5h_wecom_customer_contact_adapter_contract.md",
        "docs/development/phase_5h_wecom_customer_contact_adapter_contract.yaml",
        "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.md",
        "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.yaml",
        "tools/check_phase5i_wecom_customer_contact_fake_stub_adapter.py",
        "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py",
        "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py",
        "tests/test_phase5i_wecom_customer_contact_fake_stub_adapter.py",
        "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.md",
        "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.yaml",
        "tools/check_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
        "tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py",
        "tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py",
        "tests/test_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
        "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.md",
        "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.yaml",
        "tools/check_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/run_phase5k_wecom_customer_contact_production_callback_readiness_review.py",
        "tests/test_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.md",
        "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.yaml",
        "tools/check_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tools/run_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tests/test_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.md",
        "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.yaml",
        "tools/check_phase5m_wecom_customer_contact_callback_family_acceptance.py",
        "tests/test_phase5m_wecom_customer_contact_callback_family_acceptance.py",
        "docs/development/phase_5n_oauth_identity_adapter_contract.md",
        "docs/development/phase_5n_oauth_identity_adapter_contract.yaml",
        "tools/check_phase5n_oauth_identity_adapter_contract.py",
        "tools/run_phase5n_oauth_identity_adapter_contract_evidence.py",
        "tests/test_phase5n_oauth_identity_adapter_contract.py",
        "docs/development/phase_5o_oauth_identity_fake_stub_adapter.md",
        "docs/development/phase_5o_oauth_identity_fake_stub_adapter.yaml",
        "tools/check_phase5o_oauth_identity_fake_stub_adapter.py",
        "tools/run_phase5o_oauth_identity_fake_stub_staging_smoke.py",
        "tools/run_phase5o_oauth_identity_fake_stub_production_dry_run.py",
        "tests/test_phase5o_oauth_identity_fake_stub_adapter.py",
        "docs/development/phase_5p_oauth_identity_live_adapter_behind_flag.md",
        "docs/development/phase_5p_oauth_identity_live_adapter_behind_flag.yaml",
        "tools/check_phase5p_oauth_identity_live_adapter_behind_flag.py",
        "tools/run_phase5p_oauth_identity_live_staging_evidence.py",
        "tools/run_phase5p_oauth_identity_live_production_dry_run_gate.py",
        "tests/test_phase5p_oauth_identity_live_adapter_behind_flag.py",
        "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.md",
        "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.yaml",
        "tools/check_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/run_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/run_phase5q_oauth_identity_production_live_readiness_review.py",
        "tests/test_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "docs/development/phase_5r_oauth_identity_production_canary_readiness.md",
        "docs/development/phase_5r_oauth_identity_production_canary_readiness.yaml",
        "tools/check_phase5r_oauth_identity_production_canary_readiness.py",
        "tools/run_phase5r_oauth_identity_production_canary_readiness.py",
        "tests/test_phase5r_oauth_identity_production_canary_readiness.py",
        "docs/development/phase_5s_oauth_identity_production_live_canary_execution.md",
        "docs/development/phase_5s_oauth_identity_production_live_canary_execution.yaml",
        "tools/check_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/run_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/run_phase5s_oauth_identity_production_canary_cleanup.py",
        "tests/test_phase5s_oauth_identity_production_live_canary_execution.py",
        "docs/development/phase_5t_oauth_identity_family_acceptance.md",
        "docs/development/phase_5t_oauth_identity_family_acceptance.yaml",
        "tools/check_phase5t_oauth_identity_family_acceptance.py",
        "tests/test_phase5t_oauth_identity_family_acceptance.py",
        "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.md",
        "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.yaml",
        "tools/check_phase5u_media_upload_adapter_contract_fake_stub.py",
        "tools/run_phase5u_media_upload_fake_stub_staging_smoke.py",
        "tools/run_phase5u_media_upload_fake_stub_production_dry_run.py",
        "tests/test_phase5u_media_upload_adapter_contract_fake_stub.py",
        "docs/development/phase_5v_media_upload_live_adapter_behind_flag.md",
        "docs/development/phase_5v_media_upload_live_adapter_behind_flag.yaml",
        "tools/check_phase5v_media_upload_live_adapter_behind_flag.py",
        "tools/run_phase5v_media_upload_live_staging_evidence.py",
        "tools/run_phase5v_media_upload_live_production_dry_run_gate.py",
        "tests/test_phase5v_media_upload_live_adapter_behind_flag.py",
        "docs/development/phase_5w_media_upload_staging_live_canary_evidence.md",
        "docs/development/phase_5w_media_upload_staging_live_canary_evidence.yaml",
        "tools/check_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/run_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/run_phase5w_media_upload_production_live_readiness_review.py",
        "tests/test_phase5w_media_upload_staging_live_canary_evidence.py",
        "docs/development/phase_5x_media_upload_production_canary_readiness_execution.md",
        "docs/development/phase_5x_media_upload_production_canary_readiness_execution.yaml",
        "tools/check_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/run_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/run_phase5x_media_upload_production_canary_cleanup.py",
        "tests/test_phase5x_media_upload_production_canary_readiness_execution.py",
        "docs/development/phase_5y_media_upload_family_acceptance.md",
        "docs/development/phase_5y_media_upload_family_acceptance.yaml",
        "tools/check_phase5y_media_upload_family_acceptance.py",
        "tests/test_phase5y_media_upload_family_acceptance.py",
        "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.md",
        "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.yaml",
        "tools/check_phase5z_payment_commerce_adapter_contract_fake_stub.py",
        "tools/run_phase5z_payment_commerce_fake_stub_evidence.py",
        "tests/test_phase5z_payment_commerce_adapter_contract_fake_stub.py",
        "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.md",
        "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.yaml",
        "tools/check_phase5aa_payment_commerce_live_adapter_behind_flag.py",
        "tools/run_phase5aa_payment_commerce_live_staging_evidence.py",
        "tools/run_phase5aa_payment_commerce_live_production_dry_run_gate.py",
        "tests/test_phase5aa_payment_commerce_live_adapter_behind_flag.py",
        "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.md",
        "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.yaml",
        "tools/check_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/run_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/run_phase5ab_payment_commerce_production_readiness_review.py",
        "tests/test_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "docs/development/phase_5ac_payment_commerce_production_canary_readiness.md",
        "docs/development/phase_5ac_payment_commerce_production_canary_readiness.yaml",
        "tools/check_phase5ac_payment_commerce_production_canary_readiness.py",
        "tools/run_phase5ac_payment_commerce_production_canary_readiness.py",
        "tests/test_phase5ac_payment_commerce_production_canary_readiness.py",
        "docs/development/phase_5ad_payment_commerce_production_canary_tooling.md",
        "docs/development/phase_5ad_payment_commerce_production_canary_tooling.yaml",
        "tools/check_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/run_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/run_phase5ad_payment_commerce_production_canary_cleanup.py",
        "tests/test_phase5ad_payment_commerce_production_canary_tooling.py",
        "docs/development/phase_5ae_payment_commerce_family_acceptance.md",
        "docs/development/phase_5ae_payment_commerce_family_acceptance.yaml",
        "tools/check_phase5ae_payment_commerce_family_acceptance.py",
        "tests/test_phase5ae_payment_commerce_family_acceptance.py",
        "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.md",
        "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.yaml",
        "tools/check_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.py",
        "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_staging_smoke.py",
        "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_production_dry_run.py",
        "tests/test_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.py",
        "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.md",
        "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.yaml",
        "tools/check_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.py",
        "tools/run_phase5ag_openclaw_mcp_ai_assist_live_staging_evidence.py",
        "tools/run_phase5ag_openclaw_mcp_ai_assist_live_production_dry_run_gate.py",
        "tests/test_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.py",
        "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.md",
        "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.yaml",
        "tools/check_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
        "tools/run_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
        "tools/run_phase5ah_openclaw_mcp_ai_assist_production_readiness_review.py",
        "tests/test_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
        "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.md",
        "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.yaml",
        "tools/check_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
        "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
        "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup.py",
        "tests/test_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
        "docs/development/phase_5aj_openclaw_mcp_ai_assist_family_acceptance.md",
        "docs/development/phase_5aj_openclaw_mcp_ai_assist_family_acceptance.yaml",
        "tools/check_phase5aj_openclaw_mcp_ai_assist_family_acceptance.py",
        "tests/test_phase5aj_openclaw_mcp_ai_assist_family_acceptance.py",
        "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.md",
        "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.yaml",
        "tools/check_phase5ak_questionnaire_external_submit_contract_fake_stub.py",
        "tools/run_phase5ak_questionnaire_external_submit_fake_stub_staging_smoke.py",
        "tools/run_phase5ak_questionnaire_external_submit_fake_stub_production_dry_run.py",
        "tests/test_phase5ak_questionnaire_external_submit_contract_fake_stub.py",
        "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.md",
        "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.yaml",
        "tools/check_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py",
        "tools/run_phase5al_questionnaire_external_submit_live_staging_evidence.py",
        "tools/run_phase5al_questionnaire_external_submit_live_production_dry_run_gate.py",
        "tests/test_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py",
        "docs/development/phase_5am_questionnaire_external_submit_staging_canary_evidence.md",
        "docs/development/phase_5am_questionnaire_external_submit_staging_canary_evidence.yaml",
        "tools/check_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
        "tools/run_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
        "tools/run_phase5am_questionnaire_external_submit_production_readiness_review.py",
        "tests/test_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
        "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.md",
        "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.yaml",
        "tools/check_phase5an_questionnaire_external_submit_production_canary_readiness.py",
        "tools/run_phase5an_questionnaire_external_submit_production_canary_readiness.py",
        "tools/run_phase5an_questionnaire_external_submit_production_canary_cleanup.py",
        "tests/test_phase5an_questionnaire_external_submit_production_canary_readiness.py",
        "docs/development/phase_5ao_questionnaire_external_submit_family_acceptance.md",
        "docs/development/phase_5ao_questionnaire_external_submit_family_acceptance.yaml",
        "tools/check_phase5ao_questionnaire_external_submit_family_acceptance.py",
        "tests/test_phase5ao_questionnaire_external_submit_family_acceptance.py",
        "docs/development/phase_4br_task_groups_fixture_runtime.md",
        "docs/development/phase_4bs_workflows_fixture_runtime.md",
        "docs/development/phase_4bt_workflow_nodes_fixture_runtime.md",
        "docs/development/phase_4bu_tasks_fixture_runtime.md",
        "scripts/codex_autopilot_tick.sh",
        "tests/test_autonomous_development_loop.py",
        "tests/test_automerge_eligibility.py",
        "tests/test_phase4am_action_templates_staging_owner_decision_package.py",
        "tests/test_phase4am_action_templates_staging_approval_config_closure.py",
        "tests/test_phase4an_task_groups_native_contract_plan.py",
        "tests/test_phase4ao_task_groups_schema_route_surface_confirmation.py",
        "tests/test_phase4ap_task_groups_fixture_native_contract_plan.py",
        "tests/test_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4ar_workflows_metadata_plan.py",
        "tests/test_phase4as_workflows_schema_route_surface_confirmation.py",
        "tests/test_phase4at_workflows_fixture_native_contract_plan.py",
        "tests/test_phase4au_workflows_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4av_workflow_nodes_metadata_plan.py",
        "tests/test_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
        "tests/test_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
        "tests/test_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4az_next_internal_write_candidate_selection.py",
        "tests/test_phase4ba_tasks_metadata_plan.py",
        "tests/test_phase4bb_tasks_schema_route_surface_confirmation.py",
        "tests/test_phase4bc_tasks_fixture_native_contract_plan.py",
        "tests/test_phase4bd_tasks_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4be_agents_metadata_plan.py",
        "tests/test_phase4bf_agents_schema_route_surface_confirmation.py",
        "tests/test_phase4bg_agents_fixture_native_contract_plan.py",
        "tests/test_phase4bh_agents_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bv_agents_fixture_runtime.py",
        "tests/test_phase4bw_agent_outputs_fixture_runtime.py",
        "tests/test_phase4bx_agent_runs_fixture_runtime.py",
        "tests/test_phase4bi_agent_outputs_metadata_plan.py",
        "tests/test_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
        "tests/test_phase4bk_agent_outputs_fixture_native_contract_plan.py",
        "tests/test_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bm_agent_runs_metadata_plan.py",
        "tests/test_phase4bn_agent_runs_schema_route_surface_confirmation.py",
        "tests/test_phase4bo_agent_runs_fixture_native_contract_plan.py",
        "tests/test_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bq_agent_replay_metadata_plan.py",
        "tests/test_phase4by_agent_replay_discovery_contract_bundle.py",
        "tests/test_phase4ca_task_groups_repository_adapter_parity_bundle.py",
        "tests/test_phase4cb_workflows_repository_adapter_parity_bundle.py",
        "tests/test_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py",
        "tests/test_phase4cd_tasks_repository_adapter_parity_bundle.py",
        "tests/test_phase4ce_agents_repository_adapter_parity_bundle.py",
        "tests/test_phase4br_task_groups_fixture_runtime.py",
        "tests/test_phase4bs_workflows_fixture_runtime.py",
        "tests/test_phase4bt_workflow_nodes_fixture_runtime.py",
        "tests/test_phase4bu_tasks_fixture_runtime.py",
        "tests/test_codex_autopilot_runtime_contract.py",
        "tools/check_phase4am_action_templates_staging_owner_decision_package.py",
        "tools/check_phase4am_action_templates_staging_approval_config_closure.py",
        "tools/check_phase4an_task_groups_native_contract_plan.py",
        "tools/check_phase4ao_task_groups_schema_route_surface_confirmation.py",
        "tools/check_phase4ap_task_groups_fixture_native_contract_plan.py",
        "tools/check_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4ar_workflows_metadata_plan.py",
        "tools/check_phase4as_workflows_schema_route_surface_confirmation.py",
        "tools/check_phase4at_workflows_fixture_native_contract_plan.py",
        "tools/check_phase4au_workflows_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4av_workflow_nodes_metadata_plan.py",
        "tools/check_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
        "tools/check_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
        "tools/check_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4az_next_internal_write_candidate_selection.py",
        "tools/check_phase4ba_tasks_metadata_plan.py",
        "tools/check_phase4bb_tasks_schema_route_surface_confirmation.py",
        "tools/check_phase4bc_tasks_fixture_native_contract_plan.py",
        "tools/check_phase4bd_tasks_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4be_agents_metadata_plan.py",
        "tools/check_phase4bf_agents_schema_route_surface_confirmation.py",
        "tools/check_phase4bg_agents_fixture_native_contract_plan.py",
        "tools/check_phase4bh_agents_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4bv_agents_fixture_runtime.py",
        "tools/check_phase4bw_agent_outputs_fixture_runtime.py",
        "tools/check_phase4bx_agent_runs_fixture_runtime.py",
        "tools/check_phase4bi_agent_outputs_metadata_plan.py",
        "tools/check_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
        "tools/check_phase4bk_agent_outputs_fixture_native_contract_plan.py",
        "tools/check_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4bm_agent_runs_metadata_plan.py",
        "tools/check_phase4bn_agent_runs_schema_route_surface_confirmation.py",
        "tools/check_phase4bo_agent_runs_fixture_native_contract_plan.py",
        "tools/check_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py",
        "tools/check_phase4bq_agent_replay_metadata_plan.py",
        "tools/check_phase4by_agent_replay_discovery_contract_bundle.py",
        "tools/check_phase4ca_task_groups_repository_adapter_parity_bundle.py",
        "tools/run_phase4ca_task_groups_adapter_parity.py",
        "tools/check_phase4cb_workflows_repository_adapter_parity_bundle.py",
        "tools/run_phase4cb_workflows_adapter_parity.py",
        "tools/check_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py",
        "tools/run_phase4cc_workflow_nodes_adapter_parity.py",
        "tools/check_phase4cd_tasks_repository_adapter_parity_bundle.py",
        "tools/run_phase4cd_tasks_adapter_parity.py",
        "tools/check_phase4ce_agents_repository_adapter_parity_bundle.py",
        "tools/run_phase4ce_agents_adapter_parity.py",
        "tools/check_phase4cf_agent_outputs_repository_adapter_parity_bundle.py",
        "tools/run_phase4cf_agent_outputs_adapter_parity.py",
        "tests/test_phase4cf_agent_outputs_repository_adapter_parity_bundle.py",
        "tools/check_phase4cg_agent_runs_repository_adapter_parity_bundle.py",
        "tools/run_phase4cg_agent_runs_adapter_parity.py",
        "tests/test_phase4cg_agent_runs_repository_adapter_parity_bundle.py",
        "tools/check_phase4ch_task_groups_staging_readiness_bundle.py",
        "tools/run_phase4ch_task_groups_staging_readiness.py",
        "tests/test_phase4ch_task_groups_staging_readiness_bundle.py",
        "tools/check_phase4ci_workflows_staging_readiness_bundle.py",
        "tools/run_phase4ci_workflows_staging_readiness.py",
        "tests/test_phase4ci_workflows_staging_readiness_bundle.py",
        "tools/check_phase4cj_workflow_nodes_staging_readiness_bundle.py",
        "tools/run_phase4cj_workflow_nodes_staging_readiness.py",
        "tests/test_phase4cj_workflow_nodes_staging_readiness_bundle.py",
        "tools/check_phase4ck_tasks_staging_readiness_bundle.py",
        "tools/run_phase4ck_tasks_staging_readiness.py",
        "tests/test_phase4ck_tasks_staging_readiness_bundle.py",
        "tools/check_phase4cl_agents_staging_readiness_bundle.py",
        "tools/run_phase4cl_agents_staging_readiness.py",
        "tests/test_phase4cl_agents_staging_readiness_bundle.py",
        "tools/check_phase4cm_agent_outputs_staging_readiness_bundle.py",
        "tools/run_phase4cm_agent_outputs_staging_readiness.py",
        "tests/test_phase4cm_agent_outputs_staging_readiness_bundle.py",
        "tools/check_phase4cn_agent_runs_staging_readiness_bundle.py",
        "tools/run_phase4cn_agent_runs_staging_readiness.py",
        "tests/test_phase4cn_agent_runs_staging_readiness_bundle.py",
        "tools/check_phase4co_task_groups_production_dry_run_readiness_bundle.py",
        "tools/run_phase4co_task_groups_production_readonly_dry_run.py",
        "tests/test_phase4co_task_groups_production_dry_run_readiness_bundle.py",
        "tools/check_phase4cp_workflows_production_dry_run_readiness_bundle.py",
        "tools/run_phase4cp_workflows_production_readonly_dry_run.py",
        "tests/test_phase4cp_workflows_production_dry_run_readiness_bundle.py",
        "tools/check_phase4cq_workflow_nodes_production_dry_run_readiness_bundle.py",
        "tools/run_phase4cq_workflow_nodes_production_readonly_dry_run.py",
        "tests/test_phase4cq_workflow_nodes_production_dry_run_readiness_bundle.py",
        "tools/check_phase4cr_tasks_production_dry_run_readiness_bundle.py",
        "tools/run_phase4cr_tasks_production_readonly_dry_run.py",
        "tests/test_phase4cr_tasks_production_dry_run_readiness_bundle.py",
        "tools/check_phase4cs_agent_runs_production_dry_run_readiness_bundle.py",
        "tools/run_phase4cs_agent_runs_production_readonly_dry_run.py",
        "tests/test_phase4cs_agent_runs_production_dry_run_readiness_bundle.py",
        "tools/check_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py",
        "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py",
        "tests/test_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py",
        "tools/check_phase4cu_internal_write_acceptance_review.py",
        "tests/test_phase4cu_internal_write_acceptance_review.py",
        "tools/check_phase4cv_phase5_readiness_entry.py",
        "tests/test_phase4cv_phase5_readiness_entry.py",
        "tools/check_phase5a_wecom_tag_adapter_contract.py",
        "tools/run_phase5a_wecom_tag_adapter_contract_evidence.py",
        "tests/test_phase5a_wecom_tag_adapter_contract.py",
        "tools/check_phase5b_wecom_tag_fake_stub_adapter.py",
        "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py",
        "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py",
        "tests/test_phase5b_wecom_tag_fake_stub_adapter.py",
        "tools/check_phase5c_wecom_tag_live_adapter_behind_flag.py",
        "tools/run_phase5c_wecom_tag_live_staging_evidence.py",
        "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py",
        "tests/test_phase5c_wecom_tag_live_adapter_behind_flag.py",
        "tools/check_phase5d_wecom_tag_staging_live_canary_evidence.py",
        "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py",
        "tools/run_phase5d_wecom_tag_production_live_readiness_review.py",
        "tests/test_phase5d_wecom_tag_staging_live_canary_evidence.py",
        "tools/check_phase5e_wecom_tag_production_canary_readiness.py",
        "tools/run_phase5e_wecom_tag_production_canary_readiness.py",
        "tests/test_phase5e_wecom_tag_production_canary_readiness.py",
        "tools/check_phase5f_wecom_tag_production_live_canary_execution.py",
        "tools/run_phase5f_wecom_tag_production_live_canary_execution.py",
        "tools/run_phase5f_wecom_tag_production_canary_cleanup.py",
        "tests/test_phase5f_wecom_tag_production_live_canary_execution.py",
        "tools/check_phase5g_wecom_tag_family_acceptance.py",
        "tests/test_phase5g_wecom_tag_family_acceptance.py",
        "tools/check_phase5h_wecom_customer_contact_adapter_contract.py",
        "tools/run_phase5h_wecom_customer_contact_adapter_contract_evidence.py",
        "tests/test_phase5h_wecom_customer_contact_adapter_contract.py",
        "tools/check_phase4br_task_groups_fixture_runtime.py",
        "tools/check_phase4bs_workflows_fixture_runtime.py",
        "tools/check_phase4bt_workflow_nodes_fixture_runtime.py",
        "tools/check_phase4bu_tasks_fixture_runtime.py",
    }
    for path in sorted(paths):
        if path in policy_paths:
            continue
        full = ROOT / path
        if not full.exists() or not full.is_file():
            continue
        matched = text_hits_stop_condition(full.read_text(encoding="utf-8", errors="ignore"), terms)
        hits.extend(f"{path}: {term}" for term in matched)
    return hits


def fetch_open_autopilot_prs(skip_github: bool) -> tuple[list[dict[str, Any]], list[str]]:
    if skip_github:
        return [], ["github inspection skipped"]
    code, stdout, stderr = run_command(
        [
            "gh",
            "pr",
            "list",
            "--state",
            "open",
            "--json",
            "number,title,headRefName,labels,statusCheckRollup,url",
            "--limit",
            "50",
        ],
        timeout=45,
    )
    if code != 0:
        return [], [f"gh pr list unavailable: {(stderr or stdout).strip()}"]
    try:
        prs = json.loads(stdout)
    except json.JSONDecodeError:
        return [], ["gh pr list returned invalid JSON"]
    autopilot = [
        pr
        for pr in prs
        if "autopilot" in str(pr.get("headRefName", "")).lower()
        or "autopilot" in str(pr.get("title", "")).lower()
        or any("autopilot" in str(label.get("name", "")).lower() for label in pr.get("labels", []))
    ]
    return autopilot, []


def classify_open_pr(pr: dict[str, Any]) -> dict[str, Any]:
    labels = {str(label.get("name", "")).lower() for label in pr.get("labels", [])}
    checks = pr.get("statusCheckRollup", [])
    pending = [item.get("name") for item in checks if item.get("status") != "COMPLETED"]
    failed = [
        item.get("name")
        for item in checks
        if item.get("status") == "COMPLETED" and item.get("conclusion") not in {"SUCCESS", "SKIPPED", "NEUTRAL"}
    ]
    passed = [item.get("name") for item in checks if item.get("status") == "COMPLETED" and item.get("conclusion") == "SUCCESS"]
    return {
        "number": pr.get("number"),
        "url": pr.get("url"),
        "labels": sorted(labels),
        "pending": pending,
        "failed": failed,
        "passed": passed,
        "owner_decision_label": bool(labels & OWNER_DECISION_LABELS),
        "autopilot_safe": AUTOPILOT_SAFE_LABEL in labels,
        "checks_green": bool(checks) and not pending and not failed,
    }


def admin_merge_pr(pr_number: int | str | None) -> tuple[bool, str]:
    if not pr_number:
        return False, "missing PR number"
    code, stdout, stderr = run_command(
        ["gh", "pr", "merge", str(pr_number), "--admin", "--merge", "--delete-branch"],
        timeout=120,
    )
    if code == 0:
        return True, (stdout or "").strip()
    return False, (stderr or stdout or "").strip()


def choose_next_action(state: dict[str, Any], requested: str | None = None) -> str:
    return choose_next_work_package(state, requested)


def choose_next_work_package(state: dict[str, Any], requested: str | None = None) -> str:
    allowed = [str(item) for item in state.get("next_allowed_actions", [])]
    if requested:
        if requested not in allowed:
            raise ValueError(f"requested work package is not in next_allowed_actions: {requested}")
        return requested
    if not allowed:
        raise ValueError("phase_execution_state has no next_allowed_actions")
    policy = state.get("work_package_policy") if isinstance(state.get("work_package_policy"), dict) else {}
    should_avoid_repeated_blocked_review = (
        policy.get("avoid_repeated_blocked_evidence_review") is True
        and "phase_4am_approval_config_closure" in allowed
        and (
            state.get("last_created_pr") == "#641"
            or state.get("last_attempted_action") == "phase_4am_blocked_evidence_review"
        )
    )
    if should_avoid_repeated_blocked_review:
        return "phase_4am_approval_config_closure"
    return allowed[0]


def owner_decision_package(reason: str, work_package: str | None, output_path: Path) -> None:
    lines = [
        "# AI-CRM Codex Autopilot Owner Decision Package",
        "",
        f"- reason: {reason}",
        f"- selected_work_package: {work_package or 'none'}",
        "- auto_merge_allowed: false",
        "- admin_merge_allowed: false",
        "- production_owner_switch_allowed: false",
        "- production_write_allowed: false",
        "- fallback_removal_allowed: false",
        "- real_external_call_allowed: false",
        "",
        "## Owner Decision Needed",
        "",
        "Codex autopilot detected a stop condition or blocked state. The next step requires explicit owner review before another implementation PR may be generated or merged.",
    ]
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def prompt_for_work_package(work_package: str, state: dict[str, Any], output_path: Path) -> None:
    docs = "\n".join(f"- {path}" for path in REQUIRED_PREFLIGHT_DOCS)
    prompt = f"""# AI-CRM Codex Autopilot Next Prompt

You are working in qianlan333/AI-CRM from latest main.

## Required preflight

Read and follow:
{docs}

## Selected compressed bounded bundle

- work_package: {work_package}
- active_candidate: {state.get("active_candidate")}
- capability_owner: {state.get("capability_owner")}
- current_phase: {state.get("current_phase")}

## Hard boundaries

- Only choose from docs/development/phase_execution_state.yaml next_allowed_actions.
- For action-templates, stay within Phase 4AM staging execution / approval config closure / blocked evidence review.
- If PR #641 is merged, do not repeat a standalone blocked evidence review. Prefer the Phase 4AM staging approval/config closure package unless a stop condition requires an owner decision package.
- Do not switch production owner.
- Do not write production.
- Do not remove fallback.
- Do not modify production_compat, aicrm_next/main.py, business routes, schema/migrations, deploy/nginx/systemd, or wecom_ability_service runtime.
- Phase 4 fixture/native packages may touch explicitly selected aicrm_next/automation_engine files only.
- Phase 5B WeCom tag fake/stub packages may touch explicitly selected aicrm_next/customer_tags files only; live WeCom calls remain forbidden.
- Phase 5C WeCom tag live adapter packages may touch explicitly selected aicrm_next/customer_tags and aicrm_next/integration_gateway live-behind-flag files only; live calls must remain disabled by default.
- Phase 5I WeCom contact callback fake/stub packages may touch explicitly selected aicrm_next/integration_gateway fake/stub callback files only; live callback cutover and production writes remain forbidden.
- Phase 5J WeCom contact callback live adapter packages may touch explicitly selected aicrm_next/integration_gateway live-behind-flag callback files only; live callback processing must remain disabled by default.
- Phase 5K WeCom contact callback staging canary packages must stay docs/tools/tests/state only; production callback processing remains forbidden.
- Phase 5L WeCom contact callback production readiness packages must stay docs/tools/tests/state only; production callback execution remains forbidden by default.
- Phase 5M WeCom contact callback family acceptance packages must stay docs/tools/tests/state only; no new live callback is allowed.
- Phase 5N OAuth identity adapter contract packages must stay docs/tools/tests/state only; no live OAuth callback cutover or token exchange is allowed.
- Phase 5O OAuth identity fake/stub packages may touch explicitly selected aicrm_next/integration_gateway fake/stub OAuth files only; live OAuth callback and token exchange remain disabled.
- Phase 5P OAuth identity live-behind-flag packages may touch explicitly selected aicrm_next/integration_gateway live adapter files only; live OAuth remains disabled by default.
- Do not enable real external calls, timer, automation execution, or outbound send by default.
- If any stop condition from docs/development/autonomous_stop_conditions.yaml appears, stop and generate an owner decision package only. Do not auto-merge.

## Required implementation behavior

- Advance only one compressed bounded bundle within a single route family and risk boundary.
- Target 15-20 minutes of focused work for the current compressed safe bundle.
- Avoid one- or two-line state-only PRs. If a state-only update is unavoidable, explain in the PR body why it cannot be folded into a fuller low-risk work package.
- For Phase 4AM action-templates, a package may combine blocked evidence review summary, staging approval/config checklist, owner approval closure form, phase_execution_state.yaml update, checker/test coverage, and Next action.
- Update docs/development/phase_execution_state.yaml with the resulting status.
- Keep Business value, Business continuity, Risk / rollback, and Next action in the PR body.
- Run:
  - python3 tools/check_autonomous_development_loop.py --output-md /tmp/autonomous_development_loop.md --output-json /tmp/autonomous_development_loop.json
  - python3 tools/check_automerge_eligibility.py --output-md /tmp/automerge_eligibility.md --output-json /tmp/automerge_eligibility.json
  - python3 tools/check_legacy_facade_growth_freeze.py --output-md /tmp/legacy_facade_growth_freeze.md --output-json /tmp/legacy_facade_growth_freeze.json
  - python3 tools/generate_legacy_replacement_backlog.py --check --output-json /tmp/legacy_replacement_backlog_check.json
  - git diff --check

## Auto-merge boundary

Low-risk admin merge is allowed only when eligibility is true, GitHub required checks are green, no stop condition exists, and the diff is limited to docs/tools/tests/checker/state files, explicitly selected fixture/native aicrm_next/automation_engine runtime files, explicitly selected aicrm_next/customer_tags fake/stub files, explicitly selected Phase 5C live-behind-flag adapter files, explicitly selected Phase 5I fake/stub callback adapter files, or explicitly selected Phase 5J live-behind-flag callback adapter files. Owner decision packages must not auto-merge.
"""
    output_path.write_text(prompt, encoding="utf-8")


def build_tick_report(args: argparse.Namespace) -> dict[str, Any]:
    state = load_yaml(STATE)
    stop = load_yaml(STOP)
    terms = stop_terms(stop)
    details: dict[str, Any] = {
        "prompt_output": str(args.prompt_output),
        "owner_decision_output": str(args.owner_decision_output),
    }
    warnings: list[str] = []
    blockers: list[str] = []

    work_package: str | None = None
    try:
        work_package = choose_next_work_package(state, args.action)
    except ValueError as exc:
        blockers.append(str(exc))

    if work_package and state.get("active_candidate") == "/api/admin/automation-conversion/action-templates*":
        if work_package not in ACTION_TEMPLATES_ALLOWED_ACTIONS:
            blockers.append(f"action-templates autopilot work package is not Phase 4AM bounded: {work_package}")

    action_stop_hits = []
    if work_package and work_package not in STOP_TERM_EXEMPT_WORK_PACKAGES:
        action_stop_hits = text_hits_stop_condition(str(work_package).replace("_", " "), terms)
    if action_stop_hits:
        blockers.append(f"selected work package touches stop condition: {action_stop_hits}")

    diff_stop_hits = diff_hits_stop_condition(changed_files(), terms)
    if diff_stop_hits:
        blockers.append(f"current diff touches stop condition: {diff_stop_hits}")

    open_prs, pr_warnings = fetch_open_autopilot_prs(args.skip_github)
    warnings.extend(pr_warnings)
    pr_classifications = [classify_open_pr(pr) for pr in open_prs]
    details["open_autopilot_prs"] = pr_classifications
    for pr in pr_classifications:
        if pr["owner_decision_label"]:
            blockers.append(f"open autopilot PR has owner-decision/automerge-blocked label: #{pr['number']}")
        elif pr["pending"]:
            blockers.append(f"open autopilot PR checks pending: #{pr['number']}")
        elif pr["failed"]:
            repair_marker = LOG_DIR_DEFAULT / f"repair-attempt-pr-{pr['number']}.json"
            if repair_marker.exists():
                blockers.append(f"open autopilot PR checks failed and bounded repair already attempted: #{pr['number']}")
            else:
                details["bounded_repair_allowed_for_pr"] = pr["number"]
                repair_marker.parent.mkdir(parents=True, exist_ok=True)
                repair_marker.write_text(json.dumps({"pr": pr["number"], "at": int(time.time())}) + "\n", encoding="utf-8")
                blockers.append(f"open autopilot PR checks failed; bounded repair prompt required before new action: #{pr['number']}")
        elif pr["checks_green"] and pr["autopilot_safe"]:
            merged, merge_detail = admin_merge_pr(pr["number"])
            details["admin_merge_attempt"] = {"pr": pr["number"], "merged": merged, "detail": merge_detail}
            if merged:
                return {
                    "ok": True,
                    "result_status": "open_autopilot_pr_admin_merged",
                    "prompt_generated": False,
                    "selected_work_package": work_package,
                    "selected_action": work_package,
                    "auto_merge_allowed": True,
                    "admin_merge_allowed": True,
                    "blockers": [],
                    "warnings": warnings,
                    "details": details,
                }
            blockers.append(f"open autopilot PR admin merge failed: #{pr['number']}: {merge_detail}")
        elif pr["checks_green"] and not pr["autopilot_safe"]:
            blockers.append(f"open autopilot PR checks passed but autopilot-safe label is missing: #{pr['number']}")
        else:
            blockers.append(f"open autopilot PR exists; wait for merge or owner decision: #{pr['number']}")

    if blockers:
        args.owner_decision_output.parent.mkdir(parents=True, exist_ok=True)
        owner_decision_package("; ".join(blockers), work_package, args.owner_decision_output)
        return {
            "ok": True,
            "result_status": "owner_decision_required",
            "prompt_generated": False,
            "owner_decision_package": str(args.owner_decision_output),
            "selected_work_package": work_package,
            "selected_action": work_package,
            "auto_merge_allowed": False,
            "admin_merge_allowed": False,
            "blockers": blockers,
            "warnings": warnings,
            "details": details,
        }

    args.prompt_output.parent.mkdir(parents=True, exist_ok=True)
    prompt_for_work_package(work_package or "", state, args.prompt_output)
    return {
        "ok": True,
        "result_status": "next_prompt_generated",
        "prompt_generated": True,
        "prompt_path": str(args.prompt_output),
        "selected_work_package": work_package,
        "selected_action": work_package,
        "auto_merge_allowed": False,
        "admin_merge_allowed": False,
        "blockers": [],
        "warnings": warnings,
        "details": details,
    }


def write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Codex Autopilot Tick Report",
            "",
            f"- result_status: {report['result_status']}",
            f"- prompt_generated: {str(report.get('prompt_generated', False)).lower()}",
            f"- selected_work_package: {report.get('selected_work_package', report.get('selected_action'))}",
            f"- auto_merge_allowed: {str(report.get('auto_merge_allowed', False)).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report.get("blockers", [])),
            "",
            "## Warnings",
            *(f"- {item}" for item in report.get("warnings", [])),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--action")
    parser.add_argument("--prompt-output", type=Path, default=PROMPT_DEFAULT)
    parser.add_argument("--owner-decision-output", type=Path, default=OWNER_DECISION_DEFAULT)
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    parser.add_argument("--lock-file", type=Path, default=LOG_DIR_DEFAULT / "tick.lock")
    parser.add_argument("--skip-github", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    args.lock_file.parent.mkdir(parents=True, exist_ok=True)
    with args.lock_file.open("w", encoding="utf-8") as lock_handle:
        try:
            fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            report = {
                "ok": True,
                "result_status": "already_running",
                "prompt_generated": False,
                "auto_merge_allowed": False,
                "admin_merge_allowed": False,
                "blockers": ["single-flight lock is held"],
                "warnings": [],
                "details": {"lock_file": str(args.lock_file)},
            }
            write_outputs(report, args.output_json, args.output_md)
            print(json.dumps(report, ensure_ascii=False))
            return 0
        report = build_tick_report(args)
        write_outputs(report, args.output_json, args.output_md)
        print(json.dumps(report, ensure_ascii=False))
        return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
