#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PR_BODY = ROOT / "docs/development/autonomous_development_loop.md"
STOP = ROOT / "docs/development/autonomous_stop_conditions.yaml"

REQUIRED_PR_BODY_SECTIONS = {
    "Business value",
    "Business continuity",
    "Risk / rollback",
    "Next action",
}
LOW_RISK_PREFIXES = (
    "docs/development/",
    "tools/check_",
    "tests/test_",
)
LOW_RISK_EXACT = {
    "tools/run_codex_autopilot_tick.py",
    "tools/run_phase4ca_task_groups_adapter_parity.py",
    "tools/run_phase4cb_workflows_adapter_parity.py",
    "tools/run_phase4cc_workflow_nodes_adapter_parity.py",
    "tools/run_phase4cd_tasks_adapter_parity.py",
    "tools/run_phase4ce_agents_adapter_parity.py",
    "tools/run_phase4cf_agent_outputs_adapter_parity.py",
    "tools/run_phase4cg_agent_runs_adapter_parity.py",
    "tools/run_phase4ch_task_groups_staging_readiness.py",
    "tools/run_phase4ci_workflows_staging_readiness.py",
    "tools/run_phase4cj_workflow_nodes_staging_readiness.py",
    "tools/run_phase4ck_tasks_staging_readiness.py",
    "tools/run_phase4cl_agents_staging_readiness.py",
    "tools/run_phase4cm_agent_outputs_staging_readiness.py",
    "tools/run_phase4cn_agent_runs_staging_readiness.py",
    "tools/run_phase4co_task_groups_production_readonly_dry_run.py",
    "tools/run_phase4cp_workflows_production_readonly_dry_run.py",
    "tools/run_phase4cq_workflow_nodes_production_readonly_dry_run.py",
    "tools/run_phase4cr_tasks_production_readonly_dry_run.py",
    "tools/run_phase4cs_agent_runs_production_readonly_dry_run.py",
    "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py",
    "tools/run_phase5a_wecom_tag_adapter_contract_evidence.py",
    "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py",
    "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py",
    "tools/run_phase5c_wecom_tag_live_staging_evidence.py",
    "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py",
    "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py",
    "tools/run_phase5d_wecom_tag_production_live_readiness_review.py",
    "tools/run_phase5e_wecom_tag_production_canary_readiness.py",
    "tools/run_phase5f_wecom_tag_production_live_canary_execution.py",
    "tools/run_phase5f_wecom_tag_production_canary_cleanup.py",
    "tools/run_phase5h_wecom_customer_contact_adapter_contract_evidence.py",
    "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py",
    "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py",
    "tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py",
    "tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py",
    "tools/run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
    "tools/run_phase5k_wecom_customer_contact_production_callback_readiness_review.py",
    "tools/run_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
    "tools/run_phase5n_oauth_identity_adapter_contract_evidence.py",
    "tools/run_phase5o_oauth_identity_fake_stub_staging_smoke.py",
    "tools/run_phase5o_oauth_identity_fake_stub_production_dry_run.py",
    "tools/run_phase5p_oauth_identity_live_staging_evidence.py",
    "tools/run_phase5p_oauth_identity_live_production_dry_run_gate.py",
    "tools/run_phase5q_oauth_identity_staging_live_canary_evidence.py",
    "tools/run_phase5q_oauth_identity_production_live_readiness_review.py",
    "tools/run_phase5r_oauth_identity_production_canary_readiness.py",
    "tools/run_phase5s_oauth_identity_production_live_canary_execution.py",
    "tools/run_phase5s_oauth_identity_production_canary_cleanup.py",
    "tools/run_phase5u_media_upload_fake_stub_staging_smoke.py",
    "tools/run_phase5u_media_upload_fake_stub_production_dry_run.py",
    "tools/run_phase5v_media_upload_live_staging_evidence.py",
    "tools/run_phase5v_media_upload_live_production_dry_run_gate.py",
    "tools/run_phase5w_media_upload_staging_live_canary_evidence.py",
    "tools/run_phase5w_media_upload_production_live_readiness_review.py",
    "tools/run_phase5x_media_upload_production_canary_readiness_execution.py",
    "tools/run_phase5x_media_upload_production_canary_cleanup.py",
    "tools/run_phase5z_payment_commerce_fake_stub_evidence.py",
    "tools/run_phase5aa_payment_commerce_live_staging_evidence.py",
    "tools/run_phase5aa_payment_commerce_live_production_dry_run_gate.py",
    "tools/run_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
    "tools/run_phase5ab_payment_commerce_production_readiness_review.py",
    "tools/run_phase5ac_payment_commerce_production_canary_readiness.py",
    "tools/run_phase5ad_payment_commerce_production_canary_tooling.py",
    "tools/run_phase5ad_payment_commerce_production_canary_cleanup.py",
    "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_staging_smoke.py",
    "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_production_dry_run.py",
    "tools/run_phase5ag_openclaw_mcp_ai_assist_live_staging_evidence.py",
    "tools/run_phase5ag_openclaw_mcp_ai_assist_live_production_dry_run_gate.py",
    "tools/run_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
    "tools/run_phase5ah_openclaw_mcp_ai_assist_production_readiness_review.py",
    "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
    "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup.py",
    "tools/run_phase5ak_questionnaire_external_submit_fake_stub_staging_smoke.py",
    "tools/run_phase5ak_questionnaire_external_submit_fake_stub_production_dry_run.py",
    "tools/run_phase5al_questionnaire_external_submit_live_staging_evidence.py",
    "tools/run_phase5al_questionnaire_external_submit_live_production_dry_run_gate.py",
    "tools/run_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
    "tools/run_phase5am_questionnaire_external_submit_production_readiness_review.py",
    "tools/run_phase5an_questionnaire_external_submit_production_canary_readiness.py",
    "tools/run_phase5an_questionnaire_external_submit_production_canary_cleanup.py",
    "tools/run_phase6c_task_groups_owner_switch_canary.py",
    "tools/run_phase6c_task_groups_shadow_compare.py",
    "tools/run_phase6c_task_groups_owner_switch_rollback.py",
    "tools/run_phase6d_internal_metadata_owner_switch_batch.py",
    "tools/run_phase6g_media_adapter_enablement_gate.py",
    "tools/run_phase6g_wecom_tags_enablement_gate.py",
    "tools/run_phase6g_openclaw_mcp_enablement_gate.py",
    "tools/run_phase6k_single_scope_execution_canary.py",
    "tools/run_phase6h_production_compat_exact_route_shadow_compare.py",
    "scripts/codex_autopilot_tick.sh",
}
AUTOPILOT_DELIVERABLE_RUNTIME_PATHS = {
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
    "aicrm_next/automation_engine/group_ops/domain.py",
    "aicrm_next/integration_gateway/legacy_flask_facade.py",
    "aicrm_next/integration_gateway/wecom_group_adapter.py",
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
}
OWNER_DECISION_PACKAGE_PATHS = {
    "docs/development/phase_4am_action_templates_owner_decision_package.md",
    "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
    "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
}
POLICY_FILES_CAN_DEFINE_STOP_TERMS = {
        "docs/development/autonomous_development_loop.md",
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
        "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.md",
        "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.yaml",
        "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.md",
        "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.yaml",
        "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.md",
        "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.yaml",
        "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.md",
        "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.yaml",
        "docs/development/phase_5n_oauth_identity_adapter_contract.md",
        "docs/development/phase_5n_oauth_identity_adapter_contract.yaml",
        "docs/development/phase_5o_oauth_identity_fake_stub_adapter.md",
        "docs/development/phase_5o_oauth_identity_fake_stub_adapter.yaml",
        "docs/development/phase_5p_oauth_identity_live_adapter_behind_flag.md",
        "docs/development/phase_5p_oauth_identity_live_adapter_behind_flag.yaml",
        "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.md",
        "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.yaml",
        "docs/development/phase_5r_oauth_identity_production_canary_readiness.md",
        "docs/development/phase_5r_oauth_identity_production_canary_readiness.yaml",
        "docs/development/phase_5s_oauth_identity_production_live_canary_execution.md",
        "docs/development/phase_5s_oauth_identity_production_live_canary_execution.yaml",
        "docs/development/phase_5t_oauth_identity_family_acceptance.md",
        "docs/development/phase_5t_oauth_identity_family_acceptance.yaml",
        "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.md",
        "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.yaml",
        "docs/development/phase_5v_media_upload_live_adapter_behind_flag.md",
        "docs/development/phase_5v_media_upload_live_adapter_behind_flag.yaml",
        "docs/development/phase_5w_media_upload_staging_live_canary_evidence.md",
        "docs/development/phase_5w_media_upload_staging_live_canary_evidence.yaml",
        "docs/development/phase_5x_media_upload_production_canary_readiness_execution.md",
        "docs/development/phase_5x_media_upload_production_canary_readiness_execution.yaml",
        "docs/development/phase_5y_media_upload_family_acceptance.md",
        "docs/development/phase_5y_media_upload_family_acceptance.yaml",
        "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.md",
        "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.yaml",
        "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.md",
        "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.yaml",
        "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.md",
        "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.yaml",
        "docs/development/phase_5ac_payment_commerce_production_canary_readiness.md",
        "docs/development/phase_5ac_payment_commerce_production_canary_readiness.yaml",
        "docs/development/phase_5ad_payment_commerce_production_canary_tooling.md",
        "docs/development/phase_5ad_payment_commerce_production_canary_tooling.yaml",
        "docs/development/phase_5ae_payment_commerce_family_acceptance.md",
        "docs/development/phase_5ae_payment_commerce_family_acceptance.yaml",
        "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.md",
        "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.yaml",
        "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.md",
        "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.yaml",
        "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.md",
        "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.yaml",
        "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.md",
        "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.yaml",
        "docs/development/phase_5aj_openclaw_mcp_ai_assist_family_acceptance.md",
        "docs/development/phase_5aj_openclaw_mcp_ai_assist_family_acceptance.yaml",
        "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.md",
        "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.yaml",
        "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.md",
        "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.yaml",
        "docs/development/phase_5am_questionnaire_external_submit_staging_canary_evidence.md",
        "docs/development/phase_5am_questionnaire_external_submit_staging_canary_evidence.yaml",
        "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.md",
        "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.yaml",
        "docs/development/phase_5ao_questionnaire_external_submit_family_acceptance.md",
        "docs/development/phase_5ao_questionnaire_external_submit_family_acceptance.yaml",
        "docs/development/phase_5_aggregate_acceptance_review.md",
        "docs/development/phase_5_aggregate_acceptance_review.yaml",
        "docs/development/phase_6a_owner_production_compat_readiness.md",
        "docs/development/phase_6a_owner_production_compat_readiness.yaml",
        "docs/development/phase_6b_task_groups_owner_switch_canary_plan.md",
        "docs/development/phase_6b_task_groups_owner_switch_canary_plan.yaml",
        "docs/development/phase_6c_task_groups_owner_switch_tooling.md",
        "docs/development/phase_6c_task_groups_owner_switch_tooling.yaml",
        "docs/development/phase_6d_internal_metadata_owner_switch_batch.md",
        "docs/development/phase_6d_internal_metadata_owner_switch_batch.yaml",
        "docs/development/phase_6e_internal_owner_switch_acceptance.md",
        "docs/development/phase_6e_internal_owner_switch_acceptance.yaml",
        "docs/development/phase_6f_external_adapter_enablement_readiness.md",
        "docs/development/phase_6f_external_adapter_enablement_readiness.yaml",
        "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.md",
        "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.yaml",
        "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.md",
        "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.yaml",
        "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.md",
        "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.yaml",
        "docs/development/phase_6j_timer_execution_readiness.md",
        "docs/development/phase_6j_timer_execution_readiness.yaml",
        "docs/development/phase_6k_single_scope_execution_canary_tooling.md",
        "docs/development/phase_6k_single_scope_execution_canary_tooling.yaml",
        "docs/development/phase_6l_phase6_aggregate_acceptance.md",
        "docs/development/phase_6l_phase6_aggregate_acceptance.yaml",
        "docs/development/phase_7a_legacy_retirement_readiness.md",
        "docs/development/phase_7a_legacy_retirement_readiness.yaml",
        "docs/development/phase_7b_baseline_legacy_import_remediation.md",
        "docs/development/phase_7b_baseline_legacy_import_remediation.yaml",
        "docs/development/phase_7c_delete_ready_candidate_selection.md",
        "docs/development/phase_7c_delete_ready_candidate_selection.yaml",
        "docs/development/phase_7d_first_safe_cleanup.md",
        "docs/development/phase_7d_first_safe_cleanup.yaml",
        "docs/development/phase_7e_fallback_cleanup_readiness.md",
        "docs/development/phase_7e_fallback_cleanup_readiness.yaml",
        "docs/development/phase_7f_production_compat_cleanup_readiness.md",
        "docs/development/phase_7f_production_compat_cleanup_readiness.yaml",
        "docs/development/phase_7g_first_exact_route_fallback_removal_canary.md",
        "docs/development/phase_7g_first_exact_route_fallback_removal_canary.yaml",
        "docs/development/phase_7h_first_exact_route_production_compat_cleanup_canary.md",
        "docs/development/phase_7h_first_exact_route_production_compat_cleanup_canary.yaml",
        "docs/development/phase_7i_legacy_runtime_deletion_readiness.md",
        "docs/development/phase_7i_legacy_runtime_deletion_readiness.yaml",
        "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.md",
        "docs/development/phase_7j_legacy_runtime_cleanup_blocker_acceptance.yaml",
        "docs/development/phase_7k_final_route_ownership_manifest_cleanup.md",
        "docs/development/phase_7k_final_route_ownership_manifest_cleanup.yaml",
        "docs/development/phase_7l_final_legacy_retirement_acceptance.md",
        "docs/development/phase_7l_final_legacy_retirement_acceptance.yaml",
        "docs/development/post_phase7_new_feature_development_rules.md",
        "docs/development/post_phase7_new_feature_development_rules.yaml",
        "docs/development/phase_4br_task_groups_fixture_runtime.md",
        "docs/development/phase_4bs_workflows_fixture_runtime.md",
        "docs/development/phase_4bt_workflow_nodes_fixture_runtime.md",
        "docs/development/phase_4bu_tasks_fixture_runtime.md",
        "docs/development/phase_execution_state.yaml",
        "docs/development/autonomous_stop_conditions.yaml",
        "aicrm_next/integration_gateway/legacy_flask_facade.py",
        "scripts/codex_autopilot_tick.sh",
        "tools/check_autonomous_development_loop.py",
        "tools/check_automerge_eligibility.py",
        "tools/check_legacy_facade_growth_freeze.py",
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
        "tools/check_phase5i_wecom_customer_contact_fake_stub_adapter.py",
        "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py",
        "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py",
        "tests/test_phase5i_wecom_customer_contact_fake_stub_adapter.py",
        "tools/check_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
        "tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py",
        "tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py",
        "tests/test_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
        "tools/check_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/run_phase5k_wecom_customer_contact_production_callback_readiness_review.py",
        "tests/test_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/check_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tools/run_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tests/test_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tools/check_phase5m_wecom_customer_contact_callback_family_acceptance.py",
        "tests/test_phase5m_wecom_customer_contact_callback_family_acceptance.py",
        "tools/check_phase5n_oauth_identity_adapter_contract.py",
        "tools/run_phase5n_oauth_identity_adapter_contract_evidence.py",
        "tests/test_phase5n_oauth_identity_adapter_contract.py",
        "tools/check_phase5o_oauth_identity_fake_stub_adapter.py",
        "tools/run_phase5o_oauth_identity_fake_stub_staging_smoke.py",
        "tools/run_phase5o_oauth_identity_fake_stub_production_dry_run.py",
        "tests/test_phase5o_oauth_identity_fake_stub_adapter.py",
        "tools/check_phase5p_oauth_identity_live_adapter_behind_flag.py",
        "tools/run_phase5p_oauth_identity_live_staging_evidence.py",
        "tools/run_phase5p_oauth_identity_live_production_dry_run_gate.py",
        "tests/test_phase5p_oauth_identity_live_adapter_behind_flag.py",
        "tools/check_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/run_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/run_phase5q_oauth_identity_production_live_readiness_review.py",
        "tests/test_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/check_phase5r_oauth_identity_production_canary_readiness.py",
        "tools/run_phase5r_oauth_identity_production_canary_readiness.py",
        "tests/test_phase5r_oauth_identity_production_canary_readiness.py",
        "tools/check_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/run_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/run_phase5s_oauth_identity_production_canary_cleanup.py",
        "tests/test_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/check_phase5t_oauth_identity_family_acceptance.py",
        "tests/test_phase5t_oauth_identity_family_acceptance.py",
        "tools/check_phase5u_media_upload_adapter_contract_fake_stub.py",
        "tools/run_phase5u_media_upload_fake_stub_staging_smoke.py",
        "tools/run_phase5u_media_upload_fake_stub_production_dry_run.py",
        "tests/test_phase5u_media_upload_adapter_contract_fake_stub.py",
        "tools/check_phase5v_media_upload_live_adapter_behind_flag.py",
        "tools/run_phase5v_media_upload_live_staging_evidence.py",
        "tools/run_phase5v_media_upload_live_production_dry_run_gate.py",
        "tests/test_phase5v_media_upload_live_adapter_behind_flag.py",
        "tools/check_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/run_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/run_phase5w_media_upload_production_live_readiness_review.py",
        "tests/test_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/check_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/run_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/run_phase5x_media_upload_production_canary_cleanup.py",
        "tests/test_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/check_phase5y_media_upload_family_acceptance.py",
        "tests/test_phase5y_media_upload_family_acceptance.py",
        "tools/check_phase5z_payment_commerce_adapter_contract_fake_stub.py",
        "tools/run_phase5z_payment_commerce_fake_stub_evidence.py",
        "tests/test_phase5z_payment_commerce_adapter_contract_fake_stub.py",
        "tools/check_phase5aa_payment_commerce_live_adapter_behind_flag.py",
        "tools/run_phase5aa_payment_commerce_live_staging_evidence.py",
        "tools/run_phase5aa_payment_commerce_live_production_dry_run_gate.py",
        "tests/test_phase5aa_payment_commerce_live_adapter_behind_flag.py",
        "tools/check_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/run_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/run_phase5ab_payment_commerce_production_readiness_review.py",
        "tests/test_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/check_phase5ac_payment_commerce_production_canary_readiness.py",
        "tools/run_phase5ac_payment_commerce_production_canary_readiness.py",
        "tests/test_phase5ac_payment_commerce_production_canary_readiness.py",
        "tools/check_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/run_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/run_phase5ad_payment_commerce_production_canary_cleanup.py",
        "tests/test_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/check_phase5ae_payment_commerce_family_acceptance.py",
        "tests/test_phase5ae_payment_commerce_family_acceptance.py",
        "tools/check_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.py",
        "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_staging_smoke.py",
        "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_production_dry_run.py",
        "tests/test_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.py",
        "tools/check_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.py",
        "tools/run_phase5ag_openclaw_mcp_ai_assist_live_staging_evidence.py",
        "tools/run_phase5ag_openclaw_mcp_ai_assist_live_production_dry_run_gate.py",
        "tests/test_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.py",
        "tools/check_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
        "tools/run_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
        "tools/run_phase5ah_openclaw_mcp_ai_assist_production_readiness_review.py",
        "tests/test_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.py",
        "tools/check_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
        "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
        "tools/run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup.py",
        "tests/test_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness.py",
        "tools/check_phase5aj_openclaw_mcp_ai_assist_family_acceptance.py",
        "tests/test_phase5aj_openclaw_mcp_ai_assist_family_acceptance.py",
        "tools/check_phase5ak_questionnaire_external_submit_contract_fake_stub.py",
        "tools/run_phase5ak_questionnaire_external_submit_fake_stub_staging_smoke.py",
        "tools/run_phase5ak_questionnaire_external_submit_fake_stub_production_dry_run.py",
        "tests/test_phase5ak_questionnaire_external_submit_contract_fake_stub.py",
        "tools/check_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py",
        "tools/run_phase5al_questionnaire_external_submit_live_staging_evidence.py",
        "tools/run_phase5al_questionnaire_external_submit_live_production_dry_run_gate.py",
        "tests/test_phase5al_questionnaire_external_submit_live_adapter_behind_flag.py",
        "tools/check_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
        "tools/run_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
        "tools/run_phase5am_questionnaire_external_submit_production_readiness_review.py",
        "tests/test_phase5am_questionnaire_external_submit_staging_canary_evidence.py",
        "tools/check_phase5an_questionnaire_external_submit_production_canary_readiness.py",
        "tools/run_phase5an_questionnaire_external_submit_production_canary_readiness.py",
        "tools/run_phase5an_questionnaire_external_submit_production_canary_cleanup.py",
        "tests/test_phase5an_questionnaire_external_submit_production_canary_readiness.py",
        "tools/check_phase5ao_questionnaire_external_submit_family_acceptance.py",
        "tests/test_phase5ao_questionnaire_external_submit_family_acceptance.py",
        "tools/check_phase5_aggregate_acceptance_review.py",
        "tools/check_phase6a_owner_production_compat_readiness.py",
        "tools/check_phase6b_task_groups_owner_switch_canary_plan.py",
        "tools/check_phase6c_task_groups_owner_switch_tooling.py",
        "tools/run_phase6c_task_groups_owner_switch_canary.py",
        "tools/run_phase6c_task_groups_shadow_compare.py",
        "tools/run_phase6c_task_groups_owner_switch_rollback.py",
        "tools/check_phase6d_internal_metadata_owner_switch_batch.py",
        "tools/run_phase6d_internal_metadata_owner_switch_batch.py",
        "tools/check_phase6e_internal_owner_switch_acceptance.py",
        "tools/check_phase6f_external_adapter_enablement_readiness.py",
        "tools/check_phase6g_low_risk_external_adapter_enablement_tooling.py",
        "tools/run_phase6g_media_adapter_enablement_gate.py",
        "tools/run_phase6g_wecom_tags_enablement_gate.py",
        "tools/run_phase6g_openclaw_mcp_enablement_gate.py",
        "tools/check_phase6h_production_compat_exact_route_narrowing_readiness.py",
        "tools/run_phase6h_production_compat_exact_route_shadow_compare.py",
        "tools/check_phase6i_external_enablement_and_compat_readiness_acceptance.py",
        "tools/check_phase6j_timer_execution_readiness.py",
        "tools/check_phase6k_single_scope_execution_canary_tooling.py",
        "tools/run_phase6k_single_scope_execution_canary.py",
        "tools/check_phase6l_phase6_aggregate_acceptance.py",
        "tools/check_phase7a_legacy_retirement_readiness.py",
        "tools/check_phase7b_baseline_legacy_import_remediation.py",
        "tools/check_phase7c_delete_ready_candidate_selection.py",
        "tools/check_phase7d_first_safe_cleanup.py",
        "tools/check_phase7e_fallback_cleanup_readiness.py",
        "tools/check_phase7f_production_compat_cleanup_readiness.py",
        "tools/check_phase7g_first_exact_route_fallback_removal_canary.py",
        "tools/check_phase7h_first_exact_route_production_compat_cleanup_canary.py",
        "tools/check_phase7i_legacy_runtime_deletion_readiness.py",
        "tools/check_phase7j_legacy_runtime_cleanup_blocker_acceptance.py",
        "tools/check_phase7k_final_route_ownership_manifest_cleanup.py",
        "tools/check_phase7l_final_legacy_retirement_acceptance.py",
        "tools/check_post_phase7_new_feature_development_rules.py",
        "tests/test_phase5_aggregate_acceptance_review.py",
        "tests/test_phase6a_owner_production_compat_readiness.py",
        "tests/test_phase6b_task_groups_owner_switch_canary_plan.py",
        "tests/test_phase6c_task_groups_owner_switch_tooling.py",
        "tests/test_phase6d_internal_metadata_owner_switch_batch.py",
        "tests/test_phase6e_internal_owner_switch_acceptance.py",
        "tests/test_phase6f_external_adapter_enablement_readiness.py",
        "tests/test_phase6g_low_risk_external_adapter_enablement_tooling.py",
        "tests/test_phase6h_production_compat_exact_route_narrowing_readiness.py",
        "tests/test_phase6i_external_enablement_and_compat_readiness_acceptance.py",
        "tests/test_phase6j_timer_execution_readiness.py",
        "tests/test_phase6k_single_scope_execution_canary_tooling.py",
        "tests/test_phase6l_phase6_aggregate_acceptance.py",
        "tests/test_phase7a_legacy_retirement_readiness.py",
        "tests/test_phase7b_baseline_legacy_import_remediation.py",
        "tests/test_phase7c_delete_ready_candidate_selection.py",
        "tests/test_phase7d_first_safe_cleanup.py",
        "tests/test_phase7e_fallback_cleanup_readiness.py",
        "tests/test_phase7f_production_compat_cleanup_readiness.py",
        "tests/test_phase7g_first_exact_route_fallback_removal_canary.py",
        "tests/test_phase7h_first_exact_route_production_compat_cleanup_canary.py",
        "tests/test_phase7i_legacy_runtime_deletion_readiness.py",
        "tests/test_phase7j_legacy_runtime_cleanup_blocker_acceptance.py",
        "tests/test_phase7k_final_route_ownership_manifest_cleanup.py",
        "tests/test_phase7l_final_legacy_retirement_acceptance.py",
        "tests/test_post_phase7_new_feature_development_rules.py",
        "tools/check_phase4ci_workflows_staging_readiness_bundle.py",
        "tools/run_phase4ci_workflows_staging_readiness.py",
        "tests/test_phase4ci_workflows_staging_readiness_bundle.py",
        "tools/check_phase4cj_workflow_nodes_staging_readiness_bundle.py",
        "tools/run_phase4cj_workflow_nodes_staging_readiness.py",
        "tests/test_phase4cj_workflow_nodes_staging_readiness_bundle.py",
        "tools/check_phase4ck_tasks_staging_readiness_bundle.py",
        "tools/run_phase4ck_tasks_staging_readiness.py",
        "tests/test_phase4ck_tasks_staging_readiness_bundle.py",
        "tools/check_phase4br_task_groups_fixture_runtime.py",
        "tools/check_phase4bs_workflows_fixture_runtime.py",
        "tools/check_phase4bt_workflow_nodes_fixture_runtime.py",
        "tools/check_phase4bu_tasks_fixture_runtime.py",
        "tools/run_codex_autopilot_tick.py",
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
    }
