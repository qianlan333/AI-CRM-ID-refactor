#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
import sys

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.integration_gateway.openclaw_mcp_ai_assist_live_adapter import build_openclaw_mcp_ai_assist_live_adapter


REQUIRED_ENV = [
    "AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_ADAPTER_ENABLED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_LIVE_CALL_APPROVED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_CONFIG_REVIEWED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_ENDPOINT_REVIEWED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_CREDENTIAL_SOURCE_REVIEWED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_PROMPT_REDACTION_CONFIRMED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_NO_OUTBOUND_SEND_CONFIRMED",
    "AICRM_OPENCLAW_MCP_AI_ASSIST_NO_AUTOMATION_EXECUTION_CONFIRMED",
]


def _env_enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip() == "1"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.dry_run_live_gate and not args.execute_staging_live:
        missing.append("not_executed_missing_execution_mode")
    for env_name in REQUIRED_ENV:
        if args.execute_staging_live and not _env_enabled(env_name):
            missing.append(f"not_executed_missing_{env_name.lower()}")
    if args.execute_staging_live and not args.confirm_live_call:
        missing.append("not_executed_missing_confirm_live_call")
    if args.execute_staging_live and not args.confirm_staging_only:
        missing.append("not_executed_missing_confirm_staging_only")
    if args.execute_staging_live and not args.confirm_redaction:
        missing.append("not_executed_missing_confirm_redaction")
    if args.execute_staging_live and not args.confirm_no_outbound_send:
        missing.append("not_executed_missing_confirm_no_outbound_send")
    if args.execute_staging_live and not args.confirm_no_automation_execution:
        missing.append("not_executed_missing_confirm_no_automation_execution")
    if args.execute_staging_live and not args.idempotency_key:
        missing.append("not_executed_missing_idempotency_key")
    if args.execute_staging_live and not args.prompt and not args.tool_name:
        missing.append("not_executed_missing_prompt_or_tool")
    if missing:
        return _blocked(missing[0], missing)
    adapter = build_openclaw_mcp_ai_assist_live_adapter(confirm_no_outbound_send=args.confirm_no_outbound_send, confirm_no_automation_execution=args.confirm_no_automation_execution)
    if args.tool_name:
        result = adapter.call_mcp_tool_live(tool_name=args.tool_name, arguments={"content": args.prompt or "redacted"}, operator="phase5ag_staging", idempotency_key=args.idempotency_key or "dry-run")
    else:
        result = adapter.run_ai_assist_completion_live(prompt=args.prompt or "phase5ag dry run prompt", context={"content": "redacted"}, operator="phase5ag_staging", idempotency_key=args.idempotency_key or "dry-run")
    return {
        **result,
        "mode": "openclaw_mcp_ai_assist_staging_live_evidence",
        "dry_run_live_gate": bool(args.dry_run_live_gate),
        "execute_staging_live": bool(args.execute_staging_live),
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _blocked(status: str, missing: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "openclaw_mcp_ai_assist_staging_live_evidence",
        "result_status": status,
        "missing_items": missing,
        "real_mcp_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_llm_call_executed": False,
        "deepseek_call_executed": False,
        "outbound_send_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
        "prompt_redacted": True,
        "credential_redacted": True,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": {
            "real_mcp_call_allowed_by_default": False,
            "real_openclaw_call_allowed_by_default": False,
            "real_llm_call_allowed_by_default": False,
            "deepseek_call_allowed_by_default": False,
            "outbound_send_allowed": False,
            "timer_execution_allowed": False,
            "automation_execution_allowed": False,
            "prompt_raw_output_allowed": False,
            "credential_output_allowed": False,
        },
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5AG Staging Evidence\n\n" + "\n".join(f"- {key}: {report[key]}" for key in ("ok", "result_status", "real_mcp_call_executed", "real_openclaw_call_executed", "real_llm_call_executed", "outbound_send_executed")) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-live-gate", action="store_true")
    parser.add_argument("--execute-staging-live", action="store_true")
    parser.add_argument("--confirm-live-call", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-redaction", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--confirm-no-automation-execution", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--prompt")
    parser.add_argument("--tool-name")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"ok": report["ok"], "result_status": report["result_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
