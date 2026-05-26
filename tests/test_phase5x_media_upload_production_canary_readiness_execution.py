from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5x_media_upload_production_canary_readiness_execution as checker
from tools import run_phase5x_media_upload_production_canary_cleanup as cleanup_runner
from tools import run_phase5x_media_upload_production_canary_readiness_execution as canary_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5x_media_upload_production_canary_readiness_execution.md"
PLAN_YAML = ROOT / "docs/development/phase_5x_media_upload_production_canary_readiness_execution.yaml"


def _canary_args(**overrides):
    values = {
        "staging_evidence_json": None,
        "file_name": None,
        "content_type": None,
        "idempotency_key": None,
        "confirm_production_live_media_upload": False,
        "confirm_single_approved_file": False,
        "confirm_no_public_publish": False,
        "confirm_no_delete": False,
        "confirm_rollback_owner_approved": False,
        "confirm_no_batch_upload": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _cleanup_args(**overrides):
    values = {
        "canary_evidence_json": None,
        "confirm_production_cleanup_reviewed": False,
        "confirm_same_file": False,
        "confirm_no_destructive_delete": False,
        "confirm_no_batch_cleanup": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _write_staging(tmp_path: Path) -> str:
    path = tmp_path / "staging.json"
    path.write_text(json.dumps({"mode": "media_upload_staging_live_canary_evidence", "result_status": "staging_media_canary_completed", "production_upload_executed": False, "public_media_url_published": False, "destructive_delete_executed": False, "side_effect_safety": {}, "file_name_redacted": "fi***ng"}), encoding="utf-8")
    return str(path)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_canary_runner_default_blocked() -> None:
    report = canary_runner.build_report(_canary_args())
    assert report["result_status"] == "not_executed_missing_staging_evidence"
    assert report["production_live_upload_executed"] is False


def test_missing_staging_and_invalid_staging_block(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.json"
    invalid.write_text(json.dumps({"mode": "media_upload_staging_live_canary_evidence", "result_status": "not_executed_missing_live_adapter_enabled"}), encoding="utf-8")
    report = canary_runner.build_report(_canary_args(staging_evidence_json=str(invalid)))
    assert report["result_status"] == "not_executed_invalid_staging_evidence"


def test_missing_approvals_and_confirm_flags_block(tmp_path: Path) -> None:
    staging = _write_staging(tmp_path)
    report = canary_runner.build_report(_canary_args(staging_evidence_json=staging))
    assert report["result_status"] == "not_executed_missing_live_adapter_enabled"


def test_batch_upload_rejected(tmp_path: Path, monkeypatch) -> None:
    staging = _write_staging(tmp_path)
    for env in canary_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_NAME", "fake")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_SECRET", "redacted")
    report = canary_runner.build_report(_canary_args(staging_evidence_json=staging, file_name="a.png,b.png", content_type="image/png", idempotency_key="idem"))
    assert report["result_status"] == "not_executed_batch_upload_rejected"


def test_cleanup_default_blocked() -> None:
    report = cleanup_runner.build_report(_cleanup_args())
    assert report["cleanup_executed"] is False
    assert report["destructive_delete_executed"] is False


def test_cleanup_requires_same_file_and_no_delete(tmp_path: Path, monkeypatch) -> None:
    evidence = tmp_path / "canary.json"
    evidence.write_text(json.dumps({"mode": "media_upload_production_canary_readiness_execution"}), encoding="utf-8")
    monkeypatch.setenv("AICRM_PHASE5X_MEDIA_UPLOAD_PRODUCTION_CLEANUP_APPROVED", "1")
    monkeypatch.setenv("AICRM_PHASE5X_MEDIA_UPLOAD_ROLLBACK_OWNER_APPROVED", "1")
    report = cleanup_runner.build_report(_cleanup_args(canary_evidence_json=str(evidence), confirm_production_cleanup_reviewed=True))
    assert report["result_status"] == "not_executed_missing_confirm_same_file"
    report = cleanup_runner.build_report(_cleanup_args(canary_evidence_json=str(evidence), confirm_production_cleanup_reviewed=True, confirm_same_file=True))
    assert report["result_status"] == "not_executed_missing_confirm_no_destructive_delete"


def test_side_effect_safety_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())
    assert data["production_canary"]["batch_upload_allowed"] is False
    assert data["cleanup"]["destructive_delete_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["route owner switched", "fallback removed", "production_compat changed", "batch upload enabled", "destructive delete enabled", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
