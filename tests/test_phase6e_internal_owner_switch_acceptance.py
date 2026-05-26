from __future__ import annotations

from pathlib import Path

import tools.check_phase6e_internal_owner_switch_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN_YAML = ROOT / "docs/development/phase_6e_internal_owner_switch_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_completed_inventory_records_phase6b_6c_6d() -> None:
    inventory = checker.load_yaml(PLAN_YAML)["completed_inventory"]
    assert inventory["phase_6b_completed"] is True
    assert inventory["phase_6c_completed"] is True
    assert inventory["phase_6d_completed"] is True


def test_matrix_includes_required_acceptance_statuses() -> None:
    matrix = checker.load_yaml(PLAN_YAML)["route_family_matrix"]
    statuses = {item["acceptance_status"] for item in matrix}
    assert checker.ACCEPTANCE_STATUSES <= statuses
    assert all(item["production_compat_unchanged"] is True for item in matrix)
    assert all(item["fallback_retained"] is True for item in matrix)


def test_no_default_owner_switch_or_side_effect_authorized() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert data["acceptance_summary"]["no_default_owner_switch"] is True
    assert data["acceptance_summary"]["fallback_retained"] is True
    assert data["acceptance_summary"]["production_compat_unchanged"] is True
    assert data["acceptance_summary"]["no_timer_execution"] is True
    assert data["acceptance_summary"]["no_automation_execution"] is True
    assert data["acceptance_summary"]["no_outbound_send"] is True
    assert data["acceptance_summary"]["no_delete_ready"] is True


def test_next_bundle_recommendation() -> None:
    next_bundle = checker.load_yaml(PLAN_YAML)["next_bundle"]
    assert next_bundle["recommended_next_step"] == "phase_6f_external_adapter_enablement_readiness_bundle"
    assert next_bundle["fallback_next_step"] == "phase_6f_internal_owner_switch_followup_bundle"
    assert next_bundle["owner_switch_execution_allowed_default"] is False
    assert next_bundle["production_compat_change_allowed"] is False
    assert next_bundle["fallback_removal_allowed"] is False
