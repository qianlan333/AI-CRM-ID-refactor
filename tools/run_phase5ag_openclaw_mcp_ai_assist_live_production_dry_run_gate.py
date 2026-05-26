#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.dry_run:
        missing.append("not_executed_missing_dry_run")
    if not args.confirm_no_production_live_call:
        missing.append("not_executed_missing_confirm_no_production_live_call")
    if not args.confirm_no_outbound_send:
        missing.append("not_executed_missing_confirm_no_outbound_send")
    if not args.confirm_no_automation_execution:
        missing.append("not_executed_missing_confirm_no_automation_execution")
    ready = not missing
    return {
        "ok": ready,
        "mode": "openclaw_mcp_ai_assist_production_dry_run_gate",
        "result_status": "production_dry_run_gate_ready" if ready else missing[0],
        "missing_items": missing,
        "production_live_call_executed": False,
        "real_mcp_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_llm_call_executed": False,
        "deepseek_call_executed": False,
        "outbound_send_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
        "prompt_redacted": True,
        "credential_redacted": True,
        "route_owner_changed": False,
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
    Path(path).write_text("# Phase 5AG Production Dry Run Gate\n\n" + "\n".join(f"- {key}: {report[key]}" for key in ("ok", "result_status", "production_live_call_executed", "outbound_send_executed", "automation_execution_executed")) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-production-live-call", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--confirm-no-automation-execution", action="store_true")
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
