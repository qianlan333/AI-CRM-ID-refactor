from __future__ import annotations

import argparse
from pathlib import Path

import tools.check_phase5z_payment_commerce_adapter_contract_fake_stub as checker
import tools.run_phase5z_payment_commerce_fake_stub_evidence as runner

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.md"
PLAN_YAML = ROOT / "docs/development/phase_5z_payment_commerce_adapter_contract_fake_stub.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_runner_fake_stub_evidence_has_no_money_movement() -> None:
    report = runner.build_report(argparse.Namespace(mode="fake_stub_contract"))
    assert report["ok"] is True
    assert report["real_payment_capture_executed"] is False
    assert report["real_refund_executed"] is False
    assert report["real_settlement_executed"] is False
    assert report["production_order_state_mutation_executed"] is False


def test_yaml_authorizations_and_side_effects_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert all(value is False for value in data["side_effect_safety"].values())


def test_fake_stub_forbids_provider_secret_network_and_success_claim() -> None:
    data = checker.load_yaml(PLAN_YAML)
    fake = data["fake_stub_contract"]
    assert fake["provider_secret_required"] is False
    assert fake["network_call_allowed"] is False
    assert fake["order_db_write_allowed"] is False
    assert fake["real_financial_success_claim_allowed"] is False


def test_error_mapping_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    errors = set(data["error_mapping"]["required_error_codes"])
    assert {"payment_config_missing", "payment_signature_invalid", "real_payment_not_enabled", "refund_not_enabled", "webhook_cutover_not_enabled"} <= errors


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["real payment capture enabled", "refund enabled", "settlement enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
