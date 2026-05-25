from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_autonomous_development_loop as checker


ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "docs/development/phase_execution_state.yaml"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"
DOC = ROOT / "docs/development/autonomous_development_loop.md"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_phase_execution_state_fields_complete() -> None:
    data = checker.load_yaml(STATE)
    assert checker.REQUIRED_STATE_FIELDS <= set(data)
    assert data["current_phase"] == "phase_5_external_adapter"
    assert data["active_candidate"] == "/wecom/external-contact/callback"
    assert data["capability_owner"] == "aicrm_next.integration_gateway"
    assert data["last_merged_pr"] == "#724"


def test_completed_steps_include_phase_4al_readiness_gate() -> None:
    data = checker.load_yaml(STATE)
    assert "phase_4al_staging_execution_readiness_gate_completed" in set(data["completed_steps"])
    assert "action_templates_staging_owner_decision_package_created" in set(data["completed_steps"])
    assert "phase_4an_task_groups_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4ao_task_groups_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4ap_task_groups_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4aq_task_groups_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4ar_workflows_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4as_workflows_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4at_workflows_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4au_workflows_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4av_workflow_nodes_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4aw_workflow_nodes_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4ax_workflow_nodes_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4az_next_internal_write_candidate_selection_completed" in set(data["completed_steps"])
    assert "phase_4ba_tasks_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4bb_tasks_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4bc_tasks_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4bd_tasks_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4be_agents_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4bf_agents_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4bg_agents_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4bh_agents_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4bi_agent_outputs_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4bj_agent_outputs_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4bk_agent_outputs_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4bm_agent_runs_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4bn_agent_runs_schema_route_surface_confirmation_completed" in set(data["completed_steps"])
    assert "phase_4bo_agent_runs_fixture_native_contract_planning_completed" in set(data["completed_steps"])
    assert "phase_4bp_agent_runs_fixture_native_implementation_owner_decision_completed" in set(data["completed_steps"])
    assert "phase_4bq_agent_replay_metadata_planning_completed" in set(data["completed_steps"])
    assert "phase_4br_task_groups_fixture_native_list_create_runtime_completed" in set(data["completed_steps"])
    assert "phase_4bs_workflows_fixture_native_list_create_runtime_completed" in set(data["completed_steps"])
    assert "phase_4bt_workflow_nodes_fixture_native_list_create_runtime_completed" in set(data["completed_steps"])
    assert "phase_4bu_tasks_fixture_native_list_create_runtime_completed" in set(data["completed_steps"])
    assert "phase_4bv_agents_fixture_native_list_create_runtime_completed" in set(data["completed_steps"])
    assert "phase_4bw_agent_outputs_fixture_native_list_detail_runtime_completed" in set(data["completed_steps"])
    assert "phase_4bx_agent_runs_fixture_native_list_detail_runtime_completed" in set(data["completed_steps"])
    assert "phase_4by_agent_replay_discovery_contract_bundle_completed" in set(data["completed_steps"])
    assert "phase_4ca_task_groups_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4cb_workflows_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4cc_workflow_nodes_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4cd_tasks_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4ce_agents_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4cf_agent_outputs_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4cg_agent_runs_repository_adapter_parity_completed" in set(data["completed_steps"])
    assert "phase_4ch_task_groups_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4ci_workflows_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cj_workflow_nodes_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4ck_tasks_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cl_agents_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cm_agent_outputs_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cn_agent_runs_staging_readiness_completed" in set(data["completed_steps"])
    assert "phase_4co_task_groups_production_dry_run_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cp_workflows_production_dry_run_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cq_workflow_nodes_production_dry_run_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cr_tasks_production_dry_run_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cs_agent_runs_production_dry_run_readiness_completed" in set(data["completed_steps"])
    assert "phase_4ct_agent_outputs_production_dry_run_readiness_completed" in set(data["completed_steps"])
    assert "phase_4cu_internal_write_acceptance_review_completed" in set(data["completed_steps"])
    assert "phase_4cv_phase5_readiness_entry_completed" in set(data["completed_steps"])
    assert "phase_5a_wecom_tag_adapter_contract_completed" in set(data["completed_steps"])
    assert "phase_5b_wecom_tag_fake_stub_adapter_completed" in set(data["completed_steps"])
    assert "phase_5c_wecom_tag_live_adapter_behind_flag_completed" in set(data["completed_steps"])
    assert "phase_5d_wecom_tag_staging_live_canary_evidence_completed" in set(data["completed_steps"])
    assert "phase_5e_wecom_tag_production_canary_readiness_completed" in set(data["completed_steps"])
    assert "phase_5f_wecom_tag_production_live_canary_execution_completed" in set(data["completed_steps"])
    assert "phase_5g_wecom_tag_family_acceptance_completed" in set(data["completed_steps"])
    assert "phase_5h_wecom_customer_contact_adapter_contract_completed" in set(data["completed_steps"])
    assert "phase_5i_wecom_customer_contact_fake_stub_adapter_completed" in set(data["completed_steps"])
    assert "phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag_completed" in set(data["completed_steps"])
    assert "phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence_completed" in set(data["completed_steps"])
    assert "phase_5l_wecom_customer_contact_production_callback_canary_readiness_completed" in set(data["completed_steps"])


