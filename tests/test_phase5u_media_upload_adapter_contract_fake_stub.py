from __future__ import annotations

import argparse
from pathlib import Path

from aicrm_next.integration_gateway.media_adapters import CloudStorageAdapter, WeComMediaAdapter
import tools.check_phase5u_media_upload_adapter_contract_fake_stub as checker
import tools.run_phase5u_media_upload_fake_stub_production_dry_run as prod_runner
import tools.run_phase5u_media_upload_fake_stub_staging_smoke as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.md"
PLAN_YAML = ROOT / "docs/development/phase_5u_media_upload_adapter_contract_fake_stub.yaml"


def _staging_args(**overrides):
    values = {"idempotency_key": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def _prod_args(**overrides):
    values = {
        "dry_run": False,
        "confirm_no_live_upload": False,
        "confirm_no_public_publish": False,
        "idempotency_key": None,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_fake_media_adapters_are_deterministic() -> None:
    first = CloudStorageAdapter("fake").put_base64_object(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", idempotency_key="idem-media")
    second = CloudStorageAdapter("fake").put_base64_object(data_base64="ZmFrZQ==", file_name="fixture.png", content_type="image/png", idempotency_key="idem-media")
    assert first["storage_key"] == second["storage_key"]
    first_media = WeComMediaAdapter("fake").upload_image(data_base64="ZmFrZQ==", file_name="fixture.png", idempotency_key="idem-wecom")
    second_media = WeComMediaAdapter("fake").upload_image(data_base64="ZmFrZQ==", file_name="fixture.png", idempotency_key="idem-wecom")
    assert first_media["media_id"] == second_media["media_id"]


def test_staging_runner_default_blocked() -> None:
    report = staging_runner.build_report(_staging_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_staging_fake_stub_approval"
    assert report["live_provider_upload_executed"] is False


def test_staging_runner_approved_fake_stub_has_no_live_side_effects(monkeypatch) -> None:
    monkeypatch.setenv(staging_runner.APPROVAL_ENV, "1")
    report = staging_runner.build_report(_staging_args(idempotency_key="idem-staging"))
    assert report["ok"] is True
    assert report["metadata_valid"] is True
    assert report["live_provider_upload_executed"] is False
    assert report["network_call_executed"] is False
    assert report["public_media_url_published"] is False
    assert report["raw_file_exposed"] is False


def test_production_dry_run_requires_confirm_flags() -> None:
    report = prod_runner.build_report(_prod_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_dry_run"
    report = prod_runner.build_report(_prod_args(dry_run=True))
    assert report["result_status"] == "not_executed_missing_confirm_no_live_upload"


def test_production_dry_run_ready_has_no_live_upload() -> None:
    report = prod_runner.build_report(_prod_args(dry_run=True, confirm_no_live_upload=True, confirm_no_public_publish=True))
    assert report["ok"] is True
    assert report["live_provider_upload_executed"] is False
    assert report["public_media_url_published"] is False
    assert report["destructive_delete_executed"] is False


def test_yaml_authorizations_and_side_effects_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert all(value is False for value in data["side_effect_safety"].values())


def test_metadata_policy_forbids_raw_file_and_public_url_exposure() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["metadata_policy"]["raw_file_output_forbidden"] is True
    assert data["metadata_policy"]["public_url_redaction_required"] is True
    assert data["fake_stub_runtime"]["network_call_allowed"] is False
    assert data["fake_stub_runtime"]["public_url_publication_allowed"] is False


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "live provider upload enabled",
        "production media publish enabled",
        "public media url publication enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
