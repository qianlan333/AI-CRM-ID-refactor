from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5l_wecom_customer_contact_production_callback_canary_readiness as checker
import tools.run_phase5l_wecom_customer_contact_production_callback_canary_readiness as runner


def _args(**overrides):
    values = {
        "staging_evidence_json": None,
        "execute_production_canary": False,
        "external_userid": None,
        "event_key": None,
        "idempotency_key": None,
        "confirm_no_production_live_callback": False,
        "confirm_no_production_write": False,
        "confirm_production_live_callback": False,
        "confirm_single_approved_target": False,
        "confirm_rollback_owner_approved": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_runner_default_blocked() -> None:
    report = runner.build_report(_args())
    assert report["result_status"] == "not_executed_missing_staging_evidence"
    assert report["production_live_callback_processed"] is False


def test_invalid_staging_evidence_blocked(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"result_status": "not_executed_missing_live_adapter_enabled"}), encoding="utf-8")
    report = runner.build_report(_args(staging_evidence_json=str(path), confirm_no_production_live_callback=True, confirm_no_production_write=True))
    assert report["result_status"] == "not_executed_invalid_staging_evidence"


def test_missing_approvals_blocked(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps({"result_status": "staging_canary_phase5j_blocked", "external_userid_redacted": "exte***1234", "side_effect_safety": {}}), encoding="utf-8")
    for env in runner.REQUIRED_ENV:
        monkeypatch.delenv(env, raising=False)
    report = runner.build_report(_args(staging_evidence_json=str(path), confirm_no_production_live_callback=True, confirm_no_production_write=True))
    assert report["result_status"] == "not_executed_missing_production_canary_planning_approval"


def test_production_side_effects_false() -> None:
    report = runner.build_report(_args())
    assert report["production_canary_executed"] is False
    assert report["production_contact_write_executed"] is False
    assert report["production_identity_mapping_write_executed"] is False
    assert report["route_owner_changed"] is False
    assert report["production_compat_changed"] is False
    assert report["fallback_removed"] is False
