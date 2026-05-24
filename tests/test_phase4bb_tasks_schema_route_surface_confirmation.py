from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bb_tasks_schema_route_surface_confirmation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4bb_tasks_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_route_surface_complete_but_first_subset_is_list_create_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    surface = data["confirmed_route_surface"]
    routes = {(item["method"], item["path"]) for item in surface["legacy_registered_routes"]}
    assert routes == checker.REQUIRED_LEGACY_ROUTES
    assert set(data["recommended_first_native_subset"]) == {"list_operation_tasks", "create_operation_task_metadata_only"}
    assert "run_due_operation_tasks" in set(data["deferred_to_separate_pr"])


def test_schema_confirmation_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    schema = data["confirmed_schema"]
    assert schema["main_table"] == "automation_operation_task"
    assert checker.REQUIRED_COLUMNS <= set(schema["columns"])
    assert checker.REQUIRED_INDEXES <= set(schema["indexes"])
    assert checker.REQUIRED_RELATED_TABLES <= set(schema["related_tables"])
    assert schema["relationship_behavior"]["execution_tables_excluded_from_metadata_subset"] is True


def test_contract_confirms_list_create_metadata_only() -> None:
    contract = checker.load_yaml(PLAN_YAML)["confirmed_contract"]
    assert contract["list"]["archived_tasks_excluded_by_default"] is True
    assert "program_id" in set(contract["list"]["query"])
    assert contract["create"]["success_status"] == 201
    assert "task_name" in set(contract["create"]["required_payload"])
    assert "task" in set(contract["create"]["response_keys"])


def test_authorizations_and_exclusions_are_safe() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False
    for field in checker.EXCLUDED_TRUE_FIELDS:
        assert data["excluded_scope"][field] is True


def test_phase_execution_state_advances_to_phase_4bc() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.ROUTE
    assert "phase_4bb_tasks_schema_route_surface_confirmation_completed" in state["completed_steps"]


def test_tasks_readiness_enables_fixture_contract_planning_only() -> None:
    readiness = checker.load_yaml(STATE)["tasks_readiness"]
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["run_due_excluded"] is True
    assert readiness["task_execution_excluded"] is True
    assert readiness["workflow_execution_excluded"] is True
    assert readiness["timer_execution_excluded"] is True
    assert readiness["outbound_send_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4bc_recommendation_does_not_allow_production_actions() -> None:
    rec = checker.load_yaml(PLAN_YAML)["phase_4bc_recommendation"]
    assert rec["recommended_next_step"] == "tasks_fixture_native_contract_planning"
    assert rec["production_write_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["production_write_canary_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text


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
