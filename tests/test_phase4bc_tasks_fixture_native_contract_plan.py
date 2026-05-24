from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bc_tasks_fixture_native_contract_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bc_tasks_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4bc_tasks_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_planned_fixture_routes_are_list_create_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    scopes = {(item["method"], item["scope"]) for item in data["planned_fixture_routes"]}
    assert scopes == {("GET", "fixture_local_list"), ("POST", "fixture_local_metadata_create")}
    excluded = {item["path"] for item in data["excluded_routes"]}
    assert "/api/admin/automation-conversion/tasks/run-due" in excluded
    assert "/api/admin/automation-conversion/executions*" in excluded


def test_fixture_seed_is_deterministic_and_complete() -> None:
    seed = checker.load_yaml(PLAN_YAML)["fixture_seed"]
    assert seed["deterministic"] is True
    assert seed["production_data_allowed"] is False
    assert {"phase4bc_daily_followup_task", "phase4bc_audience_entered_task"} <= set(seed["task_codes"])
    assert checker.REQUIRED_FIELDS <= set(seed["required_fields"])


def test_list_and_create_contracts_are_safe() -> None:
    data = checker.load_yaml(PLAN_YAML)
    list_contract = data["list_contract"]
    create_contract = data["create_contract"]
    assert list_contract["archived_tasks_excluded_by_default"] is True
    assert {"ok", "tasks", "groups", "side_effect_safety"} <= set(list_contract["response_keys"])
    assert {"task_name", "idempotency_key"} <= set(create_contract["required_payload"])
    assert create_contract["missing_name_rejected"] is True
    assert create_contract["invalid_status_rejected"] is True
    assert create_contract["dangerous_fields_rejected"] is True
    assert create_contract["execution_fields_rejected"] is True


def test_idempotency_audit_and_side_effect_safety_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in ("route_family_scope_required", "operation_scope_required", "operator_scope_required", "idempotency_key_required", "replay_same_hash", "conflict_different_hash"):
        assert data["idempotency"][field] is True
    for field in ("audit_event_required", "after_snapshot_required", "rollback_payload_required", "side_effect_safety_required"):
        assert data["audit"][field] is True
    for field in checker.SIDE_EFFECT_FALSE_FIELDS:
        assert data["side_effect_safety"][field] is False


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_phase_4bd_owner_decision() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] in {checker.ROUTE, "/api/admin/automation-conversion/agents*"}
    assert "phase_4bc_tasks_fixture_native_contract_planning_completed" in state["completed_steps"]


def test_tasks_readiness_requires_owner_decision_without_runtime_readiness() -> None:
    readiness = checker.load_yaml(STATE)["tasks_readiness"]
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
    assert readiness["owner_decision_required"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


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
