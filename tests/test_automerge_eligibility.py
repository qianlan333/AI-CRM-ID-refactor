from __future__ import annotations

import json
from pathlib import Path

import tools.check_automerge_eligibility as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/autonomous_development_loop.md"


def test_checker_current_repo_passes_and_reports_expected_eligibility() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    if any(path in checker.OWNER_DECISION_PACKAGE_PATHS for path in report["details"]["changed_files"]):
        assert report["eligible"] is False
        assert report["manual_merge_required"]
    else:
        assert report["eligible"] is True


def test_pr_body_sections_required() -> None:
    text = DOC.read_text(encoding="utf-8")
    for section in checker.REQUIRED_PR_BODY_SECTIONS:
        assert section in text


def test_low_risk_changed_files_are_docs_tools_tests_only() -> None:
    report = checker.build_report()
    for path in report["details"]["changed_files"]:
        assert checker._is_low_risk_path(path)


def test_protected_runtime_path_requires_owner_approval() -> None:
    reason = checker._protected_path_reason("aicrm_next/production_compat/api.py")
    assert reason
    assert checker._protected_path_reason("aicrm_next/main.py")
    assert checker._protected_path_reason("wecom_ability_service/http/example.py")


def test_destructive_migration_detection() -> None:
    reason = checker._destructive_migration_reason("migrations/2026_drop.sql", "ALTER TABLE x DROP COLUMN y;")
    assert reason


def test_unauthorized_claim_patterns_detected() -> None:
    text = "route_switch_ready=true\ncanary_approved\nproduction_ready\ndelete_ready: true\ndelete_ready true\ncanary approved"
    for pattern in checker.UNAUTHORIZED_CLAIM_PATTERNS:
        assert __import__("re").search(pattern, text)


def test_stop_condition_terms_are_not_allowed_outside_policy_files(tmp_path: Path) -> None:
    body = tmp_path / "body.md"
    body.write_text("Business value\nBusiness continuity\nRisk / rollback\nNext action\n", encoding="utf-8")
    report = checker.build_report(pr_body_file=str(body))
    assert report["overall"] == "PASS"


