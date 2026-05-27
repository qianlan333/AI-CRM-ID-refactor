from __future__ import annotations

import json
from pathlib import Path

import tools.run_codex_autopilot_tick as runner


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools/run_codex_autopilot_tick.py"
SCRIPT = ROOT / "scripts/codex_autopilot_tick.sh"
RUNBOOK = ROOT / "docs/development/codex_autopilot_runtime_runbook.md"


def test_runner_exists_and_mentions_required_preflight_docs() -> None:
    text = TOOL.read_text(encoding="utf-8")
    for path in runner.REQUIRED_PREFLIGHT_DOCS:
        assert path in text


def test_runner_generates_cleanup_package_prompt_without_feature_path(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    owner_package = tmp_path / "owner.md"
    report = runner.main(
        [
            "--skip-github",
            "--prompt-output",
            str(prompt),
            "--owner-decision-output",
            str(owner_package),
            "--lock-file",
            str(tmp_path / "lock"),
        ]
    )
    assert report == 0
    assert prompt.exists() is True
    assert owner_package.exists() is False
    text = prompt.read_text(encoding="utf-8")
    assert "post_phase7_cleanup_owner_evidence_package_blocker_acceptance_bundle" in text
    assert "post_phase7_hxc_next_native_broadcast_backend_plan_bundle" not in text


def test_runner_owner_decision_package_on_stop_condition(tmp_path: Path) -> None:
    owner_package = tmp_path / "owner.md"
    result = runner.main(
        [
            "--skip-github",
            "--action",
            "production write",
            "--owner-decision-output",
            str(owner_package),
            "--lock-file",
            str(tmp_path / "lock"),
        ]
    )
    assert result == 0
    assert owner_package.exists()
    text = owner_package.read_text(encoding="utf-8")
    assert "auto_merge_allowed: false" in text
    assert "production_write_allowed: false" in text


def test_runner_treats_phase4am_closure_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.md",
        "docs/development/phase_4am_action_templates_staging_approval_config_closure.yaml",
        "tools/check_phase4am_action_templates_staging_approval_config_closure.py",
        "tests/test_phase4am_action_templates_staging_approval_config_closure.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4am_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.md",
        "docs/development/phase_4am_action_templates_staging_owner_decision_package.yaml",
        "tools/check_phase4am_action_templates_staging_owner_decision_package.py",
        "tests/test_phase4am_action_templates_staging_owner_decision_package.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4an_task_groups_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4an_task_groups_native_contract_plan.md",
        "docs/development/phase_4an_task_groups_native_contract_plan.yaml",
        "tools/check_phase4an_task_groups_native_contract_plan.py",
        "tests/test_phase4an_task_groups_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ao_task_groups_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.md",
        "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.yaml",
        "tools/check_phase4ao_task_groups_schema_route_surface_confirmation.py",
        "tests/test_phase4ao_task_groups_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ap_task_groups_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md",
        "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml",
        "tools/check_phase4ap_task_groups_fixture_native_contract_plan.py",
        "tests/test_phase4ap_task_groups_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4aq_task_groups_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4aq_task_groups_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4aq_task_groups_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ar_workflows_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ar_workflows_metadata_plan.md",
        "docs/development/phase_4ar_workflows_metadata_plan.yaml",
        "tools/check_phase4ar_workflows_metadata_plan.py",
        "tests/test_phase4ar_workflows_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4as_workflows_schema_route_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.md",
        "docs/development/phase_4as_workflows_schema_route_surface_confirmation.yaml",
        "tools/check_phase4as_workflows_schema_route_surface_confirmation.py",
        "tests/test_phase4as_workflows_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4at_workflows_fixture_contract_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.md",
        "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml",
        "tools/check_phase4at_workflows_fixture_native_contract_plan.py",
        "tests/test_phase4at_workflows_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4au_workflows_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4au_workflows_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4au_workflows_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4au_workflows_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4av_workflow_nodes_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4av_workflow_nodes_metadata_plan.md",
        "docs/development/phase_4av_workflow_nodes_metadata_plan.yaml",
        "tools/check_phase4av_workflow_nodes_metadata_plan.py",
        "tests/test_phase4av_workflow_nodes_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4aw_workflow_nodes_schema_route_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.md",
        "docs/development/phase_4aw_workflow_nodes_schema_route_surface_confirmation.yaml",
        "tools/check_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
        "tests/test_phase4aw_workflow_nodes_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ax_workflow_nodes_fixture_contract_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.md",
        "docs/development/phase_4ax_workflow_nodes_fixture_native_contract_plan.yaml",
        "tools/check_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
        "tests/test_phase4ax_workflow_nodes_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ay_workflow_nodes_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4ay_workflow_nodes_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4ay_workflow_nodes_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4az_next_candidate_selection_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4az_next_internal_write_candidate_selection.md",
        "docs/development/phase_4az_next_internal_write_candidate_selection.yaml",
        "tools/check_phase4az_next_internal_write_candidate_selection.py",
        "tests/test_phase4az_next_internal_write_candidate_selection.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ba_tasks_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ba_tasks_metadata_plan.md",
        "docs/development/phase_4ba_tasks_metadata_plan.yaml",
        "tools/check_phase4ba_tasks_metadata_plan.py",
        "tests/test_phase4ba_tasks_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bb_tasks_schema_route_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.md",
        "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bb_tasks_schema_route_surface_confirmation.py",
        "tests/test_phase4bb_tasks_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bc_tasks_fixture_contract_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bc_tasks_fixture_native_contract_plan.md",
        "docs/development/phase_4bc_tasks_fixture_native_contract_plan.yaml",
        "tools/check_phase4bc_tasks_fixture_native_contract_plan.py",
        "tests/test_phase4bc_tasks_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bd_tasks_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bd_tasks_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bd_tasks_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bd_tasks_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bd_tasks_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4be_agents_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4be_agents_metadata_plan.md",
        "docs/development/phase_4be_agents_metadata_plan.yaml",
        "tools/check_phase4be_agents_metadata_plan.py",
        "tests/test_phase4be_agents_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bf_agents_schema_route_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bf_agents_schema_route_surface_confirmation.md",
        "docs/development/phase_4bf_agents_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bf_agents_schema_route_surface_confirmation.py",
        "tests/test_phase4bf_agents_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bg_agents_fixture_contract_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bg_agents_fixture_native_contract_plan.md",
        "docs/development/phase_4bg_agents_fixture_native_contract_plan.yaml",
        "tools/check_phase4bg_agents_fixture_native_contract_plan.py",
        "tests/test_phase4bg_agents_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bh_agents_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bh_agents_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bh_agents_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bh_agents_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bi_agent_outputs_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bi_agent_outputs_metadata_plan.md",
        "docs/development/phase_4bi_agent_outputs_metadata_plan.yaml",
        "tools/check_phase4bi_agent_outputs_metadata_plan.py",
        "tests/test_phase4bi_agent_outputs_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bj_agent_outputs_schema_route_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.md",
        "docs/development/phase_4bj_agent_outputs_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
        "tests/test_phase4bj_agent_outputs_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bk_agent_outputs_fixture_contract_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md",
        "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml",
        "tools/check_phase4bk_agent_outputs_fixture_native_contract_plan.py",
        "tests/test_phase4bk_agent_outputs_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bl_agent_outputs_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bl_agent_outputs_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bl_agent_outputs_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bm_agent_runs_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bm_agent_runs_metadata_plan.md",
        "docs/development/phase_4bm_agent_runs_metadata_plan.yaml",
        "tools/check_phase4bm_agent_runs_metadata_plan.py",
        "tests/test_phase4bm_agent_runs_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bn_agent_runs_schema_route_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.md",
        "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.yaml",
        "tools/check_phase4bn_agent_runs_schema_route_surface_confirmation.py",
        "tests/test_phase4bn_agent_runs_schema_route_surface_confirmation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bo_agent_runs_fixture_contract_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bo_agent_runs_fixture_native_contract_plan.md",
        "docs/development/phase_4bo_agent_runs_fixture_native_contract_plan.yaml",
        "tools/check_phase4bo_agent_runs_fixture_native_contract_plan.py",
        "tests/test_phase4bo_agent_runs_fixture_native_contract_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bp_agent_runs_owner_decision_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bp_agent_runs_fixture_native_implementation_owner_decision.md",
        "docs/development/phase_4bp_agent_runs_fixture_native_implementation_owner_decision.yaml",
        "tools/check_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py",
        "tests/test_phase4bp_agent_runs_fixture_native_implementation_owner_decision.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bq_agent_replay_metadata_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bq_agent_replay_metadata_plan.md",
        "docs/development/phase_4bq_agent_replay_metadata_plan.yaml",
        "tools/check_phase4bq_agent_replay_metadata_plan.py",
        "tests/test_phase4bq_agent_replay_metadata_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4by_agent_replay_discovery_contract_bundle_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4by_agent_replay_discovery_contract_bundle.md",
        "docs/development/phase_4by_agent_replay_discovery_contract_bundle.yaml",
        "tools/check_phase4by_agent_replay_discovery_contract_bundle.py",
        "tests/test_phase4by_agent_replay_discovery_contract_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ca_task_groups_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ca_task_groups_repository_adapter_parity_bundle.md",
        "docs/development/phase_4ca_task_groups_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4ca_task_groups_repository_adapter_parity_bundle.py",
        "tools/run_phase4ca_task_groups_adapter_parity.py",
        "tests/test_phase4ca_task_groups_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cb_workflows_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cb_workflows_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cb_workflows_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cb_workflows_repository_adapter_parity_bundle.py",
        "tools/run_phase4cb_workflows_adapter_parity.py",
        "tests/test_phase4cb_workflows_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cc_workflow_nodes_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cc_workflow_nodes_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py",
        "tools/run_phase4cc_workflow_nodes_adapter_parity.py",
        "tests/test_phase4cc_workflow_nodes_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cd_tasks_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cd_tasks_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cd_tasks_repository_adapter_parity_bundle.py",
        "tools/run_phase4cd_tasks_adapter_parity.py",
        "tests/test_phase4cd_tasks_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ce_agents_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ce_agents_repository_adapter_parity_bundle.md",
        "docs/development/phase_4ce_agents_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4ce_agents_repository_adapter_parity_bundle.py",
        "tools/run_phase4ce_agents_adapter_parity.py",
        "tests/test_phase4ce_agents_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cf_agent_outputs_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cf_agent_outputs_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cf_agent_outputs_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cf_agent_outputs_repository_adapter_parity_bundle.py",
        "tools/run_phase4cf_agent_outputs_adapter_parity.py",
        "tests/test_phase4cf_agent_outputs_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cg_agent_runs_adapter_parity_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.md",
        "docs/development/phase_4cg_agent_runs_repository_adapter_parity_bundle.yaml",
        "tools/check_phase4cg_agent_runs_repository_adapter_parity_bundle.py",
        "tools/run_phase4cg_agent_runs_adapter_parity.py",
        "tests/test_phase4cg_agent_runs_repository_adapter_parity_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ch_task_groups_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ch_task_groups_staging_readiness_bundle.md",
        "docs/development/phase_4ch_task_groups_staging_readiness_bundle.yaml",
        "tools/check_phase4ch_task_groups_staging_readiness_bundle.py",
        "tools/run_phase4ch_task_groups_staging_readiness.py",
        "tests/test_phase4ch_task_groups_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ci_workflows_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ci_workflows_staging_readiness_bundle.md",
        "docs/development/phase_4ci_workflows_staging_readiness_bundle.yaml",
        "tools/check_phase4ci_workflows_staging_readiness_bundle.py",
        "tools/run_phase4ci_workflows_staging_readiness.py",
        "tests/test_phase4ci_workflows_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cj_workflow_nodes_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cj_workflow_nodes_staging_readiness_bundle.md",
        "docs/development/phase_4cj_workflow_nodes_staging_readiness_bundle.yaml",
        "tools/check_phase4cj_workflow_nodes_staging_readiness_bundle.py",
        "tools/run_phase4cj_workflow_nodes_staging_readiness.py",
        "tests/test_phase4cj_workflow_nodes_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ck_tasks_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4ck_tasks_staging_readiness_bundle.md",
        "docs/development/phase_4ck_tasks_staging_readiness_bundle.yaml",
        "tools/check_phase4ck_tasks_staging_readiness_bundle.py",
        "tools/run_phase4ck_tasks_staging_readiness.py",
        "tests/test_phase4ck_tasks_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cl_agents_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cl_agents_staging_readiness_bundle.md",
        "docs/development/phase_4cl_agents_staging_readiness_bundle.yaml",
        "tools/check_phase4cl_agents_staging_readiness_bundle.py",
        "tools/run_phase4cl_agents_staging_readiness.py",
        "tests/test_phase4cl_agents_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cm_agent_outputs_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cm_agent_outputs_staging_readiness_bundle.md",
        "docs/development/phase_4cm_agent_outputs_staging_readiness_bundle.yaml",
        "tools/check_phase4cm_agent_outputs_staging_readiness_bundle.py",
        "tools/run_phase4cm_agent_outputs_staging_readiness.py",
        "tests/test_phase4cm_agent_outputs_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cn_agent_runs_staging_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4cn_agent_runs_staging_readiness_bundle.md",
        "docs/development/phase_4cn_agent_runs_staging_readiness_bundle.yaml",
        "tools/check_phase4cn_agent_runs_staging_readiness_bundle.py",
        "tools/run_phase4cn_agent_runs_staging_readiness.py",
        "tests/test_phase4cn_agent_runs_staging_readiness_bundle.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ca_task_group_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/task_group_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cb_workflow_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/workflow_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cc_workflow_node_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/workflow_node_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cd_task_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/task_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4ce_agent_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/agent_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cf_agent_output_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/agent_output_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4cg_agent_run_adapter_runtime_path_as_guarded_policy_file() -> None:
    paths = {
        "aicrm_next/automation_engine/agent_run_sqlalchemy_repository.py",
    }
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4br_task_groups_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4br_task_groups_fixture_runtime.md",
        "tools/check_phase4br_task_groups_fixture_runtime.py",
        "tests/test_phase4br_task_groups_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4br_task_groups_runtime_paths_as_guarded_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
    }
    paths = {
        "aicrm_next/automation_engine/api.py",
        "aicrm_next/automation_engine/application.py",
        "aicrm_next/automation_engine/dto.py",
        "aicrm_next/automation_engine/repo.py",
        "aicrm_next/automation_engine/task_groups.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bs_workflows_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "route ownership switch",
        "timer",
        "nginx",
        "systemd",
    }
    paths = {
        "docs/development/phase_4bs_workflows_fixture_runtime.md",
        "tools/check_phase4bs_workflows_fixture_runtime.py",
        "tests/test_phase4bs_workflows_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bs_workflows_runtime_path_as_guarded_policy_file() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
    }
    paths = {
        "aicrm_next/automation_engine/workflows.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bt_workflow_nodes_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
    }
    paths = {
        "docs/development/phase_4bt_workflow_nodes_fixture_runtime.md",
        "tools/check_phase4bt_workflow_nodes_fixture_runtime.py",
        "tests/test_phase4bt_workflow_nodes_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bt_workflow_nodes_runtime_path_as_guarded_policy_file() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
    }
    paths = {
        "aicrm_next/automation_engine/workflow_nodes.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bu_tasks_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "run-due",
        "task execution",
    }
    paths = {
        "docs/development/phase_4bu_tasks_fixture_runtime.md",
        "tools/check_phase4bu_tasks_fixture_runtime.py",
        "tests/test_phase4bu_tasks_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bu_tasks_runtime_path_as_guarded_policy_file() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "run-due",
        "task execution",
    }
    paths = {
        "aicrm_next/automation_engine/tasks.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bv_agents_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "agent-run execution",
        "llm generation",
    }
    paths = {
        "docs/development/phase_4bv_agents_fixture_runtime.md",
        "tools/check_phase4bv_agents_fixture_runtime.py",
        "tests/test_phase4bv_agents_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bv_agents_runtime_path_as_guarded_policy_file() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "agent-run execution",
        "llm generation",
    }
    paths = {
        "aicrm_next/automation_engine/agents.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bw_agent_outputs_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "agent-run execution",
        "llm generation",
        "file download",
        "export job",
    }
    paths = {
        "docs/development/phase_4bw_agent_outputs_fixture_runtime.md",
        "tools/check_phase4bw_agent_outputs_fixture_runtime.py",
        "tests/test_phase4bw_agent_outputs_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bw_agent_outputs_runtime_path_as_guarded_policy_file() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "agent-run execution",
        "llm generation",
        "file download",
        "export job",
    }
    paths = {
        "aicrm_next/automation_engine/agent_outputs.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bx_agent_runs_runtime_artifacts_as_policy_files() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "run execution",
        "replay execution",
        "orchestration execution",
        "llm generation",
    }
    paths = {
        "docs/development/phase_4bx_agent_runs_fixture_runtime.md",
        "tools/check_phase4bx_agent_runs_fixture_runtime.py",
        "tests/test_phase4bx_agent_runs_fixture_runtime.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase4bx_agent_runs_runtime_path_as_guarded_policy_file() -> None:
    terms = {
        "production write",
        "fallback removal",
        "openclaw",
        "mcp",
        "timer",
        "outbound send",
        "run execution",
        "replay execution",
        "orchestration execution",
        "llm generation",
    }
    paths = {
        "aicrm_next/automation_engine/agent_runs.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6a_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "destructive migration",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6a_owner_production_compat_readiness.md",
        "docs/development/phase_6a_owner_production_compat_readiness.yaml",
        "tools/check_phase6a_owner_production_compat_readiness.py",
        "tests/test_phase6a_owner_production_compat_readiness.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6b_task_groups_canary_plan_artifacts_as_policy_files() -> None:
    terms = {
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "destructive migration",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6b_task_groups_owner_switch_canary_plan.md",
        "docs/development/phase_6b_task_groups_owner_switch_canary_plan.yaml",
        "tools/check_phase6b_task_groups_owner_switch_canary_plan.py",
        "tests/test_phase6b_task_groups_owner_switch_canary_plan.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6c_task_groups_tooling_artifacts_as_policy_files() -> None:
    terms = {
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "destructive migration",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6c_task_groups_owner_switch_tooling.md",
        "docs/development/phase_6c_task_groups_owner_switch_tooling.yaml",
        "tools/check_phase6c_task_groups_owner_switch_tooling.py",
        "tools/run_phase6c_task_groups_owner_switch_canary.py",
        "tools/run_phase6c_task_groups_shadow_compare.py",
        "tools/run_phase6c_task_groups_owner_switch_rollback.py",
        "tests/test_phase6c_task_groups_owner_switch_tooling.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6d_internal_metadata_batch_artifacts_as_policy_files() -> None:
    terms = {
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "destructive migration",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6d_internal_metadata_owner_switch_batch.md",
        "docs/development/phase_6d_internal_metadata_owner_switch_batch.yaml",
        "tools/check_phase6d_internal_metadata_owner_switch_batch.py",
        "tools/run_phase6d_internal_metadata_owner_switch_batch.py",
        "tests/test_phase6d_internal_metadata_owner_switch_batch.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6e_internal_owner_switch_acceptance_artifacts_as_policy_files() -> None:
    terms = {
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "destructive migration",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6e_internal_owner_switch_acceptance.md",
        "docs/development/phase_6e_internal_owner_switch_acceptance.yaml",
        "tools/check_phase6e_internal_owner_switch_acceptance.py",
        "tests/test_phase6e_internal_owner_switch_acceptance.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6f_external_adapter_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "live external call",
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "payment capture",
        "oauth callback cutover",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6f_external_adapter_enablement_readiness.md",
        "docs/development/phase_6f_external_adapter_enablement_readiness.yaml",
        "tools/check_phase6f_external_adapter_enablement_readiness.py",
        "tests/test_phase6f_external_adapter_enablement_readiness.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6g_external_adapter_tooling_artifacts_as_policy_files() -> None:
    terms = {
        "live external call",
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "payment behavior",
        "oauth callback cutover",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.md",
        "docs/development/phase_6g_low_risk_external_adapter_enablement_tooling.yaml",
        "tools/check_phase6g_low_risk_external_adapter_enablement_tooling.py",
        "tools/run_phase6g_media_adapter_enablement_gate.py",
        "tools/run_phase6g_wecom_tags_enablement_gate.py",
        "tools/run_phase6g_openclaw_mcp_enablement_gate.py",
        "tests/test_phase6g_low_risk_external_adapter_enablement_tooling.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6h_production_compat_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "production_compat",
        "wildcard narrowing",
        "fallback removal",
        "production owner switch",
        "live external call",
        "timer",
        "automation execution",
        "outbound send",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.md",
        "docs/development/phase_6h_production_compat_exact_route_narrowing_readiness.yaml",
        "tools/check_phase6h_production_compat_exact_route_narrowing_readiness.py",
        "tools/run_phase6h_production_compat_exact_route_shadow_compare.py",
        "tests/test_phase6h_production_compat_exact_route_narrowing_readiness.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6i_acceptance_artifacts_as_policy_files() -> None:
    terms = {
        "live external call",
        "production owner switch",
        "fallback removal",
        "production_compat",
        "timer",
        "automation execution",
        "outbound send",
        "payment behavior",
        "oauth callback cutover",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.md",
        "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.yaml",
        "tools/check_phase6i_external_enablement_and_compat_readiness_acceptance.py",
        "tests/test_phase6i_external_enablement_and_compat_readiness_acceptance.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6j_timer_execution_readiness_artifacts_as_policy_files() -> None:
    terms = {
        "timer",
        "run-due",
        "automation execution",
        "outbound send",
        "live external call",
        "production owner switch",
        "production_compat",
        "fallback removal",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6j_timer_execution_readiness.md",
        "docs/development/phase_6j_timer_execution_readiness.yaml",
        "tools/check_phase6j_timer_execution_readiness.py",
        "tests/test_phase6j_timer_execution_readiness.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6k_single_scope_execution_canary_artifacts_as_policy_files() -> None:
    terms = {
        "timer",
        "run-due",
        "automation execution",
        "outbound send",
        "live external call",
        "production owner switch",
        "production_compat",
        "fallback removal",
        "delete_ready",
    }
    paths = {
        "docs/development/phase_6k_single_scope_execution_canary_tooling.md",
        "docs/development/phase_6k_single_scope_execution_canary_tooling.yaml",
        "tools/check_phase6k_single_scope_execution_canary_tooling.py",
        "tools/run_phase6k_single_scope_execution_canary.py",
        "tests/test_phase6k_single_scope_execution_canary_tooling.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_treats_phase6l_aggregate_acceptance_artifacts_as_policy_files() -> None:
    terms = {
        "fallback removal",
        "production_compat",
        "delete_ready",
        "timer",
        "automation execution",
        "outbound send",
        "live external call",
        "production owner switch",
    }
    paths = {
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
        "docs/development/post_phase7_first_new_feature_intake.md",
        "docs/development/post_phase7_first_new_feature_intake.yaml",
        "docs/development/post_phase7_owner_feature_selection.md",
        "docs/development/post_phase7_owner_feature_selection.yaml",
        "docs/development/post_phase7_owner_approved_cleanup_track_activation.md",
        "docs/development/post_phase7_owner_approved_cleanup_track_activation.yaml",
        "docs/development/post_phase7_cleanup_task_groups_evidence_refresh.md",
        "docs/development/post_phase7_cleanup_task_groups_evidence_refresh.yaml",
        "docs/development/post_phase7_cleanup_workflow_nodes_evidence_refresh.md",
        "docs/development/post_phase7_cleanup_workflow_nodes_evidence_refresh.yaml",
        "docs/development/post_phase7_cleanup_blocker_acceptance.md",
        "docs/development/post_phase7_cleanup_blocker_acceptance.yaml",
        "docs/development/post_phase7_cleanup_owner_evidence_collection.md",
        "docs/development/post_phase7_cleanup_owner_evidence_collection.yaml",
        "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.md",
        "docs/development/post_phase7_cleanup_owner_evidence_waiting_acceptance.yaml",
        "docs/development/post_phase7_cleanup_owner_evidence_package_generation.md",
        "docs/development/post_phase7_cleanup_owner_evidence_package_generation.yaml",
        "aicrm_next/integration_gateway/legacy_flask_facade.py",
        "tools/check_legacy_facade_growth_freeze.py",
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
        "tools/check_post_phase7_first_new_feature_intake.py",
        "tools/check_post_phase7_owner_feature_selection.py",
        "tools/check_post_phase7_owner_approved_cleanup_track_activation.py",
        "tools/check_post_phase7_cleanup_task_groups_evidence_refresh.py",
        "tools/check_post_phase7_cleanup_workflow_nodes_evidence_refresh.py",
        "tools/check_post_phase7_cleanup_blocker_acceptance.py",
        "tools/check_post_phase7_cleanup_owner_evidence_collection.py",
        "tools/check_post_phase7_cleanup_owner_evidence_waiting_acceptance.py",
        "tools/check_post_phase7_cleanup_owner_evidence_package_generation.py",
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
        "tests/test_post_phase7_first_new_feature_intake.py",
        "tests/test_post_phase7_owner_feature_selection.py",
        "tests/test_post_phase7_owner_approved_cleanup_track_activation.py",
        "tests/test_post_phase7_cleanup_task_groups_evidence_refresh.py",
        "tests/test_post_phase7_cleanup_workflow_nodes_evidence_refresh.py",
        "tests/test_post_phase7_cleanup_blocker_acceptance.py",
        "tests/test_post_phase7_cleanup_owner_evidence_collection.py",
        "tests/test_post_phase7_cleanup_owner_evidence_waiting_acceptance.py",
        "tests/test_post_phase7_cleanup_owner_evidence_package_generation.py",
    }
    assert runner.diff_hits_stop_condition(paths, terms) == []


def test_runner_uses_single_flight_lock(tmp_path: Path) -> None:
    lock = tmp_path / "lock"
    with lock.open("w", encoding="utf-8") as handle:
        import fcntl

        fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        output = tmp_path / "report.json"
        result = runner.main(["--skip-github", "--lock-file", str(lock), "--output-json", str(output)])
        assert result == 0
        report = json.loads(output.read_text(encoding="utf-8"))
        assert report["result_status"] == "already_running"


def test_script_uses_configurable_codex_command_and_logs() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "AICRM_CODEX_COMMAND" in text
    assert "logs/codex-autopilot" in text
    assert "git fetch origin main --prune" in text
    assert "tools/run_codex_autopilot_tick.py" in text


def test_runner_admin_merges_safe_green_open_pr(monkeypatch, tmp_path: Path) -> None:
    def fake_fetch_open_autopilot_prs(skip_github: bool):
        return (
            [
                {
                    "number": 123,
                    "url": "https://github.com/qianlan333/AI-CRM/pull/123",
                    "labels": [{"name": "autopilot-safe"}],
                    "statusCheckRollup": [
                        {"name": "pr-smoke", "status": "COMPLETED", "conclusion": "SUCCESS"},
                    ],
                }
            ],
            [],
        )

    calls: list[list[str]] = []

    def fake_run_command(args: list[str], timeout: int = 60):
        calls.append(args)
        if args[:3] == ["gh", "pr", "merge"]:
            return 0, "merged", ""
        return 0, "", ""

    monkeypatch.setattr(runner, "fetch_open_autopilot_prs", fake_fetch_open_autopilot_prs)
    monkeypatch.setattr(runner, "run_command", fake_run_command)
    args = runner.parse_args(["--skip-github", "--lock-file", str(tmp_path / "lock")])
    report = runner.build_tick_report(args)
    assert report["result_status"] == "open_autopilot_pr_admin_merged"
    assert report["auto_merge_allowed"] is True
    assert report["admin_merge_allowed"] is True
    assert any(call[:3] == ["gh", "pr", "merge"] for call in calls)


def test_runner_does_not_admin_merge_owner_decision_pr(monkeypatch, tmp_path: Path) -> None:
    def fake_fetch_open_autopilot_prs(skip_github: bool):
        return (
            [
                {
                    "number": 124,
                    "url": "https://github.com/qianlan333/AI-CRM/pull/124",
                    "labels": [{"name": "owner-decision-required"}, {"name": "autopilot-safe"}],
                    "statusCheckRollup": [
                        {"name": "pr-smoke", "status": "COMPLETED", "conclusion": "SUCCESS"},
                    ],
                }
            ],
            [],
        )

    monkeypatch.setattr(runner, "fetch_open_autopilot_prs", fake_fetch_open_autopilot_prs)
    args = runner.parse_args(["--skip-github", "--lock-file", str(tmp_path / "lock")])
    report = runner.build_tick_report(args)
    assert report["result_status"] == "owner_decision_required"
    assert report["admin_merge_allowed"] is False


def test_runbook_declares_runtime_boundaries() -> None:
    text = RUNBOOK.read_text(encoding="utf-8")
    for phrase in (
        "does not change production routes",
        "may use admin merge for eligible low-risk PRs",
        "20-35 minute compressed bundles",
        "does not authorize production route switch",
        "Risk / rollback",
        "Autopilot runtime decision",
    ):
        assert phrase in text


def test_no_runtime_files_changed_if_git_diff_available() -> None:
    changed = runner.changed_files()
    assert "aicrm_next/main.py" not in changed
    assert "aicrm_next/production_compat/api.py" not in changed
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)


def test_shell_script_is_not_hardcoded_to_one_codex_binary() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'CODEX_COMMAND="${AICRM_CODEX_COMMAND:-codex}"' in text
    assert "$CODEX_COMMAND" in text


def test_runner_does_not_import_runtime_modules() -> None:
    text = TOOL.read_text(encoding="utf-8")
    forbidden = ("import aicrm_next", "from aicrm_next", "import wecom_ability_service", "from wecom_ability_service")
    for item in forbidden:
        assert item not in text
