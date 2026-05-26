from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5am_questionnaire_external_submit_staging_canary_evidence as checker
from tools import run_phase5am_questionnaire_external_submit_production_readiness_review as prod_review
from tools import run_phase5am_questionnaire_external_submit_staging_canary_evidence as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5am_questionnaire_external_submit_staging_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5am_questionnaire_external_submit_staging_canary_evidence.yaml"


def _args(**overrides):
    values = {
        "execute_staging_canary": False,
        "confirm_live_call": False,
        "confirm_staging_only": False,
        "confirm_approved_target": False,
        "confirm_no_production_write": False,
        "confirm_no_outbound_send": False,
        "idempotency_key": None,
        "slug": None,
        "submission_id": None,
        "batch_submit": False,
        "batch_tag_write": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_staging_runner_default_blocked() -> None:
    report = runner.build_report(_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_execute_staging_canary"
    assert report["production_public_submit_write_executed"] is False


def test_missing_approvals_target_and_confirm_flags_block() -> None:
    report = runner.build_report(_args(execute_staging_canary=True, slug="phase5am", submission_id="submission-1", idempotency_key="idem"))
    assert "not_executed_missing_aicrm_questionnaire_external_submit_live_adapter_enabled" in report["missing_items"]
    assert "not_executed_missing_confirm_live_call" in report["missing_items"]


def test_missing_target_and_idempotency_block() -> None:
    report = runner.build_report(_args(execute_staging_canary=True, confirm_live_call=True, confirm_staging_only=True, confirm_approved_target=True, confirm_no_production_write=True, confirm_no_outbound_send=True))
    assert "not_executed_missing_idempotency_key" in report["missing_items"]
    assert "not_executed_missing_slug" in report["missing_items"]
    assert "not_executed_missing_submission_id" in report["missing_items"]


def test_batch_submit_and_tag_write_rejected() -> None:
    report = runner.build_report(_args(execute_staging_canary=True, slug="phase5am", submission_id="submission-1", idempotency_key="idem", batch_submit=True, batch_tag_write=True))
    assert "not_executed_batch_submit_forbidden" in report["missing_items"]
    assert "not_executed_batch_tag_write_forbidden" in report["missing_items"]


def test_evidence_redacts_target_fields() -> None:
    report = runner.build_report(_args(slug="questionnaire-secret-slug", submission_id="submission-secret-id"))
    assert report["slug_redacted"] == "que...lug"
    assert report["submission_id_redacted"] == "sub...-id"
    assert report["token_redacted"] is True


def test_production_review_requires_staging_evidence(tmp_path: Path) -> None:
    missing = prod_review.build_report(argparse.Namespace(staging_evidence_json=None, confirm_no_production_write=True, confirm_no_production_tag_write=True, confirm_no_outbound_send=True))
    assert missing["ok"] is False
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"result_status": "blocked", "single_submit_attempt": True, "slug_redacted": "abc", "submission_id_redacted": "def"}), encoding="utf-8")
    ready = prod_review.build_report(argparse.Namespace(staging_evidence_json=str(evidence), confirm_no_production_write=True, confirm_no_production_tag_write=True, confirm_no_outbound_send=True))
    assert ready["ok"] is True
    assert ready["production_public_submit_write_executed"] is False
    assert ready["production_tag_write_executed"] is False


def test_yaml_safety_and_docs_forbid_unsafe_states() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["staging_live_canary_possible_with_approval"] is True
    for key, value in data["authorizations"].items():
        if key != "staging_live_canary_possible_with_approval":
            assert value is False
    assert all(value is False for value in data["side_effect_safety"].values())
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "production public submit write enabled",
        "production identity write enabled",
        "production tag write enabled",
        "live oauth callback cutover enabled",
        "outbound send enabled",
        "route owner switched",
        "fallback removed",
        "production_compat changed",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