PROTECTED_EXACT = {
    "aicrm_next/main.py",
    "app.py",
    "legacy_flask_app.py",
}
PROTECTED_PREFIXES = (
    "aicrm_next/production_compat/",
    "wecom_ability_service/",
    "deploy/",
    "systemd/",
    "nginx/",
)
MIGRATION_PREFIXES = (
    "migrations/",
    "wecom_ability_service/db/migrations/",
)
DESTRUCTIVE_MIGRATION_PATTERNS = (
    r"\bdrop\s+table\b",
    r"\bdrop\s+column\b",
    r"\balter\s+table\b.*\bdrop\b",
    r"\btruncate\b",
    r"\bdelete\s+from\b",
    r"\brename\s+(table|column)\b",
)
UNAUTHORIZED_CLAIM_PATTERNS = (
    r"\bproduction_ready\b",
    r"\bdelete_ready\s*[:=]\s*true\b",
    r"\bdelete_ready\s+true\b",
    r"\bcanary_approved\b",
    r"\bcanary approved\b",
    r"\broute_switch_ready\s*[:=]\s*true\b",
)
STOP_CONDITION_PATTERNS = (
    r"\bproduction owner switch\b",
    r"\broute ownership switch\b",
    r"\bfallback removal\b",
    r"\bremove legacy fallback\b",
    r"\bproduction write\b",
    r"\breal external call\b",
    r"\bwecom external\b",
    r"\brun-due\b",
    r"\bautomation execution\b",
    r"\boutbound send\b",
    r"\bdeploy config\b",
    r"\bdestructive migration\b",
)


