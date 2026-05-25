#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any

APPROVAL_ENV = "AICRM_PHASE5P_OAUTH_IDENTITY_PRODUCTION_DRY_RUN_APPROVED"
CONFIG_ENV = "AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED"


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def build_report(*, dry_run: bool, confirm_no_live_oauth_callback: bool) -> dict[str, Any]:
    missing: list[str] = []
    if not _enabled(APPROVAL_ENV):
        missing.append("production_dry_run_approval")
    if not _enabled(CONFIG_ENV):
        missing.append("oauth_config_review")
    if not dry_run:
        missing.append("dry_run_arg")
    if not confirm_no_live_oauth_callback:
        missing.append("confirm_no_live_oauth_callback")
    return {
        "ok": not missing,
        "mode": "production_live_oauth_dry_run_gate",
        "result_status": "ready_no_live_oauth_callback" if not missing else "blocked_missing_required_gate",
        "missing_items": missing,
        "live_oauth_call_executed": False,
        "code_exchange_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "outbound_send_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(f"# Phase 5P OAuth Production Dry-Run Gate\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- live_oauth_call_executed: false\n- code_exchange_executed: false\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-live-oauth-callback", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(dry_run=args.dry_run, confirm_no_live_oauth_callback=args.confirm_no_live_oauth_callback)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
