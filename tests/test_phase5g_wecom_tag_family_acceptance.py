from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase5g_wecom_tag_family_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5g_wecom_tag_family_acceptance.md"
YAML = ROOT / "docs/development/phase_5g_wecom_tag_family_acceptance.yaml"


def _data() -> dict:
    return checker.load_yaml(YAML)


def test_checker_current_repo_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", json.dumps(report["blockers"], ensure_ascii=False, indent=2)
    assert report["autopilot_deliverable"] is True


def test_yaml_authorizations_dangerous_items_all_false() -> None:
    authorizations = _data()["authorizations"]
    assert authorizations
    assert all(value is False for value in authorizations.values())


def test_completed_stages_cover_phase_5a_to_5f() -> None:
    stages = {item["stage"]: item for item in _data()["completed_stages"]}
    assert checker.REQUIRED_STAGES <= set(stages)
    for stage in checker.REQUIRED_STAGES:
        assert stages[stage]["complete"] is True
        assert stages[stage]["live_behavior_enabled_by_default"] is False
        assert stages[stage]["owner_switch"] is False
        assert stages[stage]["fallback_removal"] is False


def test_acceptance_decision_valid_without_production_canary_pass() -> None:
    acceptance = _data()["acceptance_decision"]
    assert acceptance["status"] in checker.ALLOWED_ACCEPTANCE
    assert acceptance["production_canary_passed"] is False
    assert acceptance["wider_rollout_authorized"] is False


def test_rollout_boundary_forbids_wider_rollout_batch_and_segment() -> None:
    rollout = _data()["rollout_boundary"]
    assert rollout["wider_rollout_authorized"] is False
    assert rollout["batch_tagging_authorized"] is False
    assert rollout["automatic_segment_tagging_authorized"] is False
    assert rollout["route_owner_switch_deferred"] is True
    assert rollout["fallback_removal_deferred"] is True
    assert rollout["production_compat_change_deferred"] is True
    assert rollout["delete_ready"] is False


def test_next_family_selected() -> None:
    next_family = _data()["next_family"]
    assert next_family["selected_next_bundle"] == "phase_5h_wecom_customer_contact_adapter_contract_bundle"
    assert next_family["route_family"] == "/wecom/external-contact/callback"
    assert next_family["capability_owner"] == "aicrm_next.integration_gateway"
    assert next_family["live_external_call_allowed"] is False
    assert next_family["required_guardrails"]


def test_business_continuity_true() -> None:
    continuity = _data()["business_continuity"]
    assert continuity
    assert all(value is True for value in continuity.values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = (
        "wider rollout enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    )
    for phrase in forbidden:
        assert phrase not in text
