from __future__ import annotations

import argparse
from pathlib import Path

from aicrm_next.integration_gateway.openclaw_mcp_ai_assist_live_adapter import build_openclaw_mcp_ai_assist_live_adapter
import tools.check_phase5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag as checker
from tools import run_phase5ag_openclaw_mcp_ai_assist_live_production_dry_run_gate as prod_runner
from tools import run_phase5ag_openclaw_mcp_ai_assist_live_staging_evidence as staging_runner


ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.md"
PLAN_YAML = ROOT / "docs/development/phase_5ag_openclaw_mcp_ai_assist_live_adapter_behind_flag.yaml"


def _staging_args(**overrides):
    values = {
        "dry_run_live_gate": False,
        "execute_staging_live": False,
        "confirm_live_call": False,
        "confirm_staging_only": False,
        "confirm_redaction": False,
        "confirm_no_outbound_send": False,
        "confirm_no_automation_execution": False,
        "idempotency_key": None,
        "prompt": "",
        "tool_name": "",
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _prod_args(**overrides):
    values = {
        "dry_run": False,
        "confirm_no_production_live_call": False,
        "confirm_no_outbound_send": False,
        "confirm_no_automation_execution": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def test_checker_passes() -> None:
    report = checker.build_report()
    assert report["overall"] == "PASS", report["blockers"]


def test_live_adapter_default_blocked() -> None:
    adapter = build_openclaw_mcp_ai_assist_live_adapter()
    result = adapter.call_mcp_tool_live(tool_name="safe.lookup", arguments={"prompt": "hello"}, operator="test", idempotency_key="idem")
    assert result["ok"] is False
    assert result["error_code"] == "live_adapter_not_enabled"
    assert result["real_mcp_call_executed"] is False
    assert result["outbound_send_executed"] is False


def test_missing_approval_and_config_return_blocked(monkeypatch) -> None:
    monkeypatch.setenv("AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_ADAPTER_ENABLED", "1")
    adapter = build_openclaw_mcp_ai_assist_live_adapter(confirm_no_outbound_send=True, confirm_no_automation_execution=True)
    result = adapter.run_ai_assist_completion_live(prompt="hello", context={"secret": "token-abc"}, operator="test", idempotency_key="idem-approval")
    assert result["error_code"] == "live_call_not_approved"
    monkeypatch.setenv("AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_CALL_APPROVED", "1")
    result = adapter.run_ai_assist_completion_live(prompt="hello", context={}, operator="test", idempotency_key="idem-config")
    assert result["error_code"] == "adapter_config_missing"


def test_missing_idempotency_and_prompt_validation() -> None:
    adapter = build_openclaw_mcp_ai_assist_live_adapter()
    assert adapter.call_mcp_tool_live(tool_name="safe.lookup", arguments={}, operator="test", idempotency_key="")["error_code"] == "idempotency_key_required"
    assert adapter.run_ai_assist_completion_live(prompt="", context={}, operator="test", idempotency_key="idem")["error_code"] == "prompt_required"


def test_idempotency_replay_and_conflict() -> None:
    adapter = build_openclaw_mcp_ai_assist_live_adapter()
    first = adapter.call_mcp_tool_live(tool_name="safe.lookup", arguments={"value": "one"}, operator="test", idempotency_key="idem-replay")
    replay = adapter.call_mcp_tool_live(tool_name="safe.lookup", arguments={"value": "one"}, operator="test", idempotency_key="idem-replay")
    conflict = adapter.call_mcp_tool_live(tool_name="safe.lookup", arguments={"value": "two"}, operator="test", idempotency_key="idem-replay")
    assert first["result_status"] == "blocked"
    assert replay["result_status"] == "replay"
    assert conflict["result_status"] == "conflict"


def test_redaction_removes_prompt_and_credentials() -> None:
    adapter = build_openclaw_mcp_ai_assist_live_adapter()
    result = adapter.run_ai_assist_completion_live(prompt="please use sk-secret-token", context={"credential": "secret"}, operator="test", idempotency_key="idem-redact")
    assert result["prompt_redacted"] is True
    assert result["credential_redacted"] is True
    assert "sk-secret-token" not in str(result)
    assert "secret" not in str(result.get("context_redacted", {}))


def test_staging_runner_default_blocked_and_requires_flags() -> None:
    default = staging_runner.build_report(_staging_args())
    assert default["ok"] is False
    assert default["real_mcp_call_executed"] is False
    missing = staging_runner.build_report(_staging_args(execute_staging_live=True, confirm_live_call=True, confirm_staging_only=True, confirm_redaction=True, confirm_no_outbound_send=True, idempotency_key="idem", prompt="hello"))
    assert missing["result_status"] == "not_executed_missing_aicrm_openclaw_mcp_ai_assist_live_adapter_enabled"


def test_production_dry_run_gate_never_calls_live_provider() -> None:
    result = prod_runner.build_report(_prod_args(dry_run=True, confirm_no_production_live_call=True, confirm_no_outbound_send=True, confirm_no_automation_execution=True))
    assert result["ok"] is True
    assert result["production_live_call_executed"] is False
    assert result["outbound_send_executed"] is False
    assert result["automation_execution_executed"] is False


def test_side_effect_safety_and_docs_forbid_unsafe_states() -> None:
    data = checker.load_yaml(PLAN_YAML)
    assert all(value is False for value in data["side_effect_safety"].values())
    text = DOC.read_text(encoding="utf-8").lower()
    forbidden = ["real mcp call enabled", "real openclaw call enabled", "real llm call enabled", "deepseek call enabled", "outbound send enabled", "timer execution enabled", "automation execution enabled", "route owner switched", "fallback removed", "production_compat changed", "delete_ready true", "delete_ready: true"]
    assert not any(claim in text for claim in forbidden)
