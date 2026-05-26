from __future__ import annotations

import argparse
from pathlib import Path

import tools.check_phase5ad_payment_commerce_production_canary_tooling as checker
from tools import run_phase5ad_payment_commerce_production_canary_cleanup as cleanup_runner
from tools import run_phase5ad_payment_commerce_production_canary_tooling as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ad_payment_commerce_production_canary_tooling.md"


def _tool_args(**overrides):
    values = {
        "phase5ac_readiness_json": None,
        "staging_evidence_json": None,
        "synthetic_target_id": "",
        "idempotency_key": None,
        "confirm_production_canary_tooling": False,
        "confirm_single_approved_target": False,
        "confirm_no_real_money_movement": False,
        "confirm_no_production_order_mutation": False,
        "confirm_no_webhook_cutover": False,
        "confirm_no_batch_target": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _cleanup_args(**overrides):
    values = {
        "canary_evidence_json": None,
        "confirm_cleanup_reviewed": False,
        "confirm_no_provider_refund": False,
        "confirm_no_production_order_cleanup": False,
        "confirm_no_batch_cleanup": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_canary_runner_default_blocked() -> None:
    result = runner.build_report(_tool_args())
    assert result["ok"] is False
    assert result["real_money_movement_executed"] is False
    assert result["production_order_state_mutation_executed"] is False


def test_batch_target_rejected() -> None:
    result = runner.build_report(_tool_args(synthetic_target_id="one,two"))
    assert "not_executed_batch_target_forbidden" in result["missing_items"]


def test_cleanup_runner_default_blocked() -> None:
    result = cleanup_runner.build_report(_cleanup_args())
    assert result["ok"] is False
    assert result["cleanup_executed"] is False
    assert result["provider_refund_executed"] is False
    assert result["production_order_cleanup_executed"] is False


def test_yaml_safety_flags() -> None:
    data = checker.load_yaml(ROOT / "docs/development/phase_5ad_payment_commerce_production_canary_tooling.yaml")
    assert data["authorizations"]["production_canary_tooling_authorized"] is True
    for key, value in data["authorizations"].items():
        if key != "production_canary_tooling_authorized":
            assert value is False
    assert data["production_canary_tooling"]["batch_target_allowed"] is False
    assert data["cleanup"]["provider_refund_allowed"] is False
    assert all(value is False for value in data["side_effect_safety"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["real payment capture enabled", "real refund enabled", "real settlement enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
