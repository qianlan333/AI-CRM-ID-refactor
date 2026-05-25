from __future__ import annotations

from pathlib import Path

import tools.check_phase5n_oauth_identity_adapter_contract as checker
import tools.run_phase5n_oauth_identity_adapter_contract_evidence as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5n_oauth_identity_adapter_contract.md"
PLAN_YAML = ROOT / "docs/development/phase_5n_oauth_identity_adapter_contract.yaml"


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_runner_default_fake_stub_evidence_passes() -> None:
    report = runner.build_report()
    assert report["ok"] is True
    assert report["mode"] == "fake_stub_contract"


def test_runner_does_not_execute_live_oauth_callback() -> None:
    report = runner.build_report()
    assert report["live_oauth_call_executed"] is False
    assert report["live_callback_processed"] is False
    assert report["code_exchange_executed"] is False
    assert report["network_call_executed"] is False


def test_runner_output_has_no_production_writes_or_send() -> None:
    report = runner.build_report()
    assert report["production_session_write_executed"] is False
    assert report["production_identity_write_executed"] is False
    assert report["outbound_send_executed"] is False
    assert report["db_write_executed"] is False


def test_yaml_authorizations_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["authorizations"].values())


def test_error_mapping_complete() -> None:
    data = checker.load_yaml(PLAN_YAML)
    errors = set(data["error_mapping"]["required_error_codes"])
    assert checker.REQUIRED_ERROR_CODES <= errors


def test_side_effect_safety_all_false() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = [
        "live oauth callback cutover enabled",
        "production session write enabled",
        "production identity write enabled",
        "production success",
        "canary approved",
        "delete_ready true",
        "delete_ready: true",
    ]
    assert not any(claim in text for claim in forbidden)
