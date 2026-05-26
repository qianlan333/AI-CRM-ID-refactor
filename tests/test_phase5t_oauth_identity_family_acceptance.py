from __future__ import annotations

from pathlib import Path

import tools.check_phase5t_oauth_identity_family_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5t_oauth_identity_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5t_oauth_identity_family_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_dangerous_items_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_completed_stages_cover_5n_to_5s() -> None:
    data = checker.load_yaml(PLAN_YAML)
    stages = {item["stage"] for item in data["completed_stages"] if item["complete"] is True}
    assert {
        "phase_5n_contract",
        "phase_5o_fake_stub_runtime",
        "phase_5p_live_adapter_behind_flag",
        "phase_5q_staging_live_canary_gate",
        "phase_5r_production_canary_readiness",
        "phase_5s_production_live_canary_tooling",
    } <= stages


def test_acceptance_decision_valid_and_canary_not_passed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    decision = data["acceptance_decision"]
    assert decision["status"] in decision["allowed_values"]
    assert decision["status"] == "accepted_with_blocked_evidence_only"
    assert decision["production_canary_passed"] is False
    assert decision["wider_rollout_authorized"] is False


def test_capability_matrix_keeps_production_side_effects_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    matrix = data["capability_matrix"]
    assert matrix["production_callback_cutover_enabled"] is False
    assert matrix["production_session_write_enabled"] is False
    assert matrix["production_identity_write_enabled"] is False
    assert matrix["token_persistence_enabled"] is False
    assert matrix["route_owner_switched"] is False
    assert matrix["fallback_removed"] is False
    assert matrix["production_compat_changed"] is False


def test_rollout_boundary_and_business_continuity() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["rollout_boundary"]["wider_rollout_authorized"] is False
    assert data["rollout_boundary"]["route_owner_switch_deferred"] is True
    assert data["rollout_boundary"]["fallback_removal_deferred"] is True
    assert data["business_continuity"]["production_behavior_unchanged"] is True


def test_next_family_selected() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next_family"]["selected_next_bundle"] == "phase_5u_media_upload_adapter_contract_fake_stub_bundle"
    assert data["next_family"]["route_family"] == "/api/admin/image-library*"
    assert data["next_family"]["capability_owner"] == "aicrm_next.media_library"
    assert data["next_family"]["live_external_call_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "wider rollout enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
        "production canary passed",
        "production callback cutover enabled",
        "production session write enabled",
        "production identity write enabled",
        "token persistence enabled",
    ]
    assert not any(claim in text for claim in forbidden)
