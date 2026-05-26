from __future__ import annotations

import argparse
from pathlib import Path

import tools.check_phase5v_media_upload_live_adapter_behind_flag as checker
from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter
from aicrm_next.integration_gateway.media_live_adapter import build_media_upload_live_adapter
from tools import run_phase5v_media_upload_live_production_dry_run_gate as prod_runner
from tools import run_phase5v_media_upload_live_staging_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5v_media_upload_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5v_media_upload_live_adapter_behind_flag.yaml"


def _staging_args(**overrides):
    values = {
        "dry_run_live_gate": False,
        "execute_live_staging": False,
        "confirm_live_media_upload": False,
        "confirm_staging_only": False,
        "confirm_no_public_publish": False,
        "idempotency_key": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _prod_args(**overrides):
    values = {
        "dry_run": False,
        "confirm_no_live_upload": False,
        "confirm_no_public_publish": False,
        "confirm_no_delete": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_live_adapter_default_blocked() -> None:
    adapter = build_media_upload_live_adapter()
    result = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", operator="test", idempotency_key="idem")
    assert result["ok"] is False
    assert result["error_code"] == "live_adapter_not_enabled"
    assert result["live_provider_upload_executed"] is False
    assert result["public_media_url_published"] is False


def test_missing_approval_and_config_return_blocked(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_LIVE_ADAPTER_ENABLED", "1")
    adapter = build_media_upload_live_adapter(confirm_live_media_upload=True)
    result = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", operator="test", idempotency_key="idem-approval")
    assert result["error_code"] == "live_upload_not_approved"
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_LIVE_UPLOAD_APPROVED", "1")
    result = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", operator="test", idempotency_key="idem-config")
    assert result["error_code"] == "media_config_missing"


def test_missing_idempotency_returns_error() -> None:
    adapter = build_media_upload_live_adapter()
    result = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", operator="test", idempotency_key="")
    assert result["error_code"] == "idempotency_key_required"


def test_idempotency_replay_and_conflict_work() -> None:
    adapter = build_media_upload_live_adapter()
    first = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", operator="test", idempotency_key="idem-replay")
    replay = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", operator="test", idempotency_key="idem-replay")
    conflict = adapter.upload_media_live(data_base64="ZmFrZQ==", file_name="other.png", content_type="image/png", operator="test", idempotency_key="idem-replay")
    assert first["result_status"] == "blocked"
    assert replay["result_status"] == "replay"
    assert replay["idempotency_replay"] is True
    assert conflict["result_status"] == "conflict"
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_phase5u_fake_stub_behavior_still_works() -> None:
    result = CloudStorageAdapter("fake").put_base64_object(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", idempotency_key="idem-5u")
    assert result["ok"] is True
    assert result["side_effect_executed"] is False


def test_staging_runner_default_blocked() -> None:
    result = staging_runner.build_report(_staging_args())
    assert result["ok"] is False
    assert result["live_provider_upload_executed"] is False
    assert result["public_media_url_published"] is False


def test_staging_runner_requires_confirm_flags(monkeypatch) -> None:
    for env in staging_runner.REQUIRED_ENV:
        monkeypatch.setenv(env, "1")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_NAME", "fake-provider")
    monkeypatch.setenv("AICRM_MEDIA_UPLOAD_PROVIDER_SECRET", "redacted-test-secret")
    result = staging_runner.build_report(_staging_args(execute_live_staging=True, confirm_live_media_upload=True, idempotency_key="idem-stage"))
    assert result["result_status"] == "not_executed_missing_confirm_staging_only"
    result = staging_runner.build_report(_staging_args(execute_live_staging=True, confirm_live_media_upload=True, confirm_staging_only=True, idempotency_key="idem-stage"))
    assert result["result_status"] == "not_executed_missing_confirm_no_public_publish"


def test_production_dry_run_gate_never_calls_live_provider() -> None:
    result = prod_runner.build_report(_prod_args(dry_run=True, confirm_no_live_upload=True, confirm_no_public_publish=True, confirm_no_delete=True))
    assert result["ok"] is True
    assert result["production_live_upload_executed"] is False
    assert result["public_media_url_published"] is False
    assert result["destructive_delete_executed"] is False


def test_side_effect_safety_forbids_high_risk_actions() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())
    assert data["authorizations"]["production_live_upload_authorized"] is False
    assert data["authorizations"]["public_media_url_publication_authorized"] is False
    assert data["authorizations"]["destructive_delete_authorized"] is False


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
