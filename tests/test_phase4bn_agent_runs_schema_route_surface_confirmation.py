from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bn_agent_runs_schema_route_surface_confirmation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4bn_agent_runs_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_plan_confirms_agent_runs_schema_route_surface() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["status"] == "phase_4bn_agent_runs_schema_route_surface_confirmation_no_runtime_change"
    assert data["route_family"] == checker.ROUTE
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    assert data["legacy_fallback_retained"] is True


def test_route_surface_list_detail_only_with_runtime_deferred() -> None:
    data = checker.load_yaml(PLAN_YAML)
    surface = data["confirmed_route_surface"]
    assert checker.REQUIRED_PRODUCTION_COMPAT_PATTERNS <= set(surface["production_compat_patterns"])
    routes = {(item["method"], item["path"], item["status"]) for item in surface["legacy_api_routes"]}
    assert checker.REQUIRED_LEGACY_ROUTES <= routes
    assert checker.REQUIRED_FIRST_NATIVE_SUBSET <= set(surface["first_native_subset"])


def test_schema_surface_and_relationship_boundaries() -> None:
    data = checker.load_yaml(PLAN_YAML)
    schema = data["confirmed_schema_surface"]
    assert schema["metadata_table"] == "automation_agent_run"
    assert checker.REQUIRED_READ_MODEL_COLUMNS <= set(schema["read_model_columns"])
    assert checker.REQUIRED_LIST_RESPONSE_KEYS <= set(schema["legacy_response_keys"]["list"])
    assert checker.REQUIRED_DETAIL_RESPONSE_KEYS <= set(schema["legacy_response_keys"]["detail"])
    assert checker.REQUIRED_DEFERRED_TABLES <= set(schema["related_runtime_tables_deferred"])
    relationships = schema["relationship_boundaries"]
    assert relationships["agent_outputs_payloads_metadata_only"] is True
    assert relationships["llm_call_log_excluded_from_metadata_subset"] is True
    assert relationships["orchestration_events_excluded_from_metadata_subset"] is True
    assert relationships["workflow_execution_excluded_from_metadata_subset"] is True


def test_native_contract_boundary_and_deferred_scope() -> None:
    data = checker.load_yaml(PLAN_YAML)
    boundary = data["native_contract_boundary"]
    assert checker.REQUIRED_FIRST_NATIVE_SUBSET <= set(boundary["first_native_subset"])
    assert checker.REQUIRED_NEXT_REQUIREMENTS <= set(boundary["next_contract_planning_requirements"])
    for field in checker.DEFERRED_TRUE_FIELDS:
        assert data["deferred_scope"][field] is True


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_phase_4bo() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.ROUTE
    assert state["last_merged_pr"] in {"#670", "#671"}
    assert state["last_attempted_action"] in {
        "phase_4bn_agent_runs_schema_route_surface_confirmation",
        "phase_4bo_agent_runs_fixture_native_contract_planning",
    }
    assert state["last_created_pr"] in {"#671", "#672"}
    assert state["recommended_next_pr"] in {
        "phase_4bo_agent_runs_fixture_native_contract_planning",
        "phase_4bp_agent_runs_fixture_native_implementation_owner_decision",
    }
    assert state["owner_approval_required"] in {False, True}
    assert state["next_allowed_actions"] in [
        ["phase_4bo_agent_runs_fixture_native_contract_planning"],
        ["phase_4bp_agent_runs_fixture_native_implementation_owner_decision"],
    ]
    assert "phase_4bn_agent_runs_schema_route_surface_confirmation_completed" in state["completed_steps"]


def test_agent_runs_readiness_ready_for_fixture_contract_only() -> None:
    readiness = checker.load_yaml(STATE)["agent_runs_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness.get("fixture_native_contract_planning_completed") in {None, True}
    assert readiness.get("fixture_native_implementation_requires_owner_decision") in {False, True}
    assert readiness.get("owner_decision_required") in {False, True}
    assert readiness["run_creation_excluded"] is True
    assert readiness["run_execution_excluded"] is True
    assert readiness["replay_execution_excluded"] is True
    assert readiness["orchestration_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["deepseek_adapter_excluded"] is True
    assert readiness["openclaw_mcp_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4bo_recommendation_does_not_allow_production_actions() -> None:
    rec = checker.load_yaml(PLAN_YAML)["phase_4bo_recommendation"]
    assert rec["recommended_next_step"] == "agent_runs_fixture_native_contract_planning"
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
