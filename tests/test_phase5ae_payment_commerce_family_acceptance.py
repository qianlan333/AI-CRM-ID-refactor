from __future__ import annotations

from pathlib import Path

import tools.check_phase5ae_payment_commerce_family_acceptance as checker


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ae_payment_commerce_family_acceptance.md"
PLAN_YAML = ROOT / "docs/development/phase_5ae_payment_commerce_family_acceptance.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_yaml_authorizations_false_and_stages_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    stages = {item["stage"] for item in data["completed_stages"] if item["complete"] is True}
    assert {"phase_5z_contract_fake_stub", "phase_5aa_live_adapter_behind_flag", "phase_5ab_staging_sandbox_canary_evidence", "phase_5ac_production_canary_readiness", "phase_5ad_production_canary_tooling"} <= stages


def test_capability_matrix_and_acceptance_decision() -> None:
    data = checker.load_yaml(PLAN_YAML)
    matrix = data["capability_matrix"]
    assert matrix["adapter_contract_complete"] is True
    assert matrix["production_canary_tooling_complete"] is True
    assert matrix["real_payment_capture_executed"] is False
    assert matrix["production_order_state_mutation_executed"] is False
    decision = data["acceptance_decision"]
    assert decision["status"] in decision["allowed_values"]
    assert decision["production_canary_passed"] is False
    assert decision["real_money_movement_occurred"] is False


def test_next_family_selected_and_business_continuity() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["next_family"]["selected_next_bundle"] == "phase_5af_openclaw_mcp_ai_assist_adapter_contract_fake_stub_bundle"
    assert data["next_family"]["live_external_call_allowed"] is False
    assert all(value is True for value in data["business_continuity"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["real payment capture enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
