from __future__ import annotations

from pathlib import Path

import tools.check_phase5m_wecom_customer_contact_callback_family_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5m_wecom_customer_contact_callback_family_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_dangerous_items_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_completed_stages_cover_5h_to_5l() -> None:
    data = checker.load_yaml(PLAN_YAML)
    stages = {item["stage"] for item in data["completed_stages"] if item["complete"] is True}
    assert {
        "phase_5h_contract",
        "phase_5i_fake_stub_runtime",
        "phase_5j_live_callback_behind_flag",
        "phase_5k_staging_live_callback_canary_gate",
        "phase_5l_production_callback_canary_readiness",
    } <= stages


def test_acceptance_decision_valid_and_canary_not_passed() -> None:
    data = checker.load_yaml(PLAN_YAML)
    decision = data["acceptance_decision"]
    assert decision["status"] in decision["allowed_values"]
    assert decision["production_callback_canary_passed"] is False
    assert decision["wider_rollout_authorized"] is False


def test_rollout_boundary_and_business_continuity() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["rollout_boundary"]["wider_rollout_authorized"] is False
    assert data["rollout_boundary"]["route_owner_switch_deferred"] is True
    assert data["rollout_boundary"]["fallback_removal_deferred"] is True
    assert data["business_continuity"]["production_behavior_unchanged"] is True


def test_next_family_selected() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next_family"]["selected_next_bundle"] == "phase_5n_oauth_identity_adapter_contract_bundle"
    assert data["next_family"]["route_family"] == "/api/h5/wechat/oauth*"


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "wider rollout enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
        "production callback canary passed",
    ]
    assert not any(claim in text for claim in forbidden)