def test_next_allowed_actions_are_phase_5m_wecom_customer_contact_family_acceptance_only() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["next_allowed_actions"]) == checker.ALLOWED_NEXT_ACTIONS


def test_forbidden_without_owner_approval_covers_high_risk_actions() -> None:
    data = checker.load_yaml(STATE)
    forbidden = {item.lower() for item in data["forbidden_without_owner_approval"]}
    assert checker.REQUIRED_FORBIDDEN <= forbidden


def test_work_package_policy_sets_bounded_low_risk_granularity() -> None:
    data = checker.load_yaml(STATE)
    policy = data["work_package_policy"]
    assert policy["selection_unit"] == "compressed_bounded_bundle"
    assert policy["target_duration_minutes_min"] == 15
    assert policy["target_duration_minutes_max"] == 20
    for field in checker.REQUIRED_WORK_PACKAGE_POLICY_TRUE:
        assert policy[field] is True
    assert policy["admin_merge_for_owner_decision_package_allowed"] is False


def test_active_candidate_in_manifest_and_backlog() -> None:
    candidate = checker.load_yaml(STATE)["active_candidate"]
    if candidate not in {"phase_4_internal_write_aggregate", "phase_5_external_adapter_entry"}:
        assert candidate in (ROOT / "docs/route_ownership/production_route_ownership_manifest.yaml").read_text(encoding="utf-8")
        assert candidate in (ROOT / "docs/development/legacy_replacement_backlog.yaml").read_text(encoding="utf-8")


def test_action_templates_not_ready_for_production_switch_or_write() -> None:
    readiness = checker.load_yaml(STATE)["action_templates_readiness"]
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["paused"] is True
    assert readiness["paused_by_pr"] == "#644"
    assert readiness["owner_decision_required"] is True


