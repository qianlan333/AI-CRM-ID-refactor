from __future__ import annotations

import argparse
import json
from pathlib import Path

import tools.check_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence as checker
from tools import run_phase5ah_openclaw_mcp_ai_assist_production_readiness_review as prod_review
from tools import run_phase5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence as runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.md"
PLAN_YAML = ROOT / "docs/development/phase_5ah_openclaw_mcp_ai_assist_staging_live_canary_evidence.yaml"


def _args(**overrides):
    values = {
        "execute_staging_canary": False,
        "confirm_live_call": False,
        "confirm_staging_only": False,
        "confirm_approved_target": False,
        "confirm_redaction": False,
        "confirm_no_outbound_send": False,
        "confirm_no_automation_execution": False,
        "idempotency_key": None,
        "prompt": "",
        "tool_name": "",
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
    assert report["outbound_send_executed"] is False


def test_missing_approvals_and_confirm_flags_block() -> None:
    report = runner.build_report(_args(execute_staging_canary=True, prompt="hello", idempotency_key="idem"))
    assert "not_executed_missing_aicrm_openclaw_mcp_ai_assist_live_adapter_enabled" in report["missing_items"]
    assert "not_executed_missing_confirm_live_call" in report["missing_items"]


def test_requires_exactly_one_prompt_or_tool(monkeypatch) -> None:
    for env_name in runner.REQUIRED_ENV:
        monkeypatch.setenv(env_name, "1")
    both = runner.build_report(_args(execute_staging_canary=True, confirm_live_call=True, confirm_staging_only=True, confirm_approved_target=True, confirm_redaction=True, confirm_no_outbound_send=True, confirm_no_automation_execution=True, idempotency_key="idem", prompt="hello", tool_name="safe.lookup"))
    assert both["result_status"] == "not_executed_requires_exactly_one_prompt_or_tool"


def test_production_review_requires_staging_evidence(tmp_path: Path) -> None:
    missing = prod_review.build_report(argparse.Namespace(staging_evidence_json=None, confirm_no_production_live_call=True, confirm_no_outbound_send=True, confirm_no_automation_execution=True))
    assert missing["ok"] is False
    evidence = tmp_path / "evidence.json"
    evidence.write_text(json.dumps({"result_status": "blocked", "prompt_redacted": True, "credential_redacted": True}), encoding="utf-8")
    invalid = prod_review.build_report(argparse.Namespace(staging_evidence_json=str(evidence), confirm_no_production_live_call=True, confirm_no_outbound_send=True, confirm_no_automation_execution=True))
    assert invalid["ok"] is True
    assert invalid["production_live_call_executed"] is False


def test_yaml_safety_and_docs_forbid_unsafe_states() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert data["authorizations"]["staging_live_canary_possible_with_approval"] is True
    for key, value in data["authorizations"].items():
        if key != "staging_live_canary_possible_with_approval":
            assert value is False
    assert all(value is False for value in data["side_effect_safety"].values())
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["production live call enabled", "outbound send enabled", "automation execution enabled", "prompt leakage enabled", "credential leakage enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
