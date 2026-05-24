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
    assert data["current_phase"] == "phase_4_internal_write"
    assert data["active_candidate"] == "/api/admin/automation-conversion/workflow-nodes*"
    assert data["capability_owner"] == "aicrm_next.automation_engine"
    assert data["last_merged_pr"] == "#652"


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


def test_next_allowed_actions_are_phase_4an_task_groups_only() -> None:
    data = checker.load_yaml(STATE)
    assert set(data["next_allowed_actions"]) == checker.ALLOWED_NEXT_ACTIONS


def test_forbidden_without_owner_approval_covers_high_risk_actions() -> None:
    data = checker.load_yaml(STATE)
    forbidden = {item.lower() for item in data["forbidden_without_owner_approval"]}
    assert checker.REQUIRED_FORBIDDEN <= forbidden


def test_work_package_policy_sets_bounded_low_risk_granularity() -> None:
    data = checker.load_yaml(STATE)
    policy = data["work_package_policy"]
    assert policy["selection_unit"] == "bounded_low_risk_work_package"
    assert policy["target_duration_minutes_min"] == 10
    assert policy["target_duration_minutes_max"] == 13
    for field in checker.REQUIRED_WORK_PACKAGE_POLICY_TRUE:
        assert policy[field] is True
    assert policy["admin_merge_for_owner_decision_package_allowed"] is False


def test_active_candidate_in_manifest_and_backlog() -> None:
    candidate = checker.load_yaml(STATE)["active_candidate"]
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
        and item["owner_approval_required"] is True
        and str(item["paused_by_pr"]).strip()
        for item in paused
    )
    readiness = data["task_groups_readiness"]
    assert readiness["native_contract_planning_started"] is True
    assert readiness["native_contract_planning_completed"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_workflows_selected_for_next_metadata_planning_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    readiness = data["workflows_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
    assert readiness["owner_decision_required"] is True
    assert readiness["paused"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_workflow_nodes_selected_for_metadata_planning_without_production_readiness() -> None:
    data = checker.load_yaml(STATE)
    assert data["active_candidate"] == "/api/admin/automation-conversion/workflow-nodes*"
    readiness = data["workflow_nodes_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["fixture_native_contract_planning_ready"] is False
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


def test_no_runtime_files_changed_if_git_diff_available() -> None:
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
    assert not any(path.startswith("aicrm_next/") for path in changed)
    assert not any(path.startswith("wecom_ability_service/") for path in changed)
    assert not any(path.startswith("migrations/") for path in changed)
    assert not any(path.startswith("deploy/") for path in changed)
