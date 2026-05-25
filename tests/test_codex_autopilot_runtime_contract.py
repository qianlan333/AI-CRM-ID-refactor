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


def test_runner_generates_prompt_without_github_when_no_open_pr(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.md"
    report = runner.main(["--skip-github", "--prompt-output", str(prompt), "--lock-file", str(tmp_path / "lock")])
    assert report == 0
    assert prompt.exists()
    prompt_text = prompt.read_text(encoding="utf-8")
    assert "phase_execution_state.yaml" in prompt_text
    assert "check_autonomous_development_loop.py" in prompt_text
    assert "check_automerge_eligibility.py" in prompt_text
    assert "bounded low-risk work package" in prompt_text
    assert "10-13 minutes" in prompt_text
    assert "phase_4bv_agents_fixture_native_list_create_runtime" in prompt_text


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
        "10-13 minute work packages",
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
