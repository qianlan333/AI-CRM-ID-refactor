#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    target = Path(path)
    if not target.exists():
        return None
    try:
        return json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    evidence = _load(args.staging_evidence_json)
    if not evidence:
        missing.append("not_executed_missing_staging_evidence")
    elif evidence.get("result_status", "").startswith("not_executed"):
        missing.append("not_executed_invalid_staging_evidence")
    if not args.confirm_no_production_live_call:
        missing.append("not_executed_missing_confirm_no_production_live_call")
    if not args.confirm_no_outbound_send:
        missing.append("not_executed_missing_confirm_no_outbound_send")
    if not args.confirm_no_automation_execution:
        missing.append("not_executed_missing_confirm_no_automation_execution")
    ready = not missing
    return {
        "ok": ready,
        "mode": "openclaw_mcp_ai_assist_production_readiness_review",
        "ready_for_phase5ai_production_canary_readiness": ready,
        "result_status": "production_readiness_review_ready" if ready else missing[0],
        "missing_items": missing,
        "evidence_summary": {
            "result_status": evidence.get("result_status") if evidence else None,
            "prompt_redacted": evidence.get("prompt_redacted") if evidence else None,
            "credential_redacted": evidence.get("credential_redacted") if evidence else None,
        },
        "production_live_call_executed": False,
        "outbound_send_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "production_live_call_executed", "outbound_send_executed", "automation_execution_executed")
    Path(path).write_text("# Phase 5AH Production Readiness Review\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
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
