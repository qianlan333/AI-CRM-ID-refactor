from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence as checker
import tools.run_phase5k_wecom_customer_contact_production_callback_readiness_review as prod_review
import tools.run_phase5k_wecom_customer_contact_staging_live_callback_canary_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5k_wecom_customer_contact_staging_live_callback_canary_evidence.md"


def _args(**overrides):
    defaults = {
        "execute_staging_canary": False,
        "confirm_live_wecom_callback": False,
        "confirm_staging_only": False,
        "confirm_approved_event": False,
        "idempotency_key": None,
        "external_userid": None,
        "event_key": None,
        "change_type": "add_external_contact",
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_staging_runner_default_blocked(monkeypatch) -> None:
    monkeypatch.delenv("AICRM_WECOM_CONTACT_CALLBACK_LIVE_ADAPTER_ENABLED", raising=False)
    report = staging_runner.build_report(_args())
    assert report["result_status"] == "not_executed_missing_live_adapter_enabled"
    assert report["live_callback_processed"] is False


def test_missing_approvals_and_target_are_blocked(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_WECOM_CONTACT_CALLBACK_LIVE_ADAPTER_ENABLED", "1")
    report = staging_runner.build_report(_args(execute_staging_canary=True))
    assert report["result_status"] == "not_executed_missing_live_callback_approval"
    assert report["production_contact_write_executed"] is False


def test_missing_target_event_idempotency_and_confirm_flags(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.SECRET_ENV:
        monkeypatch.setenv(name, "present")
    assert staging_runner.build_report(_args(execute_staging_canary=True))["result_status"] == "not_executed_missing_external_userid"
    assert staging_runner.build_report(_args(execute_staging_canary=True, external_userid="external_userid_001"))["result_status"] == "not_executed_missing_event_key"
    assert staging_runner.build_report(_args(execute_staging_canary=True, external_userid="external_userid_001", event_key="event-1"))["result_status"] == "not_executed_missing_idempotency_key"
    assert staging_runner.build_report(_args(execute_staging_canary=True, external_userid="external_userid_001", event_key="event-1", idempotency_key="idem"))["result_status"] == "not_executed_missing_confirm_live_callback"


def test_batch_targets_and_events_rejected(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.SECRET_ENV:
        monkeypatch.setenv(name, "present")
    common = dict(execute_staging_canary=True, idempotency_key="idem", confirm_live_wecom_callback=True, confirm_staging_only=True, confirm_approved_event=True)
    assert staging_runner.build_report(_args(external_userid="external_one,external_two", event_key="event-1", **common))["result_status"] == "not_executed_batch_target_rejected"
    assert staging_runner.build_report(_args(external_userid="external_one", event_key="event-1,event-2", **common))["result_status"] == "not_executed_batch_event_rejected"


def test_evidence_redacts_external_userid(monkeypatch) -> None:
    for name in staging_runner.FLAG_ENV:
        monkeypatch.setenv(name, "1")
    for name in staging_runner.SECRET_ENV:
        monkeypatch.setenv(name, "present")
    report = staging_runner.build_report(
        _args(
            execute_staging_canary=True,
            external_userid="external_userid_sensitive_1234",
            event_key="event-1",
            idempotency_key="idem",
            confirm_live_wecom_callback=True,
            confirm_staging_only=True,
            confirm_approved_event=True,
        )
    )
    assert report["external_userid_redacted"] != "external_userid_sensitive_1234"
    assert report["production_contact_write_executed"] is False


def test_production_readiness_review_never_processes_live_callback(tmp_path) -> None:
    evidence = tmp_path / "staging.json"
    evidence.write_text(json.dumps({"result_status": "staging_canary_phase5j_blocked", "external_userid_redacted": "exte***1234", "side_effect_safety": {}}), encoding="utf-8")
    report = prod_review.build_report(staging_evidence_json=str(evidence), confirm_no_production_live_callback=True)
    assert report["production_live_callback_processed"] is False
    assert report["production_contact_write_executed"] is False
    assert report["production_identity_mapping_write_executed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production callback cutover enabled",
        "production contact write enabled",
        "production identity mapping write enabled",
        "production canary approved",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
