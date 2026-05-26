#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import run_phase5ag_openclaw_mcp_ai_assist_live_staging_evidence as phase5ag


REQUIRED_ENV = [
    *phase5ag.REQUIRED_ENV,
    "AICRM_PHASE5AH_OPENCLAW_MCP_AI_ASSIST_STAGING_CANARY_APPROVED",
    "AICRM_PHASE5AH_OPENCLAW_MCP_AI_ASSIST_TARGET_APPROVED",
]


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip() == "1"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.execute_staging_canary:
        missing.append("not_executed_missing_execute_staging_canary")
    for env_name in REQUIRED_ENV:
        if args.execute_staging_canary and not _enabled(env_name):
            missing.append(f"not_executed_missing_{env_name.lower()}")
    required_flags = [
        ("confirm_live_call", "not_executed_missing_confirm_live_call"),
        ("confirm_staging_only", "not_executed_missing_confirm_staging_only"),
        ("confirm_approved_target", "not_executed_missing_confirm_approved_target"),
        ("confirm_redaction", "not_executed_missing_confirm_redaction"),
        ("confirm_no_outbound_send", "not_executed_missing_confirm_no_outbound_send"),
        ("confirm_no_automation_execution", "not_executed_missing_confirm_no_automation_execution"),
    ]
    for attr, status in required_flags:
        if args.execute_staging_canary and not getattr(args, attr):
            missing.append(status)
    if args.execute_staging_canary and not args.idempotency_key:
        missing.append("not_executed_missing_idempotency_key")
    if args.execute_staging_canary and bool(args.prompt) == bool(args.tool_name):
        missing.append("not_executed_requires_exactly_one_prompt_or_tool")
    if missing:
        return _blocked(missing[0], missing)
    upstream_args = argparse.Namespace(
        dry_run_live_gate=False,
        execute_staging_live=True,
        confirm_live_call=args.confirm_live_call,
        confirm_staging_only=args.confirm_staging_only,
        confirm_redaction=args.confirm_redaction,
        confirm_no_outbound_send=args.confirm_no_outbound_send,
        confirm_no_automation_execution=args.confirm_no_automation_execution,
        idempotency_key=args.idempotency_key,
        prompt=args.prompt or "",
        tool_name=args.tool_name or "",
    )
    result = phase5ag.build_report(upstream_args)
    return {
        **result,
        "mode": "openclaw_mcp_ai_assist_staging_live_canary_evidence",
        "single_target_only": True,
        "approved_target_confirmed": True,
        "cleanup_required": bool(result.get("provider_call_executed")),
        "cleanup_guidance": "Capture separate cleanup approval before reversing any staging artifact.",
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _blocked(status: str, missing: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "openclaw_mcp_ai_assist_staging_live_canary_evidence",
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
        "single_target_only": True,
        "cleanup_required": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": {
            "production_live_call_allowed": False,
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
    keys = ("ok", "result_status", "real_mcp_call_executed", "real_openclaw_call_executed", "real_llm_call_executed", "outbound_send_executed")
    Path(path).write_text("# Phase 5AH Staging Canary Evidence\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-staging-canary", action="store_true")
    parser.add_argument("--confirm-live-call", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-approved-target", action="store_true")
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
