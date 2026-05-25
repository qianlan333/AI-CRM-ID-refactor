from __future__ import annotations

import tools.check_phase5o_oauth_identity_fake_stub_adapter as checker
from aicrm_next.integration_gateway.oauth_identity_adapter import DETERMINISTIC_OAUTH_EVENTS, build_fake_stub_oauth_identity_adapter
from tools import run_phase5o_oauth_identity_fake_stub_production_dry_run as prod_runner
from tools import run_phase5o_oauth_identity_fake_stub_staging_smoke as staging_runner


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_deterministic_events_and_authorize_contract() -> None:
    adapter = build_fake_stub_oauth_identity_adapter()
    events = adapter.deterministic_oauth_events()["events"]
    assert events == adapter.deterministic_oauth_events()["events"]
    event = DETERMINISTIC_OAUTH_EVENTS[0]
    result = adapter.build_oauth_authorize_url_contract(slug=event["slug"], state=event["state"], redirect_uri=event["redirect_uri"])
    assert result["ok"] is True
    assert result["live_oauth_call_executed"] is False


def test_parse_normalize_and_validation() -> None:
    adapter = build_fake_stub_oauth_identity_adapter()
    event = DETERMINISTIC_OAUTH_EVENTS[0]
    parsed = adapter.parse_oauth_callback_contract(code=event["code"], state=event["state"], openid=event["openid"], unionid=event["unionid"])
    assert parsed["ok"] is True
    assert "openid" not in parsed["event"]
    assert adapter.parse_oauth_callback_contract(code="", state=event["state"], openid=event["openid"])["error_code"] == "oauth_code_missing"
    assert adapter.normalize_oauth_identity_event({"state": event["state"]})["error_code"] == "openid_missing"


def test_idempotency_replay_and_conflict() -> None:
    adapter = build_fake_stub_oauth_identity_adapter()
    event = DETERMINISTIC_OAUTH_EVENTS[0]
    assert adapter.dry_run_record_oauth_identity(event=event, operator="test", idempotency_key="")["error_code"] == "idempotency_key_required"
    first = adapter.dry_run_record_oauth_identity(event=event, operator="test", idempotency_key="key-1")
    replay = adapter.dry_run_record_oauth_identity(event=event, operator="test", idempotency_key="key-1")
    assert first["ok"] is True
    assert replay["result_status"] == "replay"
    conflict = adapter.dry_run_record_oauth_identity(event=DETERMINISTIC_OAUTH_EVENTS[1], operator="test", idempotency_key="key-1")
    assert conflict["result_status"] == "conflict"


def test_side_effect_safety_all_false() -> None:
    adapter = build_fake_stub_oauth_identity_adapter()
    result = adapter.live_oauth_callback_attempt()
    assert result["error_code"] == "live_oauth_callback_not_enabled"
    assert result["live_oauth_call_executed"] is False
    assert result["production_session_write_executed"] is False
    assert result["production_identity_write_executed"] is False


def test_readiness_runners_default_blocked() -> None:
    staging = staging_runner.build_report()
    prod = prod_runner.build_report(dry_run=False, confirm_no_live_oauth_callback=False)
    assert staging["ok"] is False
    assert prod["ok"] is False
    assert staging["live_oauth_call_executed"] is False
    assert prod["production_session_write_executed"] is False
