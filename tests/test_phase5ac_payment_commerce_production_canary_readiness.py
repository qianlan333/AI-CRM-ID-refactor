from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5ac_payment_commerce_production_canary_readiness as checker
from tools import run_phase5ac_payment_commerce_production_canary_readiness as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ac_payment_commerce_production_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5ac_payment_commerce_production_canary_readiness.yaml"


def _args(**overrides):
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


def test_readiness_runner_default_blocked() -> None:
    result = runner.build_report(_args())
    assert result["ok"] is False
    assert result["production_provider_call_executed"] is False
    assert result["real_money_movement_executed"] is False


def test_invalid_staging_evidence_blocked(tmp_path: Path) -> None:
    evidence = tmp_path / "bad.json"
    evidence.write_text(json.dumps({"ok": True, "real_money_movement_executed": True}), encoding="utf-8")
    result = runner.build_report(_args(staging_evidence_json=str(evidence), confirm_no_production_provider_call=True, confirm_no_money_movement=True, confirm_no_order_mutation=True, confirm_no_webhook_cutover=True))
    assert result["result_status"] == "not_executed_invalid_staging_evidence"


def test_missing_approvals_and_confirms_block(tmp_path: Path) -> None:
    evidence = tmp_path / "good.json"
    evidence.write_text(json.dumps({"ok": True, "real_money_movement_executed": False, "production_order_state_mutation_executed": False, "production_payment_webhook_cutover_executed": False, "provider_secret_redacted": True, "side_effect_safety": {}}), encoding="utf-8")
    result = runner.build_report(_args(staging_evidence_json=str(evidence)))
    assert "not_executed_missing_production_canary_planning_approval" in result["missing_items"]
    assert "not_executed_missing_confirm_no_production_provider_call" in result["missing_items"]


def test_yaml_policy_forbids_money_movement_and_webhook_cutover() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert data["production_target_policy"]["batch_replay_allowed"] is False
    assert data["rollback_policy"]["rollback_owner_required"] is True
    assert all(value is False for value in data["side_effect_safety"].values())


def test_runner_never_imports_live_provider_or_network() -> None:
    imports, calls = checker._imports_calls(runner.Path(__file__).resolve().parents[1] / "tools/run_phase5ac_payment_commerce_production_canary_readiness.py")
    assert not (checker.FORBIDDEN_IMPORTS & imports)
    assert not (checker.FORBIDDEN_CALLS & calls)


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["real payment capture enabled", "real refund enabled", "real settlement enabled", "production payment webhook cutover enabled", "production order state mutation enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