def test_action_templates_paused_and_task_groups_not_ready_for_production() -> None:
    data = checker.load_yaml(STATE)
    paused = data["paused_candidates"]
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/action-templates*"
        and item["paused_by_pr"] == "#644"
        and item["owner_approval_required"] is True
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/task-groups*"
        and item["owner_approval_required"] is False
        and item["status"] == "fixture_native_list_create_runtime_completed"
        and str(item["paused_by_pr"]).strip()
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/task-groups*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#686"
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflows*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#687"
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflow-nodes*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#688"
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/tasks*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#689"
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agents*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#690"
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-outputs*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#691"
        for item in paused
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-runs*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#692"
        for item in paused
    )
    readiness = data["task_groups_readiness"]
    assert readiness["native_contract_planning_started"] is True
    assert readiness["native_contract_planning_completed"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_create_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {"task_groups_fixture_local_list", "task_groups_fixture_local_metadata_create"}
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_TASK_GROUPS_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_TASK_GROUPS_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CH_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CH_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_runner_completed"] is True
    assert readiness["production_readonly_evidence_gate_completed"] is True
    assert readiness["production_readonly_blocked_evidence_output_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_TASK_GROUPS_READONLY_DRY_RUN_DATABASE_URL"
    assert readiness["production_readonly_approval_flag"] == "AICRM_PHASE4CO_PRODUCTION_READONLY_DRY_RUN_APPROVED"
    assert readiness["production_readonly_config_review_flag"] == "AICRM_PHASE4CO_PRODUCTION_CONFIG_REVIEWED"
    assert readiness["production_readonly_db_connection_attempted_by_default"] is False
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["owner_decision_required"] is False
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/task-groups*"
        and item["slice"] == "task_groups_staging_readiness_preflight"
        for item in data["staging_readiness_slices"]
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/task-groups*"
        and item["slice"] == "task_groups_production_readonly_dry_run_readiness"
        for item in data["production_dry_run_readiness_slices"]
    )


def test_workflows_runtime_completed_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    readiness = data["workflows_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_create_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {"workflows_fixture_local_list", "workflows_fixture_local_metadata_create"}
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_WORKFLOWS_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_WORKFLOWS_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CI_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CI_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_runner_completed"] is True
    assert readiness["production_readonly_evidence_gate_completed"] is True
    assert readiness["production_readonly_blocked_evidence_output_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_WORKFLOWS_READONLY_DRY_RUN_DATABASE_URL"
    assert readiness["production_readonly_approval_flag"] == "AICRM_PHASE4CP_PRODUCTION_READONLY_DRY_RUN_APPROVED"
    assert readiness["production_readonly_config_review_flag"] == "AICRM_PHASE4CP_PRODUCTION_CONFIG_REVIEWED"
    assert readiness["production_readonly_db_connection_attempted_by_default"] is False
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["owner_decision_required"] is False
    assert readiness["paused"] is False
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflows*"
        and item["slice"] == "workflows_staging_readiness_preflight"
        for item in data["staging_readiness_slices"]
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflows*"
        and item["slice"] == "workflows_production_readonly_dry_run_readiness"
        for item in data["production_dry_run_readiness_slices"]
    )


def test_workflow_nodes_runtime_completed_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflow-nodes*"
        and item["owner_approval_required"] is False
        and item["status"] == "fixture_native_list_create_runtime_completed"
        and str(item["paused_by_pr"]).strip()
        for item in data["paused_candidates"]
    )
    readiness = data["workflow_nodes_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_create_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {
        "workflow_nodes_fixture_local_list",
        "workflow_nodes_fixture_local_metadata_create",
    }
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_WORKFLOW_NODES_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_WORKFLOW_NODES_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CJ_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CJ_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert readiness["paused"] is False
    assert str(readiness["paused_by_pr"]).strip()
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflow-nodes*"
        and item["slice"] == "workflow_nodes_staging_readiness_preflight"
        for item in data["staging_readiness_slices"]
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/workflow-nodes*"
        and item["slice"] == "workflow_nodes_production_readonly_dry_run_readiness"
        for item in data["production_dry_run_readiness_slices"]
    )
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_runner_completed"] is True
    assert readiness["production_readonly_evidence_gate_completed"] is True
    assert readiness["production_readonly_blocked_evidence_output_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_WORKFLOW_NODES_READONLY_DRY_RUN_DATABASE_URL"
    assert readiness["production_readonly_approval_flag"] == "AICRM_PHASE4CQ_PRODUCTION_READONLY_DRY_RUN_APPROVED"
    assert readiness["production_readonly_config_review_flag"] == "AICRM_PHASE4CQ_PRODUCTION_CONFIG_REVIEWED"
    assert readiness["production_readonly_db_connection_attempted_by_default"] is False


def test_tasks_runtime_completed_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/tasks*"
        and item["owner_approval_required"] is False
        and item["status"] == "fixture_native_list_create_runtime_completed"
        and str(item["paused_by_pr"]).strip()
        for item in data["paused_candidates"]
    )
    readiness = data["tasks_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_create_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {
        "tasks_fixture_local_list",
        "tasks_fixture_local_metadata_create",
    }
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_TASKS_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_TASKS_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CK_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CK_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/tasks*"
        and item["slice"] == "tasks_production_readonly_dry_run_readiness"
        for item in data["production_dry_run_readiness_slices"]
    )
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_runner_completed"] is True
    assert readiness["production_readonly_evidence_gate_completed"] is True
    assert readiness["production_readonly_blocked_evidence_output_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_TASKS_READONLY_DRY_RUN_DATABASE_URL"
    assert readiness["production_readonly_approval_flag"] == "AICRM_PHASE4CR_PRODUCTION_READONLY_DRY_RUN_APPROVED"
    assert readiness["production_readonly_config_review_flag"] == "AICRM_PHASE4CR_PRODUCTION_CONFIG_REVIEWED"
    assert readiness["production_readonly_db_connection_attempted_by_default"] is False
    assert readiness["paused"] is False
    assert str(readiness["paused_by_pr"]).strip()
    assert readiness["run_due_excluded"] is True
    assert readiness["task_execution_excluded"] is True
    assert readiness["workflow_execution_excluded"] is True
    assert readiness["timer_execution_excluded"] is True
    assert readiness["outbound_send_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/tasks*"
        and item["slice"] == "tasks_staging_readiness_preflight"
        for item in data["staging_readiness_slices"]
    )


def test_agents_runtime_completed_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agents*"
        and item["owner_approval_required"] is False
        and item["status"] == "fixture_native_list_create_runtime_completed"
        and str(item["paused_by_pr"]).strip()
        for item in data["paused_candidates"]
    )
    readiness = data["agents_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_create_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {
        "agents_fixture_local_list",
        "agents_fixture_local_metadata_create",
    }
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["paused"] is False
    assert readiness["paused_by_pr"] == "#681"
    assert readiness["agent_run_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["deepseek_adapter_excluded"] is True
    assert readiness["openclaw_mcp_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is True
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_AGENTS_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_AGENTS_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CL_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CL_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_agent_outputs_fixture_runtime_completed_with_production_readonly_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert data["active_candidate"] == "/wecom/external-contact/callback"
    readiness = data["agent_outputs_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_detail_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {"agent_outputs_fixture_local_list", "agent_outputs_fixture_local_detail"}
    assert readiness["guarded_disabled_runtime_slices"] == []
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["repository_adapter_backend_flag"] == "AICRM_AGENT_OUTPUTS_REPO_BACKEND"
    assert readiness["repository_adapter_test_db_url_flag"] == "AICRM_AGENT_OUTPUTS_TEST_DATABASE_URL"
    assert readiness["repository_adapter_staging_db_url_flag"] == "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL"
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is False
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["paused"] is False
    assert readiness["paused_by_pr"] == "#683"
    assert readiness["export_job_creation_excluded"] is True
    assert readiness["file_download_excluded"] is True
    assert readiness["agent_run_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["deepseek_adapter_excluded"] is True
    assert readiness["openclaw_mcp_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_AGENT_OUTPUTS_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_AGENT_OUTPUTS_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CM_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CM_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-outputs*"
        and item["slice"] == "agent_outputs_production_readonly_dry_run_readiness"
        for item in data["production_dry_run_readiness_slices"]
    )
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_runner_completed"] is True
    assert readiness["production_readonly_evidence_gate_completed"] is True
    assert readiness["production_readonly_blocked_evidence_output_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_AGENT_OUTPUTS_READONLY_DRY_RUN_DATABASE_URL"
    assert readiness["production_readonly_approval_flag"] == "AICRM_PHASE4CT_PRODUCTION_READONLY_DRY_RUN_APPROVED"
    assert readiness["production_readonly_config_review_flag"] == "AICRM_PHASE4CT_PRODUCTION_CONFIG_REVIEWED"
    assert readiness["production_readonly_db_connection_attempted_by_default"] is False
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_agent_runs_fixture_runtime_completed_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-outputs*"
        and item["owner_approval_required"] is False
        and item["status"] == "fixture_native_list_detail_runtime_completed"
        and item["paused_by_pr"] == "#683"
        for item in data["paused_candidates"]
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-runs*"
        and item["owner_approval_required"] is False
        and item["status"] == "fixture_native_list_detail_runtime_completed"
        and item["paused_by_pr"] == "#684"
        for item in data["paused_candidates"]
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-runs*"
        and item["owner_approval_required"] is False
        and item["status"] == "repository_adapter_parity_completed"
        and item["paused_by_pr"] == "#692"
        for item in data["paused_candidates"]
    )
    readiness = data["agent_runs_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is False
    assert readiness["fixture_native_list_detail_runtime_completed"] is True
    assert readiness["owner_decision_required"] is False
    assert set(readiness["implemented_runtime_slices"]) == {"agent_runs_fixture_local_list", "agent_runs_fixture_local_detail"}
    assert readiness["guarded_disabled_runtime_slices"] == []
    assert readiness["repository_adapter_parity_completed"] is True
    assert readiness["repository_adapter_backend_flag"] == "AICRM_AGENT_RUNS_REPO_BACKEND"
    assert readiness["repository_adapter_test_db_url_flag"] == "AICRM_AGENT_RUNS_TEST_DATABASE_URL"
    assert readiness["repository_adapter_staging_db_url_flag"] == "AICRM_AGENT_RUNS_STAGING_DATABASE_URL"
    assert readiness["no_database_url_fallback"] is True
    assert readiness["default_backend_fixture_local"] is True
    assert readiness["test_db_parity_harness_completed"] is True
    assert readiness["idempotency_audit_rollback_scaffold_completed"] is False
    assert readiness["staging_readiness_bundle_completed"] is True
    assert readiness["staging_readiness_preflight_completed"] is True
    assert readiness["staging_evidence_gate_completed"] is True
    assert readiness["staging_blocked_evidence_output_completed"] is True
    assert readiness["staging_database_url_flag"] == "AICRM_AGENT_RUNS_STAGING_DATABASE_URL"
    assert readiness["staging_backend_flag"] == "AICRM_AGENT_RUNS_REPO_BACKEND"
    assert readiness["staging_approval_flag"] == "AICRM_PHASE4CN_STAGING_SMOKE_APPROVED"
    assert readiness["staging_write_approval_flag"] == "AICRM_PHASE4CN_STAGING_WRITE_APPROVED"
    assert readiness["staging_smoke_executed"] is False
    assert readiness["staging_write_executed"] is False
    assert readiness["staging_db_connection_attempted_by_default"] is False
    assert readiness["production_guard_blocks_fixture_success"] is True
    assert readiness["paused"] is False
    assert readiness["paused_by_pr"] == "#684"
    assert readiness["run_creation_excluded"] is True
    assert readiness["run_execution_excluded"] is True
    assert readiness["replay_execution_excluded"] is True
    assert readiness["orchestration_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["deepseek_adapter_excluded"] is True
    assert readiness["openclaw_mcp_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-runs*"
        and item["slice"] == "agent_runs_staging_readiness_preflight"
        for item in data["staging_readiness_slices"]
    )
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-runs*"
        and item["slice"] == "agent_runs_production_readonly_dry_run_readiness"
        for item in data["production_dry_run_readiness_slices"]
    )
    assert readiness["production_dry_run_readiness_bundle_completed"] is True
    assert readiness["production_readonly_dry_run_runner_completed"] is True
    assert readiness["production_readonly_evidence_gate_completed"] is True
    assert readiness["production_readonly_blocked_evidence_output_completed"] is True
    assert readiness["production_readonly_dry_run_executed"] is False
    assert readiness["production_readonly_db_url_flag"] == "AICRM_AGENT_RUNS_READONLY_DRY_RUN_DATABASE_URL"
    assert readiness["production_readonly_approval_flag"] == "AICRM_PHASE4CS_PRODUCTION_READONLY_DRY_RUN_APPROVED"
    assert readiness["production_readonly_config_review_flag"] == "AICRM_PHASE4CS_PRODUCTION_CONFIG_REVIEWED"
    assert readiness["production_readonly_db_connection_attempted_by_default"] is False


def test_agent_replay_selected_for_metadata_planning_without_runtime_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert any(
        item["route_family"] == "/api/admin/automation-conversion/agent-replay"
        and item["owner_approval_required"] is True
        and item["status"] == "discovery_contract_completed_replay_runtime_deferred"
        and item["paused_by_pr"] == "#685"
        for item in data["paused_candidates"]
    )
    readiness = data["agent_replay_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_runtime_deferred"] is True
    assert readiness["discovery_contract_bundle_completed"] is True
    assert readiness["paused"] is True
    assert readiness["paused_by_pr"] == "#685"
    assert readiness["replay_execution_excluded"] is True
    assert readiness["run_creation_excluded"] is True
    assert readiness["run_execution_excluded"] is True
    assert readiness["orchestration_execution_excluded"] is True
    assert readiness["agent_output_generation_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["deepseek_adapter_excluded"] is True
    assert readiness["openclaw_mcp_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
    assert readiness["owner_decision_required"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_stop_conditions_complete() -> None:
    data = checker.load_yaml(STOP)
    ids = {item["id"] for item in data["high_risk_stop_conditions"]}
    assert checker.STOP_IDS <= ids


def test_docs_include_required_autopilot_contract_sections() -> None:
    text = DOC.read_text(encoding="utf-8")
    for section in ("Business value", "Business continuity", "Risk / rollback", "Next action"):
        assert section in text


def test_only_phase4_runtime_files_changed_if_git_diff_available() -> None:
    proc = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        return
    changed = {line.strip() for line in proc.stdout.splitlines() if line.strip()}
    assert not any(path.startswith("aicrm_next/") and path not in checker.PHASE4_ALLOWED_RUNTIME_FILES for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("deploy/") for path in changed)
