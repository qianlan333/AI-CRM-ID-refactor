from __future__ import annotations

from pathlib import Path

import tools.check_phase6a_owner_production_compat_readiness as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_6a_owner_production_compat_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_6a_owner_production_compat_readiness.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_phase5_handoff_completed_and_defers_owner_fallback_production_compat() -> None:
    handoff = checker.load_yaml(PLAN_YAML)["phase_5_handoff"]
    assert handoff["phase_5_completed"] is True
    assert handoff["external_adapter_tooling_complete_under_gates"] is True
    assert handoff["production_owner_switch_deferred_to_phase6"] is True
    assert handoff["fallback_removal_deferred_to_phase7"] is True
    assert handoff["production_compat_narrowing_deferred_to_phase6_or_7"] is True
    assert handoff["delete_ready"] is False


def test_phase6a_does_not_authorize_owner_switch_execution() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["production_owner_switch_authorized"] is False
    assert data["first_phase6_candidate"]["owner_switch_execution_authorized"] is False
    assert data["phase_6b_recommendation"]["owner_switch_execution_allowed"] is False


def test_phase6a_does_not_authorize_fallback_removal() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["fallback_removal_authorized"] is False
    assert data["first_phase6_candidate"]["fallback_removal_authorized"] is False
    assert data["phase_6b_recommendation"]["fallback_removal_allowed"] is False
    assert all(item["fallback_removal_ready"] is False for item in data["candidate_inventory"]["candidates"])


def test_phase6a_does_not_authorize_production_compat_behavior_change() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["production_compat_change_authorized"] is False
    assert data["first_phase6_candidate"]["production_compat_change_authorized"] is False
    assert data["phase_6b_recommendation"]["production_compat_change_allowed"] is False


def test_first_candidate_selected() -> None:
    first = checker.load_yaml(PLAN_YAML)["first_phase6_candidate"]
    assert first["selected_route_family"] == "/api/admin/automation-conversion/task-groups*"
    assert first["capability_owner"] == "aicrm_next.automation_engine"
    assert first["risk_level"] == "low"
    assert first["required_guardrails"]
    assert first["required_evidence"]
    assert first["rollback_requirement"]


def test_business_continuity_true() -> None:
    continuity = checker.load_yaml(PLAN_YAML)["business_continuity"]
    assert all(value is True for value in continuity.values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "owner switch executed",
        "fallback removed",
        "production_compat changed",
        "timer enabled",
        "execution enabled",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
