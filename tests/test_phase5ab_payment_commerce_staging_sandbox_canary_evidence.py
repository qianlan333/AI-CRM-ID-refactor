from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5ab_payment_commerce_staging_sandbox_canary_evidence as checker
from tools import run_phase5ab_payment_commerce_production_readiness_review as prod_review
from tools import run_phase5ab_payment_commerce_staging_sandbox_canary_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5ab_payment_commerce_staging_sandbox_canary_evidence.yaml"


def _staging_args(**overrides):
    values = {
        "execute_staging_sandbox_canary": False,
        "synthetic_order_id": "",
        "amount_cents": 100,
        "currency": "CNY",
        "idempotency_key": None,
        "confirm_no_real_money_movement": False,
        "confirm_sandbox_only": False,
        "confirm_no_production_order_mutation": False,
        "confirm_no_webhook_cutover": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _review_args(**overrides):
    values = {
        "staging_evidence_json": None,
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


def test_staging_runner_default_blocked() -> None:
    result = staging_runner.build_report(_staging_args())
    assert result["ok"] is False
    assert result["result_status"] == "not_executed_missing_live_adapter_enabled"
    assert result["real_money_movement_executed"] is False


def test_missing_target_and_confirm_flags_block(monkeypatch) -> None:
    for env in staging_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_PROVIDER_NAME", "sandbox")
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_PROVIDER_SECRET", "redacted")
    result = staging_runner.build_report(_staging_args(execute_staging_sandbox_canary=True))
    assert result["result_status"] == "not_executed_missing_synthetic_order_id"
    result = staging_runner.build_report(_staging_args(execute_staging_sandbox_canary=True, synthetic_order_id="synthetic-001", idempotency_key="idem"))
    assert result["result_status"] == "not_executed_missing_confirm_no_real_money_movement"


def test_batch_replay_rejected(monkeypatch) -> None:
    for env in staging_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_PROVIDER_NAME", "sandbox")
    monkeypatch.setenv("AICRM_PAYMENT_COMMERCE_PROVIDER_SECRET", "redacted")
    result = staging_runner.build_report(_staging_args(execute_staging_sandbox_canary=True, synthetic_order_id="one,two", idempotency_key="idem"))
    assert result["result_status"] == "not_executed_batch_replay_forbidden"


def test_evidence_redacts_order_and_secret() -> None:
    result = staging_runner.build_report(_staging_args(synthetic_order_id="synthetic-001"))
    assert result["synthetic_order_id_redacted"] == "sy***01"
    assert result["provider_secret_redacted"] is True


def test_production_readiness_review_missing_evidence_blocked() -> None:
    result = prod_review.build_report(_review_args(confirm_no_production_provider_call=True, confirm_no_money_movement=True, confirm_no_order_mutation=True, confirm_no_webhook_cutover=True))
    assert result["ok"] is False
    assert result["production_provider_call_executed"] is False
    assert result["real_money_movement_executed"] is False


def test_production_readiness_review_accepts_safe_evidence(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "ok": True,
                "result_status": "staging_sandbox_payment_gate_ready",
                "real_money_movement_executed": False,
                "production_order_state_mutation_executed": False,
                "production_payment_webhook_cutover_executed": False,
                "provider_secret_redacted": True,
                "side_effect_safety": {},
            }
        ),
        encoding="utf-8",
    )
    result = prod_review.build_report(_review_args(staging_evidence_json=str(evidence), confirm_no_production_provider_call=True, confirm_no_money_movement=True, confirm_no_order_mutation=True, confirm_no_webhook_cutover=True))
    assert result["ok"] is True
    assert result["production_provider_call_executed"] is False


def test_yaml_forbids_side_effects() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())
    assert data["target_safety"]["batch_replay_allowed"] is False
    assert data["production_readiness_review"]["production_provider_call_executed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["real payment capture enabled", "real refund enabled", "real settlement enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
