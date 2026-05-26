#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SIDE_EFFECT_SAFETY = {
    "real_mcp_call_allowed": False,
    "real_openclaw_call_allowed": False,
    "real_llm_call_allowed": False,
    "deepseek_call_allowed": False,
    "outbound_send_allowed": False,
    "prompt_raw_output_allowed": False,
    "credential_output_allowed": False,
    "timer_execution_allowed": False,
    "automation_execution_allowed": False,
    "production_write_allowed": False,
}


def _request_hash(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.confirm_no_live_call:
        missing.append("not_executed_missing_confirm_no_live_call")
    ready = not missing
    payload = {"mode": "production_fake_stub_dry_run", "confirm_no_live_call": bool(args.confirm_no_live_call)}
    return {
        "ok": ready,
        "mode": "production_fake_stub_dry_run",
        "result_status": "production_fake_stub_dry_run_ready" if ready else missing[0],
        "ready_for_phase5ag_live_adapter_planning": ready,
        "missing_items": missing,
        "real_mcp_call_executed": False,
        "real_openclaw_call_executed": False,
        "real_llm_call_executed": False,
        "deepseek_call_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "credential_used": False,
        "prompt_redacted": True,
        "credential_redacted": True,
        "request_hash": _request_hash(payload),
        "side_effect_safety": SIDE_EFFECT_SAFETY,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5AF OpenClaw/MCP/AI Assist Production Fake Stub Dry Run",
        "",
        f"- ok: {report['ok']}",
        f"- result_status: {report['result_status']}",
        f"- real_mcp_call_executed: {report['real_mcp_call_executed']}",
        f"- real_openclaw_call_executed: {report['real_openclaw_call_executed']}",
        f"- real_llm_call_executed: {report['real_llm_call_executed']}",
        f"- deepseek_call_executed: {report['deepseek_call_executed']}",
        f"- outbound_send_executed: {report['outbound_send_executed']}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-no-live-call", action="store_true")
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
