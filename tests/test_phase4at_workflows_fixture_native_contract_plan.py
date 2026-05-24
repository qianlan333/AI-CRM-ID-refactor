from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4at_workflows_fixture_native_contract_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4at_workflows_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4at_workflows_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_planned_fixture_routes_are_list_and_create_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    routes = {(item["method"], item["path"], item["scope"]) for item in data["planned_fixture_routes"]}
    assert routes == {
        ("GET", "/api/admin/automation-conversion/workflows", "fixture_local_list"),
        ("POST", "/api/admin/automation-conversion/workflows", "fixture_local_metadata_create"),
    }
    excluded = {item["path"] for item in data["excluded_routes"]}
    assert "/api/admin/automation-conversion/workflows/{workflow_id}" in excluded
    assert "/api/admin/automation-conversion/workflow-nodes*" in excluded
    assert "/api/admin/automation-conversion/tasks*" in excluded
    assert "/api/admin/automation-conversion/tasks/run-due" in excluded
    assert "/api/admin/automation-conversion/executions*" in excluded


def test_fixture_seed_is_deterministic_and_non_production() -> None:
    data = checker.load_yaml(PLAN_YAML)
    seed = data["fixture_seed"]
    assert seed["deterministic"] is True
    assert seed["production_data_allowed"] is False
    assert {"phase4at_default_workflow", "phase4at_followup_workflow"} <= set(seed["workflow_codes"])
    assert checker.REQUIRED_FIELDS <= set(seed["required_fields"])


def test_contracts_include_idempotency_audit_rollback_and_safety() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert {"ok", "source_status", "route_owner", "workflows", "total", "count", "filters", "side_effect_safety"} <= set(data["list_contract"]["response_keys"])
    assert data["list_contract"]["archived_workflows_excluded_by_default"] is True
    assert data["list_contract"]["ordering"] == "updated_at_desc_id_desc"
    assert {"workflow_name", "idempotency_key"} <= set(data["create_contract"]["required_payload"])
    assert {"ok", "workflow", "audit_event", "rollback_payload", "idempotent_replay", "side_effect_safety"} <= set(data["create_contract"]["response_keys"])
    for field in ("missing_name_rejected", "duplicate_workflow_code_rejected", "invalid_status_rejected", "dangerous_fields_rejected"):
        assert data["create_contract"][field] is True
    for field in ("route_family_scope_required", "operation_scope_required", "operator_scope_required", "idempotency_key_required", "replay_same_hash", "conflict_different_hash"):
        assert data["idempotency"][field] is True
    assert data["audit"]["audit_event_required"] is True
    assert data["audit"]["before_snapshot_for_create"] == "empty_object"
    assert data["audit"]["rollback_payload_required"] is True


def test_authorizations_and_side_effects_are_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False
    for field in checker.SIDE_EFFECT_FALSE_FIELDS:
        assert data["side_effect_safety"][field] is False


def test_phase_execution_state_advances_to_owner_decision() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.ROUTE
    assert state["last_merged_pr"] == "#650"
    assert state["last_attempted_action"] == "phase_4at_workflows_fixture_native_contract_planning"
    assert state["recommended_next_pr"] == "phase_4au_workflows_fixture_native_implementation_owner_decision"
    assert state["owner_approval_required"] is True
    assert "phase_4at_workflows_fixture_native_contract_planning_completed" in state["completed_steps"]
    assert state["next_allowed_actions"] == ["phase_4au_workflows_fixture_native_implementation_owner_decision"]
    readiness = state["workflows_readiness"]
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4au_recommendation_does_not_allow_production_work() -> None:
    data = checker.load_yaml(PLAN_YAML)
    rec = data["phase_4au_recommendation"]
    assert rec["recommended_next_step"] == "workflows_fixture_native_implementation_owner_decision"
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
