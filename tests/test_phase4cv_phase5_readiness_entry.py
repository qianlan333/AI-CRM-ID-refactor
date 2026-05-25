from __future__ import annotations

from pathlib import Path

import tools.check_phase4cv_phase5_readiness_entry as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/development/phase_4cv_phase5_readiness_entry.yaml"
DOC = ROOT / "docs/development/phase_4cv_phase5_readiness_entry.md"


def load_yaml(path: Path) -> dict:
    return checker.load_yaml(path)


def test_checker_passes_for_phase5_readiness_entry() -> None:
    report = checker.build_report()
    assert report["ok"], report["blockers"]
    assert report["autopilot_deliverable"] is True


def test_yaml_authorizations_all_false() -> None:
    data = load_yaml(PLAN)
    assert data["route_family"] == "phase_5_external_adapter_entry"
    assert data["bundle_type"] == "phase_5_readiness_entry_bundle"
    assert data["authorizations"]
    assert all(value is False for value in data["authorizations"].values())


def test_phase4_handoff_accepts_readiness_but_defers_owner_and_fallback() -> None:
    handoff = load_yaml(PLAN)["phase_4_handoff"]
    assert handoff["internal_write_readiness_accepted"] is True
    assert handoff["production_owner_switch_deferred"] is True
    assert handoff["fallback_removal_deferred"] is True
    assert handoff["production_compat_narrowing_deferred"] is True
    assert handoff["blocked_evidence_expected_until_owner_config_approval"] is True


def test_phase5_scope_is_contract_first_and_blocks_live_behavior() -> None:
    scope = load_yaml(PLAN)["phase_5_scope"]
    assert checker.REQUIRED_ALLOWED_SCOPE <= set(scope["allowed"])
    assert checker.REQUIRED_FORBIDDEN_SCOPE <= set(scope["forbidden"])


def test_external_adapter_family_inventory_complete_and_no_live_calls() -> None:
    data = load_yaml(PLAN)
    families = {item["family"]: item for item in data["external_adapter_families"]}
    assert checker.REQUIRED_FAMILIES <= set(families)
    for item in families.values():
        assert item["capability_owner"]
        assert item["risk_type"] in {"adapter_contract", "external_side_effect"}
        assert item["live_call_allowed"] is False
        assert item["first_safe_step"]
        assert checker._guardrail_items(item["required_guardrails"])


def test_first_phase5_candidate_is_wecom_tag_contract_only() -> None:
    candidate = load_yaml(PLAN)["first_phase5_candidate"]
    assert candidate["selected_candidate"] == "wecom_tag_adapter_contract_planning"
    assert candidate["route_family_or_capability"] == "/api/admin/wecom/tags*"
    assert candidate["capability_owner"] == "aicrm_next.customer_tags"
    assert candidate["live_external_call_allowed"] is False
    assert candidate["production_owner_switch_allowed"] is False
    assert candidate["fallback_removal_allowed"] is False
    assert checker._guardrail_items(candidate["required_guardrails"])
    assert checker._guardrail_items(candidate["expected_phase5a_scope"])


def test_phase5_readiness_decision_selects_candidate_without_live_calls() -> None:
    decision = load_yaml(PLAN)["phase_5_readiness_decision"]
    assert decision["ready_for_phase5_planning"] is True
    assert decision["live_external_calls_authorized"] is False
    assert decision["adapter_contract_first_required"] is True
    assert decision["first_candidate_selected"] is True


def test_phase6_7_deferrals_are_true() -> None:
    deferrals = load_yaml(PLAN)["phase_6_7_deferral"]
    assert deferrals
    assert all(value is True for value in deferrals.values())


def test_business_continuity_true() -> None:
    continuity = load_yaml(PLAN)["business_continuity"]
    assert continuity
    assert all(value is True for value in continuity.values())


def test_next_bundle_points_to_phase5a_wecom_tag_adapter_contract() -> None:
    next_bundle = load_yaml(PLAN)["next_bundle"]
    assert next_bundle["recommended_next_step"] == "phase_5a_wecom_tag_adapter_contract_bundle"
    assert next_bundle["route_family"] == "/api/admin/wecom/tags*"


def test_docs_do_not_claim_forbidden_live_or_production_state() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in (
        "live external calls authorized",
        "production owner switched",
        "fallback removed",
        "production write enabled",
        "production_compat changed",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ):
        assert phrase not in text