def _run_git(args: list[str]) -> tuple[bool, str, str]:
    proc = subprocess.run(["git", *args], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
    return proc.returncode == 0, proc.stdout, proc.stderr


def _changed_files(base_ref: str, head_ref: str) -> tuple[set[str], list[str]]:
    changed: set[str] = set()
    warnings: list[str] = []
    for args in (
        ["diff", "--name-only", f"{base_ref}...{head_ref}"],
        ["diff", "--name-only"],
        ["diff", "--name-only", "--cached"],
    ):
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


def _file_text(path: str, base_ref: str) -> str:
    full_path = ROOT / path
    if full_path.exists():
        return full_path.read_text(encoding="utf-8", errors="ignore")
    ok, stdout, _ = _run_git(["show", f"{base_ref}:{path}"])
    return stdout if ok else ""


def _diff_text(paths: set[str], base_ref: str, head_ref: str) -> str:
    ok, stdout, _ = _run_git(["diff", f"{base_ref}...{head_ref}", "--", *sorted(paths)])
    parts = [stdout] if ok else []
    for path in sorted(paths):
        if (ROOT / path).exists() and path not in stdout:
            parts.append(f"\n--- {path}\n{_file_text(path, base_ref)}")
    return "\n".join(parts)


def _is_low_risk_path(path: str) -> bool:
    return (
        path in LOW_RISK_EXACT
        or path in OWNER_DECISION_PACKAGE_PATHS
        or path in AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
        or path.startswith(LOW_RISK_PREFIXES)
    )


def _has_owner_approval(path: str | None) -> bool:
    if not path:
        return False
    approval = Path(path)
    if not approval.is_absolute():
        approval = ROOT / approval
    return approval.exists() and approval.read_text(encoding="utf-8", errors="ignore").strip() != ""


def _protected_path_reason(path: str) -> str | None:
    if path in PROTECTED_EXACT:
        return f"protected exact path: {path}"
    if any(path.startswith(prefix) for prefix in PROTECTED_PREFIXES):
        return f"protected runtime/deploy path: {path}"
    return None


def _destructive_migration_reason(path: str, text: str) -> str | None:
    if not any(path.startswith(prefix) for prefix in MIGRATION_PREFIXES):
        return None
    lowered = text.lower()
    for pattern in DESTRUCTIVE_MIGRATION_PATTERNS:
        if re.search(pattern, lowered, flags=re.DOTALL):
            return f"destructive migration pattern in {path}: {pattern}"
    return None


def _pr_body_blockers(pr_body_file: Path) -> list[str]:
    if not pr_body_file.exists():
        return [f"PR body file missing: {pr_body_file}"]
    text = pr_body_file.read_text(encoding="utf-8", errors="ignore")
    blockers = [f"PR body missing required section: {section}" for section in sorted(REQUIRED_PR_BODY_SECTIONS) if section not in text]
    lowered = text.lower()
    for pattern in UNAUTHORIZED_CLAIM_PATTERNS:
        if re.search(pattern, lowered):
            blockers.append(f"PR body contains unauthorized readiness claim: {pattern}")
    return blockers


def build_report(
    base_ref: str = "origin/main",
    head_ref: str = "HEAD",
    pr_body_file: str | None = None,
    owner_approval_file: str | None = None,
) -> dict[str, Any]:
    blockers: list[str] = []
    warnings: list[str] = []
    manual_merge_required: list[str] = []

    changed, git_warnings = _changed_files(base_ref, head_ref)
    warnings.extend(git_warnings)
    pr_body_path = Path(pr_body_file) if pr_body_file else DEFAULT_PR_BODY
    if not pr_body_path.is_absolute():
        pr_body_path = ROOT / pr_body_path
    blockers.extend(_pr_body_blockers(pr_body_path))

    owner_approval_present = _has_owner_approval(owner_approval_file)
    if not changed:
        blockers.append("no changed files detected")

    non_low_risk = sorted(path for path in changed if not _is_low_risk_path(path))
    if non_low_risk:
        blockers.append(f"auto-merge eligibility only allows low-risk docs/tools/tests paths: {non_low_risk}")

    protected_hits: list[str] = []
    destructive_hits: list[str] = []
    stop_hits: list[str] = []
    claim_hits: list[str] = []
    for path in sorted(changed):
        text = _file_text(path, base_ref)
        reason = _protected_path_reason(path)
        if reason:
            protected_hits.append(reason)
        destructive_reason = _destructive_migration_reason(path, text)
        if destructive_reason:
            destructive_hits.append(destructive_reason)
        lowered = text.lower()
        if path not in POLICY_FILES_CAN_DEFINE_STOP_TERMS:
            for pattern in STOP_CONDITION_PATTERNS:
                if re.search(pattern, lowered):
                    stop_hits.append(f"{path}: {pattern}")
        for pattern in UNAUTHORIZED_CLAIM_PATTERNS:
            if path not in POLICY_FILES_CAN_DEFINE_STOP_TERMS and re.search(pattern, lowered):
                claim_hits.append(f"{path}: {pattern}")

    if protected_hits or destructive_hits:
        if owner_approval_present:
            manual_merge_required.extend(protected_hits + destructive_hits)
        else:
            blockers.extend(protected_hits + destructive_hits)
            blockers.append("protected/high-risk diff requires explicit owner approval file")
    owner_decision_hits = sorted(path for path in changed if path in OWNER_DECISION_PACKAGE_PATHS)
    if owner_decision_hits:
        manual_merge_required.append(f"owner decision package is not auto-merge eligible: {owner_decision_hits}")
    if stop_hits:
        blockers.append(f"diff touches stop condition outside policy/checker files: {stop_hits}")
    if claim_hits:
        blockers.append(f"diff contains unauthorized readiness claim: {claim_hits}")

    if not STOP.exists():
        blockers.append("autonomous_stop_conditions.yaml missing")

    eligible = not blockers and not manual_merge_required
    return {
        "overall": "PASS" if not blockers else "FAIL",
        "ok": not blockers,
        "eligible": eligible,
        "owner_approval_present": owner_approval_present,
        "manual_merge_required": manual_merge_required,
        "blockers": blockers,
        "warnings": warnings,
        "details": {
            "base_ref": base_ref,
            "head_ref": head_ref,
            "changed_files": sorted(changed),
            "pr_body_file": str(pr_body_path.relative_to(ROOT) if pr_body_path.is_relative_to(ROOT) else pr_body_path),
        },
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Auto-Merge Eligibility Check",
            "",
            f"- overall: {report['overall']}",
            f"- ok: {str(report['ok']).lower()}",
            f"- eligible: {str(report['eligible']).lower()}",
            "",
            "## Blockers",
            *(f"- {item}" for item in report["blockers"]),
            "",
            "## Manual Merge Required",
            *(f"- {item}" for item in report["manual_merge_required"]),
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-ref", default="origin/main")
    parser.add_argument("--head-ref", default="HEAD")
    parser.add_argument("--pr-body-file")
    parser.add_argument("--owner-approval-file")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = build_report(
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        pr_body_file=args.pr_body_file,
        owner_approval_file=args.owner_approval_file,
    )
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps({"overall": report["overall"], "ok": report["ok"], "eligible": report["eligible"], "blockers": report["blockers"]}, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
