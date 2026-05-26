from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness as checker
from tools import run_phase5ai_openclaw_mcp_ai_assist_production_canary_cleanup as cleanup_runner
from tools import run_phase5ai_openclaw_mcp_ai_assist_production_canary_readiness as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.md"


def _runner_args(**overrides):
    values = {
        "staging_evidence_json": None,
        "prompt": "",
        "tool_name": "",
        "idempotency_key": None,
        "confirm_production_live_call": False,
        "confirm_single_approved_target": False,
        "confirm_redacted_evidence": False,
        "confirm_credential_non_leakage": False,
        "confirm_no_outbound_send": False,
        "confirm_no_automation_execution": False,
        "confirm_rollback_owner_approved": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _cleanup_args(**overrides):
    values = {
        "canary_evidence_json": None,
        "confirm_cleanup_reviewed": False,
        "confirm_no_provider_cleanup": False,
        "confirm_no_outbound_send": False,
        "confirm_no_automation_execution": False,
        "confirm_no_batch_cleanup": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_canary_runner_default_blocked() -> None:
    result = runner.build_report(_runner_args())
    assert result["ok"] is False
    assert result["production_live_call_executed"] is False
    assert result["outbound_send_executed"] is False
    assert result["automation_execution_executed"] is False


def test_missing_staging_evidence_blocks() -> None:
    result = runner.build_report(_runner_args(prompt="safe prompt", idempotency_key="k"))
    assert "not_executed_missing_staging_evidence" in result["missing_items"]


def test_invalid_staging_evidence_blocks(tmp_path: Path) -> None:
    evidence = tmp_path / "staging.json"
    evidence.write_text(json.dumps({"ok": False, "result_status": "not_executed_missing_approval"}), encoding="utf-8")
    result = runner.build_report(_runner_args(staging_evidence_json=str(evidence), prompt="safe prompt", idempotency_key="k"))
    assert "not_executed_invalid_staging_evidence" in result["missing_items"]


def test_missing_confirm_flags_block(tmp_path: Path) -> None:
    evidence = tmp_path / "staging.json"
    evidence.write_text(json.dumps({"ok": True, "result_status": "staging_canary_evidence_ready", "outbound_send_executed": False, "automation_execution_executed": False, "side_effect_safety": {}}), encoding="utf-8")
    result = runner.build_report(_runner_args(staging_evidence_json=str(evidence), prompt="safe prompt", idempotency_key="k"))
    assert "not_executed_missing_confirm_production_live_call" in result["missing_items"]
    assert result["production_live_call_executed"] is False


def test_batch_or_multiple_targets_rejected() -> None:
    batch = runner.build_report(_runner_args(prompt="one,two", idempotency_key="k"))
    assert "not_executed_batch_prompt_forbidden" in batch["missing_items"]
    multiple = runner.build_report(_runner_args(prompt="one", tool_name="tool", idempotency_key="k"))
    assert "not_executed_multiple_targets_forbidden" in multiple["missing_items"]


def test_cleanup_runner_default_blocked() -> None:
    result = cleanup_runner.build_report(_cleanup_args())
    assert result["ok"] is False
    assert result["cleanup_executed"] is False
    assert result["provider_cleanup_executed"] is False
    assert result["automation_execution_executed"] is False


def test_yaml_safety_flags() -> None:
    data = checker.load_yaml(ROOT / "docs/development/phase_5ai_openclaw_mcp_ai_assist_production_canary_readiness.yaml")
    assert data["authorizations"]["production_canary_tooling_authorized"] is True
    for key, value in data["authorizations"].items():
        if key != "production_canary_tooling_authorized":
            assert value is False
    assert data["production_canary"]["batch_replay_allowed"] is False
    assert data["cleanup"]["provider_cleanup_allowed"] is False
    assert all(value is False for value in data["side_effect_safety"].values())


def test_docs_do_not_claim_forbidden_states() -> None:
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["production live call enabled", "outbound send enabled", "automation execution enabled", "prompt leakage enabled", "credential leakage enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
