from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4bf_agents_schema_route_surface_confirmation as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4bf_agents_schema_route_surface_confirmation.md"
PLAN_YAML = ROOT / "docs/development/phase_4bf_agents_schema_route_surface_confirmation.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)


def test_plan_confirms_agents_route_surface_without_owner_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["status"] == "phase_4bf_agents_schema_route_surface_confirmation_no_runtime_change"
    assert data["route_family"] == checker.AGENTS
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    assert data["legacy_fallback_retained"] is True
    surface = data["confirmed_route_surface"]
    assert checker.REQUIRED_PRODUCTION_PATTERNS <= set(surface["production_compat_patterns"])
    assert checker.REQUIRED_LEGACY_ROUTES <= checker._legacy_route_pairs(surface["legacy_api_routes"])


def test_schema_surface_records_metadata_and_defers_runtime_tables() -> None:
    data = checker.load_yaml(PLAN_YAML)
    schema = data["confirmed_schema_surface"]
    assert schema["metadata_table"] == "automation_agent_config"
    assert checker.REQUIRED_READ_MODEL_COLUMNS <= set(schema["read_model_columns"])
    assert checker.REQUIRED_METADATA_FIELDS <= set(schema["legacy_metadata_contract_fields"])
    assert checker.REQUIRED_RELATED_RUNTIME_TABLES <= set(schema["related_runtime_tables_deferred"])
    relationships = schema["relationship_boundaries"]
    assert relationships["agent_run_tables_excluded_from_metadata_subset"] is True
    assert relationships["output_tables_excluded_from_metadata_subset"] is True
    assert relationships["llm_call_log_excluded_from_metadata_subset"] is True


def test_native_boundary_is_metadata_only_and_deferred_scope_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    boundary = data["native_contract_boundary"]
    assert checker.REQUIRED_FIRST_NATIVE_SUBSET <= set(boundary["first_native_subset"])
    assert checker.REQUIRED_DEFERRED_SCOPE <= set(boundary["deferred_to_separate_pr"])
    assert "no_agent_run_execution" in boundary["next_contract_planning_requirements"]
    assert "no_llm_generation" in boundary["next_contract_planning_requirements"]
    assert "no_external_calls" in boundary["next_contract_planning_requirements"]


def test_authorizations_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    for field in checker.AUTH_FALSE_FIELDS:
        assert data["authorizations"][field] is False


def test_phase_execution_state_advances_to_phase_4bg() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.AGENTS
    assert state["last_merged_pr"] == "#662"
    assert state["last_attempted_action"] == "phase_4bf_agents_schema_route_surface_confirmation"
    assert state["last_created_pr"] == "#663"
    assert state["recommended_next_pr"] == "phase_4bg_agents_fixture_native_contract_planning"
    assert state["owner_approval_required"] is False
    assert state["next_allowed_actions"] == ["phase_4bg_agents_fixture_native_contract_planning"]
    assert "phase_4bf_agents_schema_route_surface_confirmation_completed" in state["completed_steps"]


def test_agents_readiness_allows_next_contract_planning_only() -> None:
    readiness = checker.load_yaml(STATE)["agents_readiness"]
    assert readiness["metadata_planning_ready"] is True
    assert readiness["metadata_planning_completed"] is True
    assert readiness["schema_route_surface_confirmation_ready"] is True
    assert readiness["schema_route_surface_confirmed"] is True
    assert readiness["fixture_native_contract_planning_ready"] is True
    assert readiness["agent_run_execution_excluded"] is True
    assert readiness["llm_generation_excluded"] is True
    assert readiness["deepseek_adapter_excluded"] is True
    assert readiness["openclaw_mcp_excluded"] is True
    assert readiness["external_call_excluded"] is True
    assert readiness["runtime_implementation_ready"] is False
    assert readiness["production_owner_switch_ready"] is False
    assert readiness["production_write_ready"] is False
    assert readiness["fallback_removal_ready"] is False
    assert readiness["production_repository_route_enablement_ready"] is False
    assert readiness["delete_ready"] is False


def test_phase_4bg_recommendation_does_not_allow_production_actions() -> None:
    rec = checker.load_yaml(PLAN_YAML)["phase_4bg_recommendation"]
    assert rec["recommended_next_step"] == "agents_fixture_native_contract_planning"
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
