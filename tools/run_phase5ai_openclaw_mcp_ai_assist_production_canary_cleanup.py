#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    target = Path(path)
    if not target.exists():
        return {}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    evidence = _load(args.canary_evidence_json)
    if not evidence:
        missing.append("not_executed_missing_canary_evidence")
    if not _enabled("AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_PRODUCTION_CLEANUP_APPROVED"):
        missing.append("not_executed_missing_cleanup_approval")
    if not _enabled("AICRM_PHASE5AI_OPENCLAW_MCP_AI_ASSIST_ROLLBACK_OWNER_APPROVED"):
        missing.append("not_executed_missing_rollback_owner")
    for attr, status in (
        ("confirm_cleanup_reviewed", "not_executed_missing_confirm_cleanup_reviewed"),
        ("confirm_no_provider_cleanup", "not_executed_missing_confirm_no_provider_cleanup"),
        ("confirm_no_outbound_send", "not_executed_missing_confirm_no_outbound_send"),
        ("confirm_no_automation_execution", "not_executed_missing_confirm_no_automation_execution"),
        ("confirm_no_batch_cleanup", "not_executed_missing_confirm_no_batch_cleanup"),
    ):
        if not getattr(args, attr):
            missing.append(status)
    return {
        "ok": not missing,
        "mode": "openclaw_mcp_ai_assist_production_canary_cleanup",
        "result_status": "cleanup_ready_local_artifact_only" if not missing else missing[0],
        "cleanup_executed": False,
        "provider_cleanup_executed": False,
        "outbound_send_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
        "batch_cleanup_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "provider_cleanup_executed": False,
            "outbound_send_executed": False,
            "timer_execution_executed": False,
            "automation_execution_executed": False,
            "batch_cleanup_executed": False,
        },
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = ("ok", "result_status", "cleanup_executed", "provider_cleanup_executed", "automation_execution_executed")
    Path(path).write_text("# Phase 5AI OpenClaw MCP AI Assist Cleanup\n\n" + "\n".join(f"- {key}: {report[key]}" for key in fields) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canary-evidence-json")
    parser.add_argument("--confirm-cleanup-reviewed", action="store_true")
    parser.add_argument("--confirm-no-provider-cleanup", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--confirm-no-automation-execution", action="store_true")
    parser.add_argument("--confirm-no-batch-cleanup", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report["ok"] else "BLOCKED", "ok": report["ok"], "status": report["result_status"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
