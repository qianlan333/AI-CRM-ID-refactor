from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bk_agent_outputs_fixture_native_contract_plan as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.md"
PLAN_YAML = ROOT / "docs/development/phase_4bk_agent_outputs_fixture_native_contract_plan.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_plan_is_agent_outputs_list_detail_fixture_only() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["status"] == "phase_4bk_agent_outputs_fixture_native_contract_planning_no_runtime_change"
    assert data["route_family"] == checker.ROUTE
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    route_scopes = {(item["method"], item["scope"]) for item in data["planned_fixture_routes"]}
    assert route_scopes == {("GET", "fixture_local_metadata_list"), ("GET", "fixture_local_metadata_detail")}


def test_fixture_seed_is_deterministic_and_local() -> None:
    data = checker.load_yaml(PLAN_YAML)
    seed = data["fixture_seed"]
    assert seed["deterministic"] is True
    assert seed["production_data_allowed"] is False
    assert {"phase4bk_output_reply_draft", "phase4bk_output_route_decision"} <= set(seed["output_ids"])
    assert checker.REQUIRED_FIELDS <= set(seed["required_fields"])


def test_list_and_detail_contracts_are_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_LIST_QUERY <= set(data["list_contract"]["query"])
    assert checker.REQUIRED_LIST_RESPONSE_KEYS <= set(data["list_contract"]["response_keys"])
    assert data["list_contract"]["ordering"] == "created_at_desc_id_desc"
    assert data["list_contract"]["export_rows_excluded"] is True
    assert checker.REQUIRED_DETAIL_RESPONSE_KEYS <= set(data["detail_contract"]["response_keys"])
    assert data["detail_contract"]["not_found_status"] == 404
    assert data["detail_contract"]["missing_output_rejected_without_side_effect"] is True


def test_visibility_and_side_effect_safety() -> None:
    data = checker.load_yaml(PLAN_YAML)
    visibility = data["visibility_contract"]
    assert visibility["masked_visibility_required"] is True
    assert visibility["console_visibility_fixture_mode_allowed"] is True
    assert visibility["raw_output_not_production_evidence"] is True
    assert visibility["normalized_payload_not_production_evidence"] is True
    assert visibility["production_data_allowed"] is False
    for field in checker.SIDE_EFFECT_FALSE_FIELDS:
        assert data["side_effect_safety"][field] is False


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_phase_4bl_owner_decision() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] in {checker.ROUTE, "/api/admin/automation-conversion/agent-runs*"}
    assert state["last_merged_pr"] in {"#667", "#668"}
    assert state["last_attempted_action"] in {
        "phase_4bk_agent_outputs_fixture_native_contract_planning",
        "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision",
    }
    assert state["last_created_pr"] in {"#668", "#669"}
    assert state["recommended_next_pr"] in {
        "phase_4bl_agent_outputs_fixture_native_implementation_owner_decision",
        "phase_4bm_agent_runs_metadata_planning",
    }
    assert state["owner_approval_required"] in {False, True}
    assert state["next_allowed_actions"] in [
        ["phase_4bl_agent_outputs_fixture_native_implementation_owner_decision"],
        ["phase_4bm_agent_runs_metadata_planning"],
    ]
    assert "phase_4bk_agent_outputs_fixture_native_contract_planning_completed" in state["completed_steps"]


def test_agent_outputs_readiness_requires_owner_decision_without_runtime_readiness() -> None:
    readiness = checker.load_yaml(STATE)["agent_outputs_readiness"]
    assert readiness["fixture_native_contract_planning_completed"] is True
    assert readiness["fixture_native_implementation_requires_owner_decision"] is True
    assert readiness["owner_decision_required"] is True
    assert readiness.get("paused") in {None, True}
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4bl_recommendation_does_not_allow_production_actions() -> None:
    rec = checker.load_yaml(PLAN_YAML)["phase_4bl_recommendation"]
    assert rec["recommended_next_step"] == "agent_outputs_fixture_native_implementation_owner_decision"
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
