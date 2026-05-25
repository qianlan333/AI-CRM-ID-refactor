from __future__ import annotations

import json
import subprocess
from pathlib import Path

import tools.check_phase4by_agent_replay_discovery_contract_bundle as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_4by_agent_replay_discovery_contract_bundle.md"
PLAN_YAML = ROOT / "docs/development/phase_4by_agent_replay_discovery_contract_bundle.yaml"
STATE = ROOT / "docs/development/phase_execution_state.yaml"


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_bundle_metadata_and_route_boundary() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["bundle"]["type"] == "discovery_contract_bundle"
    assert data["route_family"] == checker.AGENT_REPLAY
    assert data["current_runtime_owner"] == "production_compat"
    assert data["production_behavior"] == "legacy_forward"
    assert data["legacy_fallback_retained"] is True
    assert data["fixture_allowed_in_production"] is False
    assert data["bundle"]["estimated_pr_count_reduction_percent"] >= 40


def test_bundle_combines_discovery_contract_stages() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert checker.REQUIRED_INCLUDED_STAGES <= set(data["included_stages"])
    assert checker.REQUIRED_EXCLUDED_STAGES <= set(data["excluded_stages"])


def test_route_surface_is_get_only_for_future_fixture_contract() -> None:
    route_surface = checker.load_yaml(PLAN_YAML)["route_surface_confirmation"]
    assert set(route_surface["manifest_methods"]) == {"GET", "OPTIONS", "HEAD"}
    assert set(route_surface["contract_methods_for_future_fixture_native"]) == {"GET"}
    included = {(item["method"], item["path"], item["status"]) for item in route_surface["included_routes"]}
    assert ("GET", checker.AGENT_REPLAY, "fixture_native_readonly_metadata_contract_planned") in included
    assert route_surface["delete_ready"] is False


def test_fixture_contract_is_metadata_only_and_blocks_fixture_success_in_production() -> None:
    contract = checker.load_yaml(PLAN_YAML)["fixture_native_contract"]
    assert contract["selected_subset"] == "agent_replay_readonly_metadata"
    assert contract["production_mode_returns_fixture_success"] is False
    assert checker.REQUIRED_RESPONSE_KEYS <= set(contract["required_response_keys"])
    assert checker.REQUIRED_ROW_FIELDS <= set(contract["required_row_fields"])
    assert checker.REQUIRED_DEFERRED_TABLES <= set(contract["related_tables_deferred"])
    assert all(row["side_effects_enabled"] is False for row in contract["fixture_seed_rows"])


def test_safety_authorizations_remain_disabled() -> None:
    safety = checker.load_yaml(PLAN_YAML)["safety_guards"]
    for field in checker.REQUIRED_SAFETY_TRUE:
        assert safety[field] is True
    for field in checker.REQUIRED_AUTH_FALSE:
        assert safety[field] is False


def test_state_records_agent_replay_deferral_and_next_compressed_bundle() -> None:
    state = checker.load_yaml(STATE)
    assert state["active_candidate"] == checker.TASK_GROUPS
    assert state["last_merged_pr"] == "#684"
    assert state["last_attempted_action"] == "phase_4by_agent_replay_discovery_contract_bundle"
    assert state["last_created_pr"] == "#685"
    assert state["recommended_next_pr"] == checker.NEXT_BUNDLE
    assert state["next_allowed_actions"] == [checker.NEXT_BUNDLE]
    assert checker.COMPLETED_STEP in state["completed_steps"]
    assert any(
        item["route_family"] == checker.AGENT_REPLAY
        and item["status"] == "discovery_contract_completed_replay_runtime_deferred"
        and item["paused_by_pr"] == "#685"
        and item["owner_approval_required"] is True
        for item in state["paused_candidates"]
    )


def test_agent_replay_readiness_is_paused_without_runtime_readiness() -> None:
    readiness = checker.load_yaml(STATE)["agent_replay_readiness"]
    for field in (
        "metadata_planning_ready",
        "metadata_planning_completed",
        "schema_route_surface_confirmation_ready",
        "schema_route_surface_confirmed",
        "fixture_native_contract_planning_ready",
        "fixture_native_contract_planning_completed",
        "fixture_native_runtime_deferred",
        "discovery_contract_bundle_completed",
        "paused",
        "replay_execution_excluded",
        "run_creation_excluded",
        "run_execution_excluded",
        "orchestration_execution_excluded",
        "agent_output_generation_excluded",
        "llm_generation_excluded",
        "deepseek_adapter_excluded",
        "openclaw_mcp_excluded",
        "external_call_excluded",
        "fixture_native_implementation_requires_owner_decision",
        "owner_decision_required",
    ):
        assert readiness[field] is True
    assert readiness["paused_by_pr"] == "#685"
    for field in (
        "runtime_implementation_ready",
        "production_owner_switch_ready",
        "production_write_ready",
        "fallback_removal_ready",
        "production_repository_route_enablement_ready",
        "delete_ready",
    ):
        assert readiness[field] is False


def test_next_bundle_recommendation_is_task_groups_adapter_parity() -> None:
    rec = checker.load_yaml(PLAN_YAML)["next_bundle_recommendation"]
    assert rec["recommended_next_step"] == checker.NEXT_BUNDLE
    assert rec["route_family"] == checker.TASK_GROUPS
    assert rec["bundle_type"] == "repository_adapter_parity_bundle"
    assert rec["production_write_allowed"] is False
    assert rec["production_route_switch_allowed"] is False
    assert rec["fallback_removal_allowed"] is False
    assert rec["live_external_call_allowed"] is False


def test_doc_contains_required_bundle_sections() -> None:
    text = DOC.read_text(encoding="utf-8")
    for section in (
        "Bundle Type",
        "Included Stages",
        "Excluded Stages",
        "Route Family",
        "Runtime Behavior",
        "Production Behavior",
        "Fallback Behavior",
        "Verification",
        "Risk / Rollback",
        "Next Bundle Recommendation",
    ):
        assert f"## {section}" in text


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in checker.FORBIDDEN_DOC_CLAIMS:
        assert phrase not in text


def test_no_protected_runtime_files_changed_if_git_diff_available() -> None:
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
