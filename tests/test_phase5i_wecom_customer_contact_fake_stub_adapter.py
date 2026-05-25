from __future__ import annotations

import json
from pathlib import Path

import tools.check_phase5i_wecom_customer_contact_fake_stub_adapter as checker
import tools.run_phase5i_wecom_customer_contact_fake_stub_production_dry_run as prod_runner
import tools.run_phase5i_wecom_customer_contact_fake_stub_staging_smoke as staging_runner
from aicrm_next.integration_gateway.wecom_contact_callback_adapter import (
    DETERMINISTIC_EVENTS,
    FakeStubWeComContactCallbackAdapter,
)


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.md"
PLAN_YAML = ROOT / "docs/development/phase_5i_wecom_customer_contact_fake_stub_adapter.yaml"
RUNTIME = ROOT / "aicrm_next/integration_gateway/wecom_contact_callback_adapter.py"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_list_deterministic_fake_events() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    report = adapter.deterministic_events()
    assert report["ok"] is True
    assert report["events"] == adapter.deterministic_events()["events"]
    assert len(report["events"]) >= 2
    assert "external_userid" not in report["events"][0]
    assert report["live_callback_processed"] is False


def test_parse_and_normalize_external_contact_event() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    parsed = adapter.parse_external_contact_event(
        {"Event": "external_contact", "ChangeType": "add_external_contact", "ExternalUserID": "external_userid_abc123", "UserID": "follow_user_001"}
    )
    assert parsed["ok"] is True
    normalized = adapter.normalize_external_contact_event(
        {"Event": "external_contact", "ChangeType": "add_external_contact", "ExternalUserID": "external_userid_abc123", "UserID": "follow_user_001"}
    )
    assert normalized["ok"] is True
    assert normalized["event"]["external_userid_redacted"]
    assert "external_userid" not in normalized["event"]


def test_normalize_rejects_missing_external_userid() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    result = adapter.normalize_external_contact_event({"event_type": "external_contact", "change_type": "add_external_contact", "follow_user_userid": "u1"})
    assert result["ok"] is False
    assert result["error_code"] == "external_userid_missing"


def test_normalize_rejects_missing_follow_user_userid() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    result = adapter.normalize_external_contact_event({"event_type": "external_contact", "change_type": "add_external_contact", "external_userid": "ex1"})
    assert result["ok"] is False
    assert result["error_code"] == "follow_user_userid_missing"


def test_dry_run_record_contact_event_requires_idempotency_key() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    result = adapter.dry_run_record_contact_event(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="")
    assert result["ok"] is False
    assert result["error_code"] == "idempotency_key_required"


def test_dry_run_record_contact_event_replay_and_conflict() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    first = adapter.dry_run_record_contact_event(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="same-key")
    replay = adapter.dry_run_record_contact_event(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="same-key")
    conflict = adapter.dry_run_record_contact_event(event=DETERMINISTIC_EVENTS[1], operator="tester", idempotency_key="same-key")
    duplicate = adapter.dry_run_record_contact_event(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="new-key")
    assert first["ok"] is True
    assert replay["result_status"] == "replay"
    assert replay["idempotency_replay"] is True
    assert conflict["ok"] is False
    assert conflict["result_status"] == "conflict"
    assert duplicate["result_status"] == "duplicate_event_replay"
    assert duplicate["event_key_replay"] is True


def test_dry_run_identity_mapping_replay_and_conflict() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    first = adapter.dry_run_identity_mapping(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="identity-key")
    replay = adapter.dry_run_identity_mapping(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="identity-key")
    conflict = adapter.dry_run_identity_mapping(event=DETERMINISTIC_EVENTS[1], operator="tester", idempotency_key="identity-key")
    assert first["ok"] is True
    assert replay["result_status"] == "replay"
    assert conflict["ok"] is False
    assert conflict["result_status"] == "conflict"


def test_side_effect_safety_all_false() -> None:
    adapter = FakeStubWeComContactCallbackAdapter()
    result = adapter.dry_run_record_contact_event(event=DETERMINISTIC_EVENTS[0], operator="tester", idempotency_key="safety-key")
    fields = [
        "live_callback_processed",
        "production_write_executed",
        "production_contact_write_executed",
        "production_identity_mapping_write_executed",
        "production_tag_write_executed",
        "outbound_send_executed",
        "customer_sync_executed",
        "token_used",
        "aes_key_used",
        "decrypt_executed",
        "network_call_executed",
        "db_write_executed",
        "production_behavior_changed",
        "production_compat_changed",
        "fallback_removed",
        "production_success_claimed",
    ]
    assert all(result[field] is False for field in fields)
    assert all(value is False for value in result["side_effect_safety"].values())


def test_staging_runner_default_blocked(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5I_WECOM_CONTACT_STAGING_SMOKE_APPROVED", raising=False)
    report = staging_runner.build_report()
    assert report["ok"] is False
    assert report["result_status"] == "blocked_missing_staging_smoke_approval"
    assert report["live_callback_processed"] is False


def test_production_dry_run_runner_requires_approval_config_and_args(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5I_WECOM_CONTACT_PRODUCTION_DRY_RUN_APPROVED", raising=False)
    monkeypatch.delenv("AICRM_PHASE5I_WECOM_CONTACT_PRODUCTION_CONFIG_REVIEWED", raising=False)
    report = prod_runner.build_report(dry_run=False, confirm_no_live_callback=False)
    assert report["ok"] is False
    assert set(report["missing_items"]) == {
        "production_dry_run_approval",
        "production_config_review",
        "dry_run_arg",
        "confirm_no_live_callback",
    }
    assert report["production_contact_write_executed"] is False


def test_yaml_authorizations_and_error_mapping_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert checker.REQUIRED_ERROR_CODES <= set(data["error_mapping"]["required_error_codes"])
    assert all(value is False for value in data["side_effect_safety"].values())


def test_runtime_static_text_does_not_import_or_execute_live_callback() -> None:
    text = RUNTIME.read_text(encoding="utf-8")
    forbidden = ["requests", "httpx", "aiohttp", "wecom_ability_service", "externalcontact/mark_tag", "send_message", "os.getenv"]
    assert not any(token in text for token in forbidden)
    adapter = FakeStubWeComContactCallbackAdapter()
    attempt = adapter.live_callback_attempt()
    assert attempt["ok"] is False
    assert attempt["error_code"] == "live_callback_not_enabled"
    assert attempt["live_callback_processed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "live callback cutover enabled",
        "production contact write enabled",
        "production identity mapping write enabled",
        "production success",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)


def test_runner_cli_writes_blocked_json(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AICRM_PHASE5I_WECOM_CONTACT_STAGING_SMOKE_APPROVED", raising=False)
    output = tmp_path / "staging.json"
    assert staging_runner.main(["--output-json", str(output)]) == 0
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report["ok"] is False
    assert report["live_callback_processed"] is False