def test_phase5a_wecom_tag_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5a_wecom_tag_adapter_contract.md",
        "docs/development/phase_5a_wecom_tag_adapter_contract.yaml",
        "tools/check_phase5a_wecom_tag_adapter_contract.py",
        "tools/run_phase5a_wecom_tag_adapter_contract_evidence.py",
        "tests/test_phase5a_wecom_tag_adapter_contract.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4am_closure_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.md",
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.yaml",
        "tools/check_phase4am_action_templates_staging_approval_config_closure.py",
        "tests/test_phase4am_action_templates_staging_approval_config_closure.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cr_tasks_production_dry_run_artifacts_are_low_risk_policy_files() -> None:
    expected = {
        "docs/development/phase_4cr_tasks_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4cr_tasks_production_dry_run_readiness_bundle.yaml",
        "tools/check_phase4cr_tasks_production_dry_run_readiness_bundle.py",
        "tools/run_phase4cr_tasks_production_readonly_dry_run.py",
        "tests/test_phase4cr_tasks_production_dry_run_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase4cs_agent_runs_production_dry_run_artifacts_are_low_risk_policy_files() -> None:
    expected = {
        "docs/development/phase_4cs_agent_runs_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4cs_agent_runs_production_dry_run_readiness_bundle.yaml",
        "tools/check_phase4cs_agent_runs_production_dry_run_readiness_bundle.py",
        "tools/run_phase4cs_agent_runs_production_readonly_dry_run.py",
        "tests/test_phase4cs_agent_runs_production_dry_run_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase4ct_agent_outputs_production_dry_run_artifacts_are_low_risk_policy_files() -> None:
    expected = {
        "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.md",
        "docs/development/phase_4ct_agent_outputs_production_dry_run_readiness_bundle.yaml",
        "tools/check_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py",
        "tools/run_phase4ct_agent_outputs_production_readonly_dry_run.py",
        "tests/test_phase4ct_agent_outputs_production_dry_run_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase4cu_internal_write_acceptance_review_artifacts_are_low_risk_policy_files() -> None:
    expected = {
        "docs/development/phase_4cu_internal_write_acceptance_review.md",
        "docs/development/phase_4cu_internal_write_acceptance_review.yaml",
        "tools/check_phase4cu_internal_write_acceptance_review.py",
        "tests/test_phase4cu_internal_write_acceptance_review.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase4cv_phase5_readiness_entry_artifacts_are_low_risk_policy_files() -> None:
    expected = {
        "docs/development/phase_4cv_phase5_readiness_entry.md",
        "docs/development/phase_4cv_phase5_readiness_entry.yaml",
        "tools/check_phase4cv_phase5_readiness_entry.py",
        "tests/test_phase4cv_phase5_readiness_entry.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase4am_owner_decision_package_is_manual_merge_only() -> None:
    expected_owner_paths = {
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
    }
    expected_policy_paths = expected_owner_paths | {
        "tools/check_phase4am_action_templates_staging_owner_decision_package.py",
        "tests/test_phase4am_action_templates_staging_owner_decision_package.py",
    }
    assert expected_owner_paths <= checker.OWNER_DECISION_PACKAGE_PATHS
    assert expected_policy_paths <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4an_task_groups_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4an_task_groups_native_contract_plan.md",
        "docs/development/phase_4an_task_groups_native_contract_plan.yaml",
        "tools/check_phase4an_task_groups_native_contract_plan.py",
        "tests/test_phase4an_task_groups_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ao_task_groups_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.md",
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.yaml",
        "tools/check_phase4ao_task_groups_schema_route_surface_confirmation.py",
        "tests/test_phase4ao_task_groups_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ap_task_groups_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md",
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml",
        "tools/check_phase4ap_task_groups_fixture_native_contract_plan.py",
        "tests/test_phase4ap_task_groups_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4aq_task_groups_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ar_workflows_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ar_workflows_metadata_plan.md",
        "docs/development/phase_4ar_workflows_metadata_plan.yaml",
        "tools/check_phase4ar_workflows_metadata_plan.py",
        "tests/test_phase4ar_workflows_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4as_workflows_schema_route_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.md",
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.yaml",
        "tools/check_phase4as_workflows_schema_route_surface_confirmation.py",
        "tests/test_phase4as_workflows_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4at_workflows_fixture_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.md",
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml",
        "tools/check_phase4at_workflows_fixture_native_contract_plan.py",
        "tests/test_phase4at_workflows_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4au_workflows_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4au_workflows_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4au_workflows_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4av_workflow_nodes_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4av_workflow_nodes_metadata_plan.md",
        "docs/development/phase_4av_workflow_nodes_metadata_plan.yaml",
        "tools/check_phase4av_workflow_nodes_metadata_plan.py",
        "tests/test_phase4av_workflow_nodes_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4aw_workflow_nodes_schema_route_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.md",
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.yaml",
        "tools/check_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
        "tests/test_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ax_workflow_nodes_fixture_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.md",
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.yaml",
        "tools/check_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
        "tests/test_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ay_workflow_nodes_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4az_next_candidate_selection_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4az_next_internal_write_candidate_selection.md",
        "docs/development/phase_4az_next_internal_write_candidate_selection.yaml",
        "tools/check_phase4az_next_internal_write_candidate_selection.py",
        "tests/test_phase4az_next_internal_write_candidate_selection.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ba_tasks_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ba_tasks_metadata_plan.md",
        "docs/development/phase_4ba_tasks_metadata_plan.yaml",
        "tools/check_phase4ba_tasks_metadata_plan.py",
        "tests/test_phase4ba_tasks_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bb_tasks_schema_route_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.md",
        "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bb_tasks_schema_route_surface_confirmation.py",
        "tests/test_phase4bb_tasks_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bc_tasks_fixture_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bc_tasks_fixture_native_contract_plan.md",
        "docs/development/phase_4bc_tasks_fixture_native_contract_plan.yaml",
        "tools/check_phase4bc_tasks_fixture_native_contract_plan.py",
        "tests/test_phase4bc_tasks_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bd_tasks_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bd_tasks_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bd_tasks_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bd_tasks_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bd_tasks_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4be_agents_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4be_agents_metadata_plan.md",
        "docs/development/phase_4be_agents_metadata_plan.yaml",
        "tools/check_phase4be_agents_metadata_plan.py",
        "tests/test_phase4be_agents_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bf_agents_schema_route_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bf_agents_schema_route_surface_confirmation.md",
        "docs/development/phase_4bf_agents_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bf_agents_schema_route_surface_confirmation.py",
        "tests/test_phase4bf_agents_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bg_agents_fixture_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bg_agents_fixture_native_contract_plan.md",
        "docs/development/phase_4bg_agents_fixture_native_contract_plan.yaml",
        "tools/check_phase4bg_agents_fixture_native_contract_plan.py",
        "tests/test_phase4bg_agents_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bh_agents_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bh_agents_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bh_agents_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bi_agent_outputs_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bi_agent_outputs_metadata_plan.md",
        "docs/development/phase_4bi_agent_outputs_metadata_plan.yaml",
        "tools/check_phase4bi_agent_outputs_metadata_plan.py",
        "tests/test_phase4bi_agent_outputs_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bj_agent_outputs_schema_route_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md",
        "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
        "tests/test_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bk_agent_outputs_fixture_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md",
        "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml",
        "tools/check_phase4bk_agent_outputs_fixture_native_contract_plan.py",
        "tests/test_phase4bk_agent_outputs_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bl_agent_outputs_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bm_agent_runs_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bm_agent_runs_metadata_plan.md",
        "docs/development/phase_4bm_agent_runs_metadata_plan.yaml",
        "tools/check_phase4bm_agent_runs_metadata_plan.py",
        "tests/test_phase4bm_agent_runs_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bn_agent_runs_schema_route_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.md",
        "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bn_agent_runs_schema_route_surface_confirmation.py",
        "tests/test_phase4bn_agent_runs_schema_route_surface_confirmation.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bo_agent_runs_fixture_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bo_agent_runs_fixture_native_contract_plan.md",
        "docs/development/phase_4bo_agent_runs_fixture_native_contract_plan.yaml",
        "tools/check_phase4bo_agent_runs_fixture_native_contract_plan.py",
        "tests/test_phase4bo_agent_runs_fixture_native_contract_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bp_agent_runs_owner_decision_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bp_agent_runs_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bp_agent_runs_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bq_agent_replay_metadata_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bq_agent_replay_metadata_plan.md",
        "docs/development/phase_4bq_agent_replay_metadata_plan.yaml",
        "tools/check_phase4bq_agent_replay_metadata_plan.py",
        "tests/test_phase4bq_agent_replay_metadata_plan.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4by_agent_replay_discovery_contract_bundle_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4by_agent_replay_discovery_contract_bundle.md",
        "docs/development/phase_4by_agent_replay_discovery_contract_bundle.yaml",
        "tools/check_phase4by_agent_replay_discovery_contract_bundle.py",
        "tests/test_phase4by_agent_replay_discovery_contract_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ca_task_groups_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ca_task_groups_repository_adapter_parity_bundle.md",
        "docs/development/phase_4ca_task_groups_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4ca_task_groups_repository_adapter_parity_bundle.py",
        "tools/run_phase4ca_task_groups_adapter_parity.py",
        "tests/test_phase4ca_task_groups_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cb_workflows_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cb_workflows_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cb_workflows_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cb_workflows_repository_adapter_parity_bundle.py",
        "tools/run_phase4cb_workflows_adapter_parity.py",
        "tests/test_phase4cb_workflows_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cc_workflow_nodes_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py",
        "tools/run_phase4cc_workflow_nodes_adapter_parity.py",
        "tests/test_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cd_tasks_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cd_tasks_repository_adapter_parity_bundle.py",
        "tools/run_phase4cd_tasks_adapter_parity.py",
        "tests/test_phase4cd_tasks_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ce_agents_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ce_agents_repository_adapter_parity_bundle.md",
        "docs/development/phase_4ce_agents_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4ce_agents_repository_adapter_parity_bundle.py",
        "tools/run_phase4ce_agents_adapter_parity.py",
        "tests/test_phase4ce_agents_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cf_agent_outputs_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cf_agent_outputs_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cf_agent_outputs_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cf_agent_outputs_repository_adapter_parity_bundle.py",
        "tools/run_phase4cf_agent_outputs_adapter_parity.py",
        "tests/test_phase4cf_agent_outputs_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cg_agent_runs_adapter_parity_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cg_agent_runs_repository_adapter_parity_bundle.py",
        "tools/run_phase4cg_agent_runs_adapter_parity.py",
        "tests/test_phase4cg_agent_runs_repository_adapter_parity_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ch_task_groups_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ch_task_groups_staging_readiness_bundle.md",
        "docs/development/phase_4ch_task_groups_staging_readiness_bundle.yaml",
        "tools/check_phase4ch_task_groups_staging_readiness_bundle.py",
        "tools/run_phase4ch_task_groups_staging_readiness.py",
        "tests/test_phase4ch_task_groups_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ci_workflows_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ci_workflows_staging_readiness_bundle.md",
        "docs/development/phase_4ci_workflows_staging_readiness_bundle.yaml",
        "tools/check_phase4ci_workflows_staging_readiness_bundle.py",
        "tools/run_phase4ci_workflows_staging_readiness.py",
        "tests/test_phase4ci_workflows_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cj_workflow_nodes_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cj_workflow_nodes_staging_readiness_bundle.md",
        "docs/development/phase_4cj_workflow_nodes_staging_readiness_bundle.yaml",
        "tools/check_phase4cj_workflow_nodes_staging_readiness_bundle.py",
        "tools/run_phase4cj_workflow_nodes_staging_readiness.py",
        "tests/test_phase4cj_workflow_nodes_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4ck_tasks_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4ck_tasks_staging_readiness_bundle.md",
        "docs/development/phase_4ck_tasks_staging_readiness_bundle.yaml",
        "tools/check_phase4ck_tasks_staging_readiness_bundle.py",
        "tools/run_phase4ck_tasks_staging_readiness.py",
        "tests/test_phase4ck_tasks_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cl_agents_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cl_agents_staging_readiness_bundle.md",
        "docs/development/phase_4cl_agents_staging_readiness_bundle.yaml",
        "tools/check_phase4cl_agents_staging_readiness_bundle.py",
        "tools/run_phase4cl_agents_staging_readiness.py",
        "tests/test_phase4cl_agents_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cm_agent_outputs_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cm_agent_outputs_staging_readiness_bundle.md",
        "docs/development/phase_4cm_agent_outputs_staging_readiness_bundle.yaml",
        "tools/check_phase4cm_agent_outputs_staging_readiness_bundle.py",
        "tools/run_phase4cm_agent_outputs_staging_readiness.py",
        "tests/test_phase4cm_agent_outputs_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4cn_agent_runs_staging_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4cn_agent_runs_staging_readiness_bundle.md",
        "docs/development/phase_4cn_agent_runs_staging_readiness_bundle.yaml",
        "tools/check_phase4cn_agent_runs_staging_readiness_bundle.py",
        "tools/run_phase4cn_agent_runs_staging_readiness.py",
        "tests/test_phase4cn_agent_runs_staging_readiness_bundle.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS
    assert checker._is_low_risk_path("tools/run_phase4cn_agent_runs_staging_readiness.py")


def test_phase4br_task_groups_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4br_task_groups_fixture_runtime.md",
        "tools/check_phase4br_task_groups_fixture_runtime.py",
        "tests/test_phase4br_task_groups_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4br_runtime_paths_are_autopilot_deliverable() -> None:
    expected = {
        "aicrm_next/automation_engine/api.py",
        "aicrm_next/automation_engine/application.py",
        "aicrm_next/automation_engine/dto.py",
        "aicrm_next/automation_engine/repo.py",
        "aicrm_next/automation_engine/task_groups.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase4ca_task_group_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/task_group_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/task_group_sqlalchemy_repository.py")


def test_phase4cb_workflow_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/workflow_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/workflow_sqlalchemy_repository.py")


def test_phase4cc_workflow_node_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/workflow_node_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/workflow_node_sqlalchemy_repository.py")


def test_phase4cd_task_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/task_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/task_sqlalchemy_repository.py")


def test_phase4ce_agent_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/agent_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/agent_sqlalchemy_repository.py")


def test_phase4cf_agent_output_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/agent_output_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/agent_output_sqlalchemy_repository.py")


def test_phase4cg_agent_run_adapter_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/agent_run_sqlalchemy_repository.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/agent_run_sqlalchemy_repository.py")


def test_phase4bs_workflows_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bs_workflows_fixture_runtime.md",
        "tools/check_phase4bs_workflows_fixture_runtime.py",
        "tests/test_phase4bs_workflows_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bs_workflows_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/workflows.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/workflows.py")


def test_phase4bt_workflow_nodes_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bt_workflow_nodes_fixture_runtime.md",
        "tools/check_phase4bt_workflow_nodes_fixture_runtime.py",
        "tests/test_phase4bt_workflow_nodes_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bt_workflow_nodes_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/workflow_nodes.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/workflow_nodes.py")


def test_phase4bu_tasks_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bu_tasks_fixture_runtime.md",
        "tools/check_phase4bu_tasks_fixture_runtime.py",
        "tests/test_phase4bu_tasks_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bu_tasks_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/tasks.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/tasks.py")


def test_phase4bv_agents_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bv_agents_fixture_runtime.md",
        "tools/check_phase4bv_agents_fixture_runtime.py",
        "tests/test_phase4bv_agents_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bv_agents_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/agents.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/agents.py")


def test_phase4bw_agent_outputs_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bw_agent_outputs_fixture_runtime.md",
        "tools/check_phase4bw_agent_outputs_fixture_runtime.py",
        "tests/test_phase4bw_agent_outputs_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bw_agent_outputs_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/agent_outputs.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/agent_outputs.py")


