from __future__ import annotations

import argparse
from pathlib import Path

import tools.check_phase5j_wecom_customer_contact_live_callback_adapter_behind_flag as checker
import tools.run_phase5j_wecom_customer_contact_live_callback_production_dry_run_gate as prod_runner
import tools.run_phase5j_wecom_customer_contact_live_callback_staging_evidence as staging_runner
from aicrm_next.integration_gateway.wecom_contact_callback_adapter import DETERMINISTIC_EVENTS, FakeStubWeComContactCallbackAdapter
from aicrm_next.integration_gateway.wecom_contact_callback_live_adapter import (
    FLAG_CONFIG_REVIEWED,
    FLAG_LIVE_APPROVED,
    FLAG_LIVE_ENABLED,
    LiveWeComContactCallbackAdapter,
)


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5j_wecom_customer_contact_live_callback_adapter_behind_flag.md"
RUNTIME = ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_live_adapter.py"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_live_adapter_default_blocked(monkeypatch) -> None:
    for name in [FLAG_LIVE_ENABLED, FLAG_LIVE_APPROVED, FLAG_CONFIG_REVIEWED]:
        monkeypatch.delenv(name, raising=False)
    adapter = LiveWeComContactCallbackAdapter()
    result = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="key-1")
    assert result["ok"] is False
    assert result["error_code"] == "live_adapter_not_enabled"
    assert result["live_callback_processed"] is False


def test_missing_approval_returns_live_callback_not_approved(monkeypatch) -> None:
    monkeypatch.setenv(FLAG_LIVE_ENABLED, "1")
    monkeypatch.delenv(FLAG_LIVE_APPROVED, raising=False)
    adapter = LiveWeComContactCallbackAdapter()
    result = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="key-2")
    assert result["ok"] is False
    assert result["error_code"] == "live_callback_not_approved"


def test_missing_config_returns_callback_config_missing(monkeypatch) -> None:
    monkeypatch.setenv(FLAG_LIVE_ENABLED, "1")
    monkeypatch.setenv(FLAG_LIVE_APPROVED, "1")
    monkeypatch.delenv(FLAG_CONFIG_REVIEWED, raising=False)
    adapter = LiveWeComContactCallbackAdapter(confirm_live_wecom_callback=True)
    result = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="key-3")
    assert result["ok"] is False
    assert result["error_code"] == "callback_config_missing"


def test_missing_idempotency_returns_required() -> None:
    adapter = LiveWeComContactCallbackAdapter()
    result = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="")
    assert result["ok"] is False
    assert result["error_code"] == "idempotency_key_required"


def test_blocked_idempotency_replay_and_conflict(monkeypatch) -> None:
    monkeypatch.setenv(FLAG_LIVE_ENABLED, "1")
    adapter = LiveWeComContactCallbackAdapter()
    first = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="same")
    replay = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="same")
    conflict = adapter.record_contact_event_live(event=DETERMINISTIC_EVENTS[1], operator="tester", idempotency_key="same")
    assert first["ok"] is False
    assert replay["result_status"] == "replay"
    assert replay["idempotency_replay"] is True
    assert conflict["result_status"] == "conflict"
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_fake_stub_behavior_from_phase5i_still_works() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    result = adapter.dry_run_identity_mapping(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="fake-still-works")
    assert result["ok"] is True
    assert result["production_write_executed"] is False


def test_staging_evidence_runner_default_blocked(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5J_WECOM_CONTACT_STAGING_LIVE_APPROVED", raising=False)
    args = argparse.Namespace(dry_run_live_gate=False, execute_live_staging=False, confirm_live_wecom_callback=False)
    report = staging_runner.build_report(args)
    assert report["ok"] is True
    assert report["result_status"] == "blocked_not_executed"
    assert report["live_callback_processed"] is False


def test_production_dry_run_gate_never_processes_live_callback(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5J_WECOM_CONTACT_PRODUCTION_DRY_RUN_APPROVED", raising=False)
    report = prod_runner.build_report(dry_run=True, confirm_no_live_callback=True)
    assert report["ok"] is False
    assert report["live_callback_processed"] is False
    assert report["production_contact_write_executed"] is False
    assert report["production_identity_mapping_write_executed"] is False


def test_side_effect_safety_forbids_outbound_oauth_payment_media_openclaw_mcp() -> None:
    adapter = LiveWeComContactCallbackAdapter()
    result = adapter.record_identity_mapping_live(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="safety")
    safety = result["side_effect_safety"]
    for key in [
        "outbound_send_executed",
        "oauth_callback_executed",
        "payment_executed",
        "media_upload_executed",
        "openclaw_mcp_executed",
        "timer_execution_executed",
        "automation_execution_executed",
        "production_compat_changed",
        "fallback_removed",
    ]:
        assert safety[key] is False


def test_runtime_does_not_import_legacy_client_or_send() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    forbidden = ["wecom_ability_service", "requests", "httpx", "aiohttp", "send_message", "externalcontact/mark_tag"]
    assert not any(token in text for token in forbidden)


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production callback cutover enabled",
        "production contact write enabled",
        "production identity mapping write enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
