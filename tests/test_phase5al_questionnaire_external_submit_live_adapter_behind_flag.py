from __future__ import annotations

import argparse
from pathlib import Path

from aicrm_next.questionnaire.external_submit_live_adapter import build_questionnaire_external_submit_live_adapter
import tools.check_phase5al_questionnaire_external_submit_live_adapter_behind_flag as checker
from tools import run_phase5al_questionnaire_external_submit_live_production_dry_run_gate as prod_runner
from tools import run_phase5al_questionnaire_external_submit_live_staging_evidence as staging_runner

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5al_questionnaire_external_submit_live_adapter_behind_flag.yaml"


def _stage_args(**overrides):
    values = {"dry_run_live_gate": False, "execute_staging_live": False, "confirm_live_call": False, "confirm_staging_only": False, "confirm_no_production_write": False, "confirm_no_outbound_send": False, "idempotency_key": None, "slug": None}
    values.update(overrides)
    return argparse.Namespace(**values)


def _prod_args(**overrides):
    values = {"dry_run": False, "confirm_no_live_call": False, "confirm_no_production_write": False}
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_live_adapter_default_blocked() -> None:
    adapter = build_questionnaire_external_submit_live_adapter()
    result = adapter.submit_public_live(slug="safe", payload={"external_userid": "wm_raw"}, operator="test", idempotency_key="k")
    assert result["ok"] is False
    assert result["production_public_submit_write_executed"] is False
    assert result["error_code"] == "live_adapter_not_enabled"


def test_idempotency_required_and_replay() -> None:
    adapter = build_questionnaire_external_submit_live_adapter()
    missing = adapter.submit_public_live(slug="safe", payload={}, operator="test", idempotency_key="")
    first = adapter.submit_public_live(slug="safe", payload={}, operator="test", idempotency_key="same")
    replay = adapter.submit_public_live(slug="safe", payload={}, operator="test", idempotency_key="same")
    conflict = adapter.submit_public_live(slug="other", payload={}, operator="test", idempotency_key="same")
    assert missing["error_code"] == "idempotency_key_required"
    assert first["result_status"] == "blocked"
    assert replay["result_status"] == "replay"
    assert conflict["error_code"] == "duplicate_idempotency_key"


def test_runners_default_blocked() -> None:
    staging = staging_runner.build_report(_stage_args())
    prod = prod_runner.build_report(_prod_args(dry_run=True, confirm_no_live_call=True, confirm_no_production_write=True))
    assert staging["ok"] is False
    assert prod["ok"] is False
    assert prod["live_call_executed"] is False
    assert staging["production_tag_write_executed"] is False


def test_yaml_safety_flags() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["live_adapter_code_authorized"] is True
    for key, value in data["authorizations"].items():
        if key != "live_adapter_code_authorized":
            assert value is False
    assert all(value is False for value in data["side_effect_safety"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["production public submit write enabled", "production identity write enabled", "production tag write enabled", "live oauth callback cutover enabled", "outbound send enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
