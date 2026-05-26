from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5q_oauth_identity_staging_live_canary_evidence as checker
import tools.run_phase5q_oauth_identity_production_live_readiness_review as prod_review
import tools.run_phase5q_oauth_identity_staging_live_canary_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5q_oauth_identity_staging_live_canary_evidence.md"


def _args(**overrides):
    defaults = {
        "execute_staging_canary": False,
        "confirm_live_oauth_call": False,
        "confirm_staging_only": False,
        "confirm_approved_target": False,
        "idempotency_key": None,
        "state": None,
        "code": None,
        "fake_safe_code": None,
        "callback_url": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_staging_runner_default_blocked(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED", raising=False)
    report = staging_runner.build_report(_args())
    assert report["result_status"] == "not_executed_missing_live_adapter_enabled"
    assert report["live_oauth_call_executed"] is False


def test_missing_approvals_return_blocked_statuses(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED", "1")
    report = staging_runner.build_report(_args(execute_staging_canary=True))
    assert report["result_status"] == "not_executed_missing_live_callback_approval"
    assert report["production_session_write_executed"] is False


def test_missing_state_code_idempotency_and_confirm_flags(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.CONFIG_ENV:
        monkeypatch.setenv(name, "present")
    assert staging_runner.build_report(_args(execute_staging_canary=True))["result_status"] == "not_executed_missing_code_or_safe_code"
    assert staging_runner.build_report(_args(execute_staging_canary=True, fake_safe_code="safe-code"))["result_status"] == "not_executed_missing_state"
    assert staging_runner.build_report(_args(execute_staging_canary=True, fake_safe_code="safe-code", state="state-1"))["result_status"] == "not_executed_missing_idempotency_key"
    assert staging_runner.build_report(_args(execute_staging_canary=True, fake_safe_code="safe-code", state="state-1", idempotency_key="idem"))["result_status"] == "not_executed_missing_confirm_live_oauth_call"


def test_missing_confirm_flags_return_blocked(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.CONFIG_ENV:
        monkeypatch.setenv(name, "present")
    common = dict(execute_staging_canary=True, fake_safe_code="safe-code", state="state-1", idempotency_key="idem")
    assert staging_runner.build_report(_args(**common, confirm_live_oauth_call=True))["result_status"] == "not_executed_missing_confirm_staging_only"
    assert staging_runner.build_report(_args(**common, confirm_live_oauth_call=True, confirm_staging_only=True))["result_status"] == "not_executed_missing_confirm_approved_target"


def test_production_callback_url_rejected(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.CONFIG_ENV:
        monkeypatch.setenv(name, "present")
    report = staging_runner.build_report(
        _args(
            execute_staging_canary=True,
            fake_safe_code="safe-code",
            state="state-1",
            idempotency_key="idem",
            confirm_live_oauth_call=True,
            confirm_staging_only=True,
            confirm_approved_target=True,
            callback_url="https://prod.example.com/api/h5/wechat/oauth/callback",
        )
    )
    assert report["result_status"] == "not_executed_production_callback_url_forbidden"


def test_evidence_redacts_state_code_and_token(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.CONFIG_ENV:
        monkeypatch.setenv(name, "present")
    report = staging_runner.build_report(
        _args(
            execute_staging_canary=True,
            fake_safe_code="safe-code-sensitive",
            state="state-sensitive",
            idempotency_key="idem",
            confirm_live_oauth_call=True,
            confirm_staging_only=True,
            confirm_approved_target=True,
            callback_url="https://staging.example.com/api/h5/wechat/oauth/callback",
        )
    )
    assert report["redacted_state"] != "state-sensitive"
    assert report["redacted_code"] != "safe-code-sensitive"
    assert report["token_redacted"] is True
    assert report["production_session_write_executed"] is False
    assert report["production_identity_write_executed"] is False


def test_production_readiness_review_never_calls_oauth_provider(tmp_path) -> None:
    evidence = tmp_path / "staging.json"
    evidence.write_text(json.dumps({"result_status": "staging_canary_phase5p_blocked", "redacted_state": "sta***ive", "redacted_code": "cod***ive", "side_effect_safety": {}}), encoding="utf-8")
    report = prod_review.build_report(
        staging_evidence_json=str(evidence),
        confirm_no_production_live_oauth_call=True,
        confirm_no_production_callback_cutover=True,
        confirm_no_production_session_write=True,
    )
    assert report["production_live_oauth_call_executed"] is False
    assert report["production_callback_cutover_executed"] is False
    assert report["production_session_write_executed"] is False
    assert report["production_identity_write_executed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production callback cutover enabled",
        "production session write enabled",
        "production identity write enabled",
        "production owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
