from __future__ import annotations

import argparse

import tools.check_phase5p_oauth_identity_live_adapter_behind_flag as checker
from aicrm_next.integration_gateway.oauth_identity_live_adapter import build_live_oauth_identity_adapter
from tools import run_phase5p_oauth_identity_live_production_dry_run_gate as prod_runner
from tools import run_phase5p_oauth_identity_live_staging_evidence as staging_runner


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_live_adapter_default_blocked() -> None:
    adapter = build_live_oauth_identity_adapter()
    result = adapter.exchange_code_live(code="code", state="state", operator="test", idempotency_key="key")
    assert result["ok"] is False
    assert result["error_code"] == "live_adapter_not_enabled"
    assert result["live_oauth_call_executed"] is False


def test_missing_idempotency_returns_error() -> None:
    adapter = build_live_oauth_identity_adapter()
    result = adapter.exchange_code_live(code="code", state="state", operator="test", idempotency_key="")
    assert result["error_code"] == "idempotency_key_required"


def test_staging_runner_default_blocked() -> None:
    args = argparse.Namespace(dry_run_live_gate=False, execute_live_staging=False, confirm_live_oauth_callback=False)
    result = staging_runner.build_report(args)
    assert result["ok"] is False
    assert result["live_oauth_call_executed"] is False


def test_production_dry_run_never_calls_live() -> None:
    result = prod_runner.build_report(dry_run=True, confirm_no_live_oauth_callback=True)
    assert result["live_oauth_call_executed"] is False
    assert result["production_session_write_executed"] is False
    assert result["production_identity_write_executed"] is False
