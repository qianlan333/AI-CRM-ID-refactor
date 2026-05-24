from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4ap_task_groups_fixture_native_contract_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4ap_task_groups_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_planned_fixture_routes_are_list_create_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    routes = {(item["method"], item["scope"]) for item in data["planned_fixture_routes"]}
    assert routes == {("GET", "fixture_local_list"), ("POST", "fixture_local_metadata_create")}


def test_fixture_seed_is_deterministic_and_safe() -> None:
    data = checker.load_yaml(PLAN_YAML)
    seed = data["fixture_seed"]
    assert seed["deterministic"] is True
    assert seed["production_data_allowed"] is False
    assert checker.REQUIRED_FIELDS <= set(seed["required_fields"])


def test_list_and_create_contracts_include_safety_and_idempotency() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["list_contract"]["archived_groups_excluded_by_default"] is True
    assert "side_effect_safety" in data["list_contract"]["response_keys"]
    assert {"group_name", "idempotency_key"} <= set(data["create_contract"]["required_payload"])
    assert data["create_contract"]["missing_name_rejected"] is True
    assert data["create_contract"]["duplicate_group_name_rejected"] is True
    assert data["idempotency"]["replay_same_hash"] is True
    assert data["idempotency"]["conflict_different_hash"] is True
    assert data["audit"]["rollback_payload_required"] is True


def test_high_risk_authorizations_and_side_effects_are_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False
    for field in checker.SIDE_EFFECT_FALSE_FIELDS:
        assert data["side_effect_safety"][field] is False


def test_phase_execution_state_advances_to_phase_4aq_owner_decision() -> None:
    state = checker.load_yaml(STATE)
    assert state["last_merged_pr"] == "#646"
    assert state["last_attempted_action"] == "phase_4ap_task_groups_fixture_native_contract_planning"
    assert state["recommended_next_pr"] == "phase_4aq_task_groups_fixture_native_implementation_owner_decision"
    assert state["owner_approval_required"] is True
    assert "phase_4ap_task_groups_fixture_native_contract_planning_completed" in state["completed_steps"]
    assert state["next_allowed_actions"] == ["phase_4aq_task_groups_fixture_native_implementation_owner_decision"]
    readiness = state["task_groups_readiness"]
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
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
