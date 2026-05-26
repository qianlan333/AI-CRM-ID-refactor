from __future__ import annotations

from pathlib import Path

import tools.check_phase6i_external_enablement_and_compat_readiness_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6i_external_enablement_and_compat_readiness_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_completed_inventory_and_authorizations() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["completed_inventory"].values())
    assert all(value is False for value in data["authorizations"].values())


def test_external_matrix_records_statuses_and_no_default_live_calls() -> None:
    matrix = checker.load_yaml(PLAN_YAML)["external_adapter_enablement_matrix"]
    statuses = {item["acceptance_status"] for item in matrix}
    assert "accepted_for_owner_reviewed_enablement_tooling" in statuses
    assert "needs_followup_before_enablement" in statuses
    assert "excluded_due_to_high_risk" in statuses
    assert all(item["fallback_retained"] is True for item in matrix)
    assert all(item["production_owner_switch"] is False for item in matrix)
    assert all(item["live_external_call_by_default"] is False for item in matrix)


def test_compat_matrix_keeps_behavior_unchanged() -> None:
    matrix = checker.load_yaml(PLAN_YAML)["production_compat_narrowing_readiness_matrix"]
    assert matrix
    assert all(item["production_compat_behavior_change"] is False for item in matrix)
    assert all(item["fallback_retained"] is True for item in matrix)


def test_acceptance_summary_and_next_bundle() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is True for value in data["acceptance_summary"].values())
    assert data["next_bundle"]["recommended_next_step"] == "phase_6j_timer_execution_readiness_bundle"
    assert data["next_bundle"]["fallback_next_step"] == "phase_6j_low_risk_external_adapter_owner_reviewed_enablement_bundle"
    assert data["next_bundle"]["implement_6j_in_this_pr"] is False
