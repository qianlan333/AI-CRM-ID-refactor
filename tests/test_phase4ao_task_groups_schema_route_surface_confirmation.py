from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4ao_task_groups_schema_route_surface_confirmation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4ao_task_groups_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_route_surface_confirmed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    surface = data["confirmed_route_surface"]
    assert "/api/admin/automation-conversion/task-groups" in surface["production_compat_patterns"]
    assert "/api/admin/automation-conversion/task-groups/wildcard_path" in surface["production_compat_patterns"]
    methods = {item["method"] for item in surface["legacy_registered_routes"]}
    assert methods == {"GET", "POST", "PUT", "DELETE"}


def test_schema_surface_confirmed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    schema = data["confirmed_schema"]
    assert schema["main_table"] == "automation_operation_task_group"
    assert checker.REQUIRED_COLUMNS <= set(schema["columns"])
    assert "idx_automation_operation_task_group_program" in schema["index"]
    assert "automation_operation_task" in schema["related_tables"]
    assert schema["relationship_behavior"]["delete_contract"] == "archive_group_and_ungroup_tasks"


def test_contract_surface_identifies_list_create_update_archive() -> None:
    data = checker.load_yaml(PLAN_YAML)
    contract = data["confirmed_contract"]
    assert contract["list"]["archived_groups_excluded_by_default"] is True
    assert contract["list"]["ordering"] == "sort_order_asc_id_asc"
    assert contract["create"]["success_status"] == 201
    assert "group_name" in contract["create"]["required_payload"]
    assert contract["update"]["missing_group_status"] == 404
    assert contract["delete"]["behavior"] == "archive_group_and_ungroup_tasks"


def test_first_native_subset_is_list_create_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert set(data["recommended_first_native_subset"]) == {"list_task_groups", "create_task_group"}
    assert {"update_task_group", "delete_or_archive_task_group", "task_routes", "run_due"} <= set(data["deferred_to_separate_pr"])


def test_all_high_risk_authorizations_false_and_exclusions_true() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False
    for field in checker.EXCLUDED_TRUE_FIELDS:
        assert data["excluded_scope"][field] is True


def test_phase_execution_state_advances_to_phase_4ap() -> None:
    state = checker.load_yaml(STATE)
    assert "phase_4ao_task_groups_schema_route_surface_confirmation_completed" in state["completed_steps"]
    assert state["task_groups_readiness"]["schema_route_surface_confirmed"] is True
    assert state["task_groups_readiness"]["fixture_native_contract_planning_ready"] is True
    assert state["task_groups_readiness"]["production_owner_switch_ready"] is False
    assert state["task_groups_readiness"]["production_write_ready"] is False
    assert state["task_groups_readiness"]["fallback_removal_ready"] is False
    assert state["task_groups_readiness"]["delete_ready"] is False


def test_phase_4ap_recommendation_keeps_production_locked() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4ap_recommendation"]
    assert rec["recommended_next_step"] == "task_groups_fixture_native_contract_planning"
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
