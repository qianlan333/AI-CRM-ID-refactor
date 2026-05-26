from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5w_media_upload_staging_live_canary_evidence as checker
from tools import run_phase5w_media_upload_production_live_readiness_review as prod_review
from tools import run_phase5w_media_upload_staging_live_canary_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5w_media_upload_staging_live_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5w_media_upload_staging_live_canary_evidence.yaml"


def _staging_args(**overrides):
    values = {
        "execute_staging_canary": False,
        "confirm_live_media_upload": False,
        "confirm_staging_only": False,
        "confirm_approved_test_file": False,
        "confirm_no_public_publish": False,
        "idempotency_key": None,
        "file_name": None,
        "content_type": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _review_args(**overrides):
    values = {
        "staging_evidence_json": None,
        "confirm_no_production_live_upload": False,
        "confirm_no_public_publish": False,
        "confirm_no_delete": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_staging_runner_default_blocked() -> None:
    report = staging_runner.build_report(_staging_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_live_adapter_enabled"
    assert report["live_provider_upload_executed"] is False


def test_missing_approval_and_target_return_blocked(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_LIVE_ADAPTER_ENABLED", "1")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_LIVE_UPLOAD_APPROVED", "1")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_CONFIG_REVIEWED", "1")
    monkeypatch.setenv("AICRM_PHASE5V_MEDIA_UPLOAD_STAGING_LIVE_APPROVED", "1")
    report = staging_runner.build_report(_staging_args())
    assert report["result_status"] == "not_executed_missing_staging_canary_approval"
    monkeypatch.setenv("AICRM_PHASE5W_MEDIA_UPLOAD_STAGING_CANARY_APPROVED", "1")
    report = staging_runner.build_report(_staging_args())
    assert report["result_status"] == "not_executed_missing_target_approval"


def test_missing_target_idempotency_and_confirm_flags_return_blocked(monkeypatch) -> None:
    for env in staging_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_NAME", "fake-provider")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_SECRET", "redacted-test-secret")
    report = staging_runner.build_report(_staging_args(execute_staging_canary=True))
    assert report["result_status"] == "not_executed_missing_confirm_live_media_upload"
    report = staging_runner.build_report(_staging_args(execute_staging_canary=True, confirm_live_media_upload=True, confirm_staging_only=True, confirm_approved_test_file=True, confirm_no_public_publish=True))
    assert report["result_status"] == "not_executed_missing_idempotency_key"
    report = staging_runner.build_report(_staging_args(execute_staging_canary=True, confirm_live_media_upload=True, confirm_staging_only=True, confirm_approved_test_file=True, confirm_no_public_publish=True, idempotency_key="idem"))
    assert report["result_status"] == "not_executed_missing_file_name"


def test_batch_file_target_rejected(monkeypatch) -> None:
    for env in staging_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_NAME", "fake-provider")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_SECRET", "redacted-test-secret")
    report = staging_runner.build_report(_staging_args(execute_staging_canary=True, confirm_live_media_upload=True, confirm_staging_only=True, confirm_approved_test_file=True, confirm_no_public_publish=True, idempotency_key="idem", file_name="a.png,b.png", content_type="image/png"))
    assert report["result_status"] == "not_executed_batch_file_target_rejected"


def test_evidence_redacts_file_metadata() -> None:
    report = staging_runner.build_report(_staging_args(file_name="fixture-sensitive-name.png", content_type="image/png"))
    assert report["file_name_redacted"] != "fixture-sensitive-name.png"
    assert "***" in report["file_name_redacted"]


def test_production_readiness_review_never_calls_provider(tmp_path: Path) -> None:
    evidence = tmp_path / "staging.json"
    evidence.write_text(json.dumps({"mode": "media_upload_staging_live_canary_evidence", "result_status": "staging_media_canary_completed", "public_media_url_published": False, "production_upload_executed": False, "destructive_delete_executed": False, "side_effect_safety": {}, "file_name_redacted": "fi***ng"}), encoding="utf-8")
    report = prod_review.build_report(_review_args(staging_evidence_json=str(evidence), confirm_no_production_live_upload=True, confirm_no_public_publish=True, confirm_no_delete=True))
    assert report["ok"] is True
    assert report["production_live_upload_executed"] is False
    assert report["public_media_url_published"] is False
    assert report["destructive_delete_executed"] is False


def test_production_readiness_review_blocks_missing_or_invalid_evidence(tmp_path: Path) -> None:
    report = prod_review.build_report(_review_args(confirm_no_production_live_upload=True, confirm_no_public_publish=True, confirm_no_delete=True))
    assert report["result_status"] == "not_executed_missing_staging_evidence"
    evidence = tmp_path / "blocked.json"
    evidence.write_text(json.dumps({"mode": "media_upload_staging_live_canary_evidence", "result_status": "not_executed_missing_live_adapter_enabled"}), encoding="utf-8")
    report = prod_review.build_report(_review_args(staging_evidence_json=str(evidence), confirm_no_production_live_upload=True, confirm_no_public_publish=True, confirm_no_delete=True))
    assert report["result_status"] == "not_executed_invalid_staging_evidence"


def test_yaml_side_effect_safety_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())
    assert data["target_safety"]["batch_upload_allowed"] is False
    assert data["target_safety"]["public_media_url_publication_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production live upload enabled",
        "public media url publication enabled",
        "destructive delete enabled",
        "raw file exposure enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
