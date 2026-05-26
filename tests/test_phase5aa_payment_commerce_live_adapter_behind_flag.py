from __future__ import annotations

import argparse
from pathlib import Path

import tools.check_phase5aa_payment_commerce_live_adapter_behind_flag as checker
from aicrm_next.integration_gateway.payment_commerce_live_adapter import build_payment_commerce_live_adapter
from tools import run_phase5aa_payment_commerce_live_production_dry_run_gate as prod_runner
from tools import run_phase5aa_payment_commerce_live_staging_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5aa_payment_commerce_live_adapter_behind_flag.yaml"


def _staging_args(**overrides):
    values = {
        "dry_run_live_gate": False,
        "execute_sandbox_staging": False,
        "confirm_no_money_movement": False,
        "confirm_sandbox_only": False,
        "confirm_no_order_mutation": False,
        "confirm_no_webhook_cutover": False,
        "idempotency_key": None,
        "order_id": "",
        "amount_cents": 100,
        "currency": "CNY",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _prod_args(**overrides):
    values = {
        "dry_run": False,
        "confirm_no_production_provider_call": False,
        "confirm_no_money_movement": False,
        "confirm_no_order_mutation": False,
        "confirm_no_webhook_cutover": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_live_adapter_default_blocked() -> None:
    adapter = build_payment_commerce_live_adapter()
    result = adapter.create_payment_intent_live(order_id="order-001", amount_cents=100, currency="CNY", operator="test", idempotency_key="idem")
    assert result["ok"] is False
    assert result["error_code"] == "live_adapter_not_enabled"
    assert result["real_payment_capture_executed"] is False
    assert result["production_order_state_mutation_executed"] is False


def test_missing_approval_and_config_return_blocked(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_LIVE_ADAPTER_ENABLED", "1")
    adapter = build_payment_commerce_live_adapter(confirm_no_money_movement=True)
    result = adapter.create_payment_intent_live(order_id="order-001", amount_cents=100, currency="CNY", operator="test", idempotency_key="idem-approval")
    assert result["error_code"] == "live_payment_call_not_approved"
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_LIVE_CALL_APPROVED", "1")
    result = adapter.create_payment_intent_live(order_id="order-001", amount_cents=100, currency="CNY", operator="test", idempotency_key="idem-config")
    assert result["error_code"] == "payment_config_missing"


def test_missing_idempotency_returns_error() -> None:
    adapter = build_payment_commerce_live_adapter()
    result = adapter.create_payment_intent_live(order_id="order-001", amount_cents=100, currency="CNY", operator="test", idempotency_key="")
    assert result["error_code"] == "idempotency_key_required"


def test_idempotency_replay_and_conflict_work() -> None:
    adapter = build_payment_commerce_live_adapter()
    first = adapter.create_payment_intent_live(order_id="order-001", amount_cents=100, currency="CNY", operator="test", idempotency_key="idem-replay")
    replay = adapter.create_payment_intent_live(order_id="order-001", amount_cents=100, currency="CNY", operator="test", idempotency_key="idem-replay")
    conflict = adapter.create_payment_intent_live(order_id="order-002", amount_cents=100, currency="CNY", operator="test", idempotency_key="idem-replay")
    assert first["result_status"] == "blocked"
    assert replay["result_status"] == "replay"
    assert replay["idempotency_replay"] is True
    assert conflict["result_status"] == "conflict"
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_refund_and_webhook_paths_remain_blocked() -> None:
    adapter = build_payment_commerce_live_adapter()
    refund = adapter.request_refund_live(payment_reference="pay-001", amount_cents=100, operator="test", idempotency_key="idem-refund")
    webhook = adapter.verify_payment_webhook_live(payload_hash="hash", signature="sig", operator="test", idempotency_key="idem-webhook")
    assert refund["error_code"] == "refund_not_enabled"
    assert webhook["error_code"] == "webhook_cutover_not_enabled"
    assert refund["real_refund_executed"] is False
    assert webhook["production_payment_webhook_cutover_executed"] is False


def test_staging_runner_default_blocked() -> None:
    result = staging_runner.build_report(_staging_args())
    assert result["ok"] is False
    assert result["provider_call_executed"] is False
    assert result["real_money_movement_executed"] is False


def test_staging_runner_requires_confirm_flags(monkeypatch) -> None:
    for env in staging_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_PROVIDER_NAME", "fake-sandbox")
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_PROVIDER_SECRET", "redacted-test-secret")
    result = staging_runner.build_report(_staging_args(execute_sandbox_staging=True, confirm_no_money_movement=True, idempotency_key="idem-stage", order_id="synthetic-001"))
    assert result["result_status"] == "not_executed_missing_confirm_sandbox_only"
    result = staging_runner.build_report(_staging_args(execute_sandbox_staging=True, confirm_no_money_movement=True, confirm_sandbox_only=True, idempotency_key="idem-stage", order_id="synthetic-001"))
    assert result["result_status"] == "not_executed_missing_confirm_no_order_mutation"


def test_production_dry_run_gate_never_calls_provider() -> None:
    result = prod_runner.build_report(_prod_args(dry_run=True, confirm_no_production_provider_call=True, confirm_no_money_movement=True, confirm_no_order_mutation=True, confirm_no_webhook_cutover=True))
    assert result["ok"] is True
    assert result["production_provider_call_executed"] is False
    assert result["real_money_movement_executed"] is False
    assert result["production_order_state_mutation_executed"] is False


def test_side_effect_safety_forbids_financial_actions() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())
    assert data["authorizations"]["real_payment_capture_authorized"] is False
    assert data["authorizations"]["real_refund_authorized"] is False
    assert data["authorizations"]["real_settlement_authorized"] is False
    assert data["authorizations"]["production_payment_webhook_cutover_authorized"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "real payment capture enabled",
        "real refund enabled",
        "real settlement enabled",
        "production payment webhook cutover enabled",
        "production order state mutation enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
