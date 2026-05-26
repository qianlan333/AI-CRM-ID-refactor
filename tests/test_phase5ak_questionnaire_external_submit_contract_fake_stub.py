from __future__ import annotations

import argparse
from pathlib import Path

from aicrm_next.questionnaire.external_submit_adapter import build_questionnaire_external_submit_fake_stub_adapter
import tools.check_phase5ak_questionnaire_external_submit_contract_fake_stub as checker
from tools import run_phase5ak_questionnaire_external_submit_fake_stub_production_dry_run as prod_runner
from tools import run_phase5ak_questionnaire_external_submit_fake_stub_staging_smoke as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.md"
PLAN_YAML = ROOT / "docs/development/phase_5ak_questionnaire_external_submit_contract_fake_stub.yaml"


def _staging_args(**overrides):
    values = {"idempotency_key": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def _prod_args(**overrides):
    values = {"dry_run": False, "confirm_no_production_write": False, "idempotency_key": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_fake_submission_deterministic() -> None:
    adapter = build_questionnaire_external_submit_fake_stub_adapter()
    assert adapter.deterministic_fake_public_submission() == adapter.deterministic_fake_public_submission()


def test_dry_run_submit_idempotency_replay_and_conflict() -> None:
    adapter = build_questionnaire_external_submit_fake_stub_adapter()
    fake = adapter.deterministic_fake_public_submission()
    first = adapter.dry_run_public_submit(slug=fake["slug"], answers=fake["answers"], identity=fake["identity"], operator="test", idempotency_key="same")
    replay = adapter.dry_run_public_submit(slug=fake["slug"], answers=fake["answers"], identity=fake["identity"], operator="test", idempotency_key="same")
    conflict = adapter.dry_run_public_submit(slug="different", answers=fake["answers"], identity=fake["identity"], operator="test", idempotency_key="same")
    assert first["ok"] is True
    assert replay["result_status"] == "replay"
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_missing_idempotency_key_blocks() -> None:
    adapter = build_questionnaire_external_submit_fake_stub_adapter()
    fake = adapter.deterministic_fake_public_submission()
    result = adapter.dry_run_public_submit(slug=fake["slug"], answers=fake["answers"], identity=fake["identity"], operator="test", idempotency_key="")
    assert result["error_code"] == "idempotency_key_required"


def test_identity_and_tag_dry_runs_are_side_effect_free() -> None:
    adapter = build_questionnaire_external_submit_fake_stub_adapter()
    fake = adapter.deterministic_fake_public_submission()
    identity = adapter.dry_run_identity_mapping(submission=fake, operator="test", idempotency_key="identity")
    tag = adapter.dry_run_tag_writeback(submission=fake, tag_ids=fake["tag_ids"], operator="test", idempotency_key="tag")
    assert identity["production_identity_write_executed"] is False
    assert tag["production_tag_write_executed"] is False
    assert tag["outbound_send_executed"] is False


def test_runners_default_blocked() -> None:
    staging = staging_runner.build_report(_staging_args())
    prod = prod_runner.build_report(_prod_args(confirm_no_production_write=True))
    assert staging["ok"] is False
    assert prod["ok"] is False
    assert staging["production_tag_write_executed"] is False
    assert prod["production_public_submit_write_executed"] is False


def test_yaml_authorizations_and_side_effect_safety() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())
    assert all(value is False for value in data["side_effect_safety"].values())
    assert data["fake_stub_contract"]["external_userid_redaction_required"] is True
    assert data["next_bundle"]["recommended_next_step"] == "phase_5al_questionnaire_external_submit_live_adapter_behind_flag_bundle"


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["production public submit write enabled", "production identity write enabled", "production tag write enabled", "live oauth callback cutover enabled", "outbound send enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
