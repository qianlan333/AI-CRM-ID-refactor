from __future__ import annotations

from pathlib import Path

import tools.check_phase4cu_internal_write_acceptance_review as checker


ROOT = Path(__file__).resolve().parents[1]
PLAN = ROOT / "docs/development/phase_4cu_internal_write_acceptance_review.yaml"
DOC = ROOT / "docs/development/phase_4cu_internal_write_acceptance_review.md"


def load_yaml(path: Path) -> dict:
    return checker.load_yaml(path)


def test_checker_passes_for_phase4cu_acceptance_review() -> None:
    report = checker.build_report()
    assert report["ok"], report["blockers"]
    assert report["autopilot_deliverable"] is True


def test_yaml_authorizations_all_false() -> None:
    data = load_yaml(PLAN)
    assert data["route_family"] == "phase_4_internal_write_aggregate"
    assert data["bundle_type"] == "phase_4_internal_write_acceptance_review_bundle"
    assert data["authorizations"]
    assert all(value is False for value in data["authorizations"].values())


def test_route_family_inventory_complete() -> None:
    data = load_yaml(PLAN)
    routes = {item["route_family"] for item in data["route_families"]}
    assert checker.REQUIRED_ROUTE_FAMILIES <= routes
    for item in data["route_families"]:
        assert item["latest_stage"]
        assert item["phase_4_acceptance_status"] in checker.ALLOWED_ACCEPTANCE_STATUS
        assert item["blockers"]
        assert all(blocker["item"] for blocker in item["blockers"])


def test_acceptance_matrix_fields_complete() -> None:
    data = load_yaml(PLAN)
    matrix = data["acceptance_matrix"]
    assert set(matrix["required_fields"]) == checker.REQUIRED_MATRIX_FIELDS
    routes = {row["route_family"] for row in matrix["rows"]}
    assert checker.REQUIRED_ROUTE_FAMILIES <= routes
    for row in matrix["rows"]:
        assert checker.REQUIRED_MATRIX_FIELDS <= set(row)
        assert row["production_owner_switched"] is False
        assert row["fallback_removed"] is False
        assert row["production_write_enabled"] is False
        assert row["phase_4_acceptance_status"] in checker.ALLOWED_ACCEPTANCE_STATUS


def test_phase4_decision_defers_owner_switch_fallback_and_production_compat() -> None:
    decision = load_yaml(PLAN)["phase_4_decision"]
    assert isinstance(decision["readiness_accepted"], bool)
    assert decision["owner_switch_deferred"] is True
    assert decision["fallback_removal_deferred"] is True
    assert decision["production_compat_narrowing_deferred"] is True


def test_phase5_readiness_does_not_authorize_live_external_calls() -> None:
    phase5 = load_yaml(PLAN)["phase_5_readiness"]
    assert isinstance(phase5["ready_for_phase5_planning"], bool)
    assert phase5["external_live_calls_authorized"] is False
    assert phase5["adapter_contract_first_required"] is True


def test_phase6_7_deferrals_are_true() -> None:
    deferrals = load_yaml(PLAN)["phase_6_7_deferral"]
    assert deferrals
    assert all(value is True for value in deferrals.values())


def test_business_continuity_true() -> None:
    continuity = load_yaml(PLAN)["business_continuity"]
    assert continuity
    assert all(value is True for value in continuity.values())


def test_docs_do_not_claim_forbidden_production_state() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    for phrase in (
        "production owner switched",
        "fallback removed",
        "production write enabled",
        "external calls enabled",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ):
        assert phrase not in text
