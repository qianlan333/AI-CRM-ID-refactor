from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5an_questionnaire_external_submit_production_canary_readiness as checker
from tools import run_phase5an_questionnaire_external_submit_production_canary_cleanup as cleanup
from tools import run_phase5an_questionnaire_external_submit_production_canary_readiness as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.md"
PLAN_YAML = ROOT / "docs/development/phase_5an_questionnaire_external_submit_production_canary_readiness.yaml"


def _args(**overrides):
    values = {
        "staging_evidence_json": None,
        "slug": None,
        "submission_id": None,
        "idempotency_key": None,
        "batch_submit": False,
        "batch_tag_write": False,
        "confirm_no_production_owner_switch": False,
        "confirm_no_production_write": False,
        "confirm_no_production_tag_write": False,
        "confirm_no_outbound_send": False,
        "confirm_single_approved_target": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_runner_default_blocked() -> None:
    report = runner.build_report(_args())
    assert report["ok"] is False
    assert report["result_status"] == "not_executed_missing_staging_evidence"
    assert report["production_public_submit_write_executed"] is False


def test_missing_staging_evidence_and_approvals_block() -> None:
    report = runner.build_report(_args(slug="phase5an", submission_id="submission-1", idempotency_key="idem"))
    assert "not_executed_missing_staging_evidence" in report["missing_items"]
    assert "not_executed_missing_production_canary_planning_approval" in report["missing_items"]


def test_missing_target_idempotency_and_confirm_flags_block() -> None:
    report = runner.build_report(_args(confirm_no_production_owner_switch=True, confirm_no_production_write=True, confirm_no_production_tag_write=True, confirm_no_outbound_send=True, confirm_single_approved_target=True))
    assert "not_executed_missing_idempotency_key" in report["missing_items"]
    assert "not_executed_missing_slug" in report["missing_items"]
    assert "not_executed_missing_submission_id" in report["missing_items"]


def test_batch_submit_and_tag_write_rejected() -> None:
    report = runner.build_report(_args(slug="phase5an", submission_id="submission-1", idempotency_key="idem", batch_submit=True, batch_tag_write=True))
    assert "not_executed_batch_submit_forbidden" in report["missing_items"]
    assert "not_executed_batch_tag_write_forbidden" in report["missing_items"]


def test_cleanup_runner_default_blocked() -> None:
    report = cleanup.build_report(argparse.Namespace(canary_evidence_json=None, confirm_cleanup_reviewed=False, confirm_no_production_submit_delete=False, confirm_no_production_identity_delete=False, confirm_no_production_tag_cleanup=False, confirm_no_batch_cleanup=False))
    assert report["ok"] is False
    assert report["cleanup_executed"] is False
    assert report["production_submit_delete_executed"] is False
    assert report["production_identity_delete_executed"] is False


def test_staging_evidence_must_not_qualify_when_blocked(tmp_path: Path) -> None:
    evidence = tmp_path / "staging.json"
    evidence.write_text(json.dumps({"result_status": "not_executed_missing_execute_staging_canary", "production_public_submit_write_executed": False, "production_identity_write_executed": False, "production_tag_write_executed": False, "side_effect_safety": {}}), encoding="utf-8")
    report = runner.build_report(_args(staging_evidence_json=str(evidence), slug="phase5an", submission_id="submission-1", idempotency_key="idem"))
    assert "not_executed_invalid_staging_evidence" in report["missing_items"]


def test_yaml_safety_and_docs_forbid_unsafe_states() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["production_canary_tooling_authorized"] is True
    for key, value in data["authorizations"].items():
        if key != "production_canary_tooling_authorized":
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
