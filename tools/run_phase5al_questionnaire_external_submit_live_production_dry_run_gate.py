#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip() == "1"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not _enabled("AICRM_PHASE5AL_QUESTIONNAIRE_PRODUCTION_DRY_RUN_APPROVED"):
        missing.append("not_executed_missing_production_dry_run_approval")
    if not _enabled("AICRM_QUESTIONNAIRE_EXTERNAL_SUBMIT_CONFIG_REVIEWED"):
        missing.append("not_executed_missing_config_review")
    if not args.dry_run:
        missing.append("not_executed_missing_dry_run")
    if not args.confirm_no_live_call:
        missing.append("not_executed_missing_confirm_no_live_call")
    if not args.confirm_no_production_write:
        missing.append("not_executed_missing_confirm_no_production_write")
    return {
        "ok": not missing,
        "mode": "questionnaire_external_submit_live_production_dry_run_gate",
        "result_status": "production_dry_run_gate_ready" if not missing else missing[0],
        "missing_items": missing,
        "live_call_executed": False,
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "live_oauth_callback_cutover_executed": False,
        "outbound_send_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": {"live_call_executed": False, "production_write_executed": False},
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "live_call_executed", "production_public_submit_write_executed")
    Path(path).write_text("# Phase 5AL Questionnaire Production Dry Run Gate\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-live-call", action="store_true")
    parser.add_argument("--confirm-no-production-write", action="store_true")
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