def test_phase4bx_agent_runs_runtime_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_4bx_agent_runs_fixture_runtime.md",
        "tools/check_phase4bx_agent_runs_fixture_runtime.py",
        "tests/test_phase4bx_agent_runs_fixture_runtime.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase4bx_agent_runs_runtime_path_is_autopilot_deliverable() -> None:
    assert "aicrm_next/automation_engine/agent_runs.py" in checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    assert checker._is_low_risk_path("aicrm_next/automation_engine/agent_runs.py")


def test_phase5b_wecom_tag_fake_stub_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5b_wecom_tag_fake_stub_adapter.md",
        "docs/development/phase_5b_wecom_tag_fake_stub_adapter.yaml",
        "tools/check_phase5b_wecom_tag_fake_stub_adapter.py",
        "tools/run_phase5b_wecom_tag_fake_stub_staging_smoke.py",
        "tools/run_phase5b_wecom_tag_fake_stub_production_dry_run.py",
        "tests/test_phase5b_wecom_tag_fake_stub_adapter.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5b_wecom_tag_fake_stub_runtime_paths_are_autopilot_deliverable() -> None:
    expected = {
        "aicrm_next/customer_tags/api.py",
        "aicrm_next/customer_tags/application.py",
        "aicrm_next/customer_tags/dto.py",
        "aicrm_next/customer_tags/wecom_tag_adapter.py",
        "aicrm_next/customer_tags/wecom_tag_contract.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase5c_wecom_tag_live_adapter_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.md",
        "docs/development/phase_5c_wecom_tag_live_adapter_behind_flag.yaml",
        "tools/check_phase5c_wecom_tag_live_adapter_behind_flag.py",
        "tools/run_phase5c_wecom_tag_live_staging_evidence.py",
        "tools/run_phase5c_wecom_tag_live_production_dry_run_gate.py",
        "tests/test_phase5c_wecom_tag_live_adapter_behind_flag.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5c_wecom_tag_live_adapter_runtime_paths_are_autopilot_deliverable() -> None:
    expected = {
        "aicrm_next/customer_tags/api.py",
        "aicrm_next/customer_tags/application.py",
        "aicrm_next/customer_tags/dto.py",
        "aicrm_next/customer_tags/wecom_tag_contract.py",
        "aicrm_next/customer_tags/wecom_tag_live_adapter.py",
        "aicrm_next/integration_gateway/wecom_tag_live_gateway.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS
    for path in expected:
        assert checker._is_low_risk_path(path)


def test_phase5d_wecom_tag_staging_live_canary_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.md",
        "docs/development/phase_5d_wecom_tag_staging_live_canary_evidence.yaml",
        "tools/check_phase5d_wecom_tag_staging_live_canary_evidence.py",
        "tools/run_phase5d_wecom_tag_staging_live_canary_evidence.py",
        "tools/run_phase5d_wecom_tag_production_live_readiness_review.py",
        "tests/test_phase5d_wecom_tag_staging_live_canary_evidence.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5e_wecom_tag_production_canary_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5e_wecom_tag_production_canary_readiness.md",
        "docs/development/phase_5e_wecom_tag_production_canary_readiness.yaml",
        "tools/check_phase5e_wecom_tag_production_canary_readiness.py",
        "tools/run_phase5e_wecom_tag_production_canary_readiness.py",
        "tests/test_phase5e_wecom_tag_production_canary_readiness.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5f_wecom_tag_production_live_canary_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5f_wecom_tag_production_live_canary_execution.md",
        "docs/development/phase_5f_wecom_tag_production_live_canary_execution.yaml",
        "tools/check_phase5f_wecom_tag_production_live_canary_execution.py",
        "tools/run_phase5f_wecom_tag_production_live_canary_execution.py",
        "tools/run_phase5f_wecom_tag_production_canary_cleanup.py",
        "tests/test_phase5f_wecom_tag_production_live_canary_execution.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5g_wecom_tag_family_acceptance_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5g_wecom_tag_family_acceptance.md",
        "docs/development/phase_5g_wecom_tag_family_acceptance.yaml",
        "tools/check_phase5g_wecom_tag_family_acceptance.py",
        "tests/test_phase5g_wecom_tag_family_acceptance.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5h_wecom_customer_contact_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5h_wecom_customer_contact_adapter_contract.md",
        "docs/development/phase_5h_wecom_customer_contact_adapter_contract.yaml",
        "tools/check_phase5h_wecom_customer_contact_adapter_contract.py",
        "tools/run_phase5h_wecom_customer_contact_adapter_contract_evidence.py",
        "tests/test_phase5h_wecom_customer_contact_adapter_contract.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5i_wecom_customer_contact_fake_stub_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.md",
        "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.yaml",
        "tools/check_phase5i_wecom_customer_contact_fake_stub_adapter.py",
        "tools/run_phase5i_wecom_customer_contact_fake_stub_staging_smoke.py",
        "tools/run_phase5i_wecom_customer_contact_fake_stub_production_dry_run.py",
        "tests/test_phase5i_wecom_customer_contact_fake_stub_adapter.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5i_wecom_customer_contact_fake_stub_runtime_paths_are_automerge_deliverables() -> None:
    expected = {
        "aicrm_next/integration_gateway/wecom_contact_callback_adapter.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_contract.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS


def test_phase5j_wecom_customer_contact_live_callback_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.md",
        "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.yaml",
        "tools/check_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
        "tools/run_phase5j_wecom_customer_contact_live_callback_staging_evidence.py",
        "tools/run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate.py",
        "tests/test_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5j_wecom_customer_contact_live_callback_runtime_paths_are_automerge_deliverables() -> None:
    expected = {
        "aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_live_gateway.py",
        "aicrm_next/integration_gateway/wecom_contact_callback_application.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS


def test_phase5k_wecom_customer_contact_staging_canary_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.md",
        "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.yaml",
        "tools/check_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
        "tools/run_phase5k_wecom_customer_contact_production_callback_readiness_review.py",
        "tests/test_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5l_wecom_customer_contact_production_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.md",
        "docs/development/phase_5l_wecom_customer_contact_production_callback_canary_readiness.yaml",
        "tools/check_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tools/run_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
        "tests/test_phase5l_wecom_customer_contact_production_callback_canary_readiness.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5m_wecom_customer_contact_family_acceptance_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.md",
        "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.yaml",
        "tools/check_phase5m_wecom_customer_contact_callback_family_acceptance.py",
        "tests/test_phase5m_wecom_customer_contact_callback_family_acceptance.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5n_oauth_identity_contract_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5n_oauth_identity_adapter_contract.md",
        "docs/development/phase_5n_oauth_identity_adapter_contract.yaml",
        "tools/check_phase5n_oauth_identity_adapter_contract.py",
        "tools/run_phase5n_oauth_identity_adapter_contract_evidence.py",
        "tests/test_phase5n_oauth_identity_adapter_contract.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5o_oauth_identity_fake_stub_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5o_oauth_identity_fake_stub_adapter.md",
        "docs/development/phase_5o_oauth_identity_fake_stub_adapter.yaml",
        "tools/check_phase5o_oauth_identity_fake_stub_adapter.py",
        "tools/run_phase5o_oauth_identity_fake_stub_staging_smoke.py",
        "tools/run_phase5o_oauth_identity_fake_stub_production_dry_run.py",
        "tests/test_phase5o_oauth_identity_fake_stub_adapter.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5p_oauth_identity_live_adapter_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5p_oauth_identity_live_adapter_behind_flag.md",
        "docs/development/phase_5p_oauth_identity_live_adapter_behind_flag.yaml",
        "tools/check_phase5p_oauth_identity_live_adapter_behind_flag.py",
        "tools/run_phase5p_oauth_identity_live_staging_evidence.py",
        "tools/run_phase5p_oauth_identity_live_production_dry_run_gate.py",
        "tests/test_phase5p_oauth_identity_live_adapter_behind_flag.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5q_oauth_identity_staging_canary_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.md",
        "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.yaml",
        "tools/check_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/run_phase5q_oauth_identity_staging_live_canary_evidence.py",
        "tools/run_phase5q_oauth_identity_production_live_readiness_review.py",
        "tests/test_phase5q_oauth_identity_staging_live_canary_evidence.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5r_oauth_identity_production_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5r_oauth_identity_production_canary_readiness.md",
        "docs/development/phase_5r_oauth_identity_production_canary_readiness.yaml",
        "tools/check_phase5r_oauth_identity_production_canary_readiness.py",
        "tools/run_phase5r_oauth_identity_production_canary_readiness.py",
        "tests/test_phase5r_oauth_identity_production_canary_readiness.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5s_oauth_identity_production_canary_execution_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5s_oauth_identity_production_live_canary_execution.md",
        "docs/development/phase_5s_oauth_identity_production_live_canary_execution.yaml",
        "tools/check_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/run_phase5s_oauth_identity_production_live_canary_execution.py",
        "tools/run_phase5s_oauth_identity_production_canary_cleanup.py",
        "tests/test_phase5s_oauth_identity_production_live_canary_execution.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5t_oauth_identity_family_acceptance_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5t_oauth_identity_family_acceptance.md",
        "docs/development/phase_5t_oauth_identity_family_acceptance.yaml",
        "tools/check_phase5t_oauth_identity_family_acceptance.py",
        "tests/test_phase5t_oauth_identity_family_acceptance.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5u_media_upload_contract_fake_stub_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.md",
        "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.yaml",
        "tools/check_phase5u_media_upload_adapter_contract_fake_stub.py",
        "tools/run_phase5u_media_upload_fake_stub_staging_smoke.py",
        "tools/run_phase5u_media_upload_fake_stub_production_dry_run.py",
        "tests/test_phase5u_media_upload_adapter_contract_fake_stub.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5v_media_upload_live_adapter_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5v_media_upload_live_adapter_behind_flag.md",
        "docs/development/phase_5v_media_upload_live_adapter_behind_flag.yaml",
        "tools/check_phase5v_media_upload_live_adapter_behind_flag.py",
        "tools/run_phase5v_media_upload_live_staging_evidence.py",
        "tools/run_phase5v_media_upload_live_production_dry_run_gate.py",
        "tests/test_phase5v_media_upload_live_adapter_behind_flag.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5v_media_upload_live_adapter_runtime_paths_are_bounded() -> None:
    expected = {
        "aicrm_next/integration_gateway/media_live_adapter.py",
        "aicrm_next/integration_gateway/media_live_gateway.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS


def test_phase5w_media_upload_staging_canary_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5w_media_upload_staging_live_canary_evidence.md",
        "docs/development/phase_5w_media_upload_staging_live_canary_evidence.yaml",
        "tools/check_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/run_phase5w_media_upload_staging_live_canary_evidence.py",
        "tools/run_phase5w_media_upload_production_live_readiness_review.py",
        "tests/test_phase5w_media_upload_staging_live_canary_evidence.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5x_media_upload_production_canary_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5x_media_upload_production_canary_readiness_execution.md",
        "docs/development/phase_5x_media_upload_production_canary_readiness_execution.yaml",
        "tools/check_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/run_phase5x_media_upload_production_canary_readiness_execution.py",
        "tools/run_phase5x_media_upload_production_canary_cleanup.py",
        "tests/test_phase5x_media_upload_production_canary_readiness_execution.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5y_media_upload_family_acceptance_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5y_media_upload_family_acceptance.md",
        "docs/development/phase_5y_media_upload_family_acceptance.yaml",
        "tools/check_phase5y_media_upload_family_acceptance.py",
        "tests/test_phase5y_media_upload_family_acceptance.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5z_payment_commerce_contract_fake_stub_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.md",
        "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.yaml",
        "tools/check_phase5z_payment_commerce_adapter_contract_fake_stub.py",
        "tools/run_phase5z_payment_commerce_fake_stub_evidence.py",
        "tests/test_phase5z_payment_commerce_adapter_contract_fake_stub.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5aa_payment_commerce_live_adapter_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.md",
        "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.yaml",
        "tools/check_phase5aa_payment_commerce_live_adapter_behind_flag.py",
        "tools/run_phase5aa_payment_commerce_live_staging_evidence.py",
        "tools/run_phase5aa_payment_commerce_live_production_dry_run_gate.py",
        "tests/test_phase5aa_payment_commerce_live_adapter_behind_flag.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5aa_payment_commerce_live_adapter_runtime_paths_are_bounded() -> None:
    expected = {
        "aicrm_next/integration_gateway/payment_commerce_live_adapter.py",
        "aicrm_next/integration_gateway/payment_commerce_live_gateway.py",
    }
    assert expected <= checker.AUTOPILOT_DELIVERABLE_RUNTIME_PATHS


def test_phase5ab_payment_commerce_staging_sandbox_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.md",
        "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.yaml",
        "tools/check_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/run_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
        "tools/run_phase5ab_payment_commerce_production_readiness_review.py",
        "tests/test_phase5ab_payment_commerce_staging_sandbox_canary_evidence.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5ac_payment_commerce_production_readiness_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5ac_payment_commerce_production_canary_readiness.md",
        "docs/development/phase_5ac_payment_commerce_production_canary_readiness.yaml",
        "tools/check_phase5ac_payment_commerce_production_canary_readiness.py",
        "tools/run_phase5ac_payment_commerce_production_canary_readiness.py",
        "tests/test_phase5ac_payment_commerce_production_canary_readiness.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5ad_payment_commerce_production_tooling_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5ad_payment_commerce_production_canary_tooling.md",
        "docs/development/phase_5ad_payment_commerce_production_canary_tooling.yaml",
        "tools/check_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/run_phase5ad_payment_commerce_production_canary_tooling.py",
        "tools/run_phase5ad_payment_commerce_production_canary_cleanup.py",
        "tests/test_phase5ad_payment_commerce_production_canary_tooling.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5ae_payment_commerce_family_acceptance_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5ae_payment_commerce_family_acceptance.md",
        "docs/development/phase_5ae_payment_commerce_family_acceptance.yaml",
        "tools/check_phase5ae_payment_commerce_family_acceptance.py",
        "tests/test_phase5ae_payment_commerce_family_acceptance.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5af_openclaw_mcp_ai_assist_contract_fake_stub_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.md",
        "docs/development/phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.yaml",
        "tools/check_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.py",
        "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_staging_smoke.py",
        "tools/run_phase5af_openclaw_mcp_ai_assist_fake_stub_production_dry_run.py",
        "tests/test_phase5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_phase5ag_openclaw_mcp_ai_assist_live_adapter_artifacts_can_define_stop_terms_as_policy() -> None:
    expected = {
        "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.md",
        "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.yaml",
        "tools/check_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.py",
        "tools/run_phase5ag_openclaw_mcp_ai_assist_live_staging_evidence.py",
        "tools/run_phase5ag_openclaw_mcp_ai_assist_live_production_dry_run_gate.py",
        "tests/test_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.py",
    }
    assert expected <= checker.POLICY_FILES_CAN_DEFINE_STOP_TERMS


def test_owner_approval_does_not_make_protected_diff_automerge_eligible(tmp_path: Path) -> None:
    approval = tmp_path / "approval.md"
    approval.write_text("owner approval placeholder", encoding="utf-8")
    assert checker._has_owner_approval(str(approval)) is True


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production_ready",
        "canary_approved",
        "route_switch_ready=true",
        "delete_ready: true",
    ]
    for item in forbidden:
        assert item not in text
