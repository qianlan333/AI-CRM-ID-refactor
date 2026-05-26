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

from aicrm_next.questionnaire.external_submit_live_adapter import build_questionnaire_external_submit_live_adapter

REQUIRED_ENV = [
    "AICRM_QUESTIONNAIRE_EXTERNAL_SUBMIT_LIVE_ADAPTER_ENABLED",
    "AICRM_QUESTIONNAIRE_EXTERNAL_SUBMIT_LIVE_CALL_APPROVED",
    "AICRM_QUESTIONNAIRE_EXTERNAL_SUBMIT_CONFIG_REVIEWED",
    "AICRM_QUESTIONNAIRE_EXTERNAL_SUBMIT_TARGET_POLICY_REVIEWED",
    "AICRM_QUESTIONNAIRE_EXTERNAL_SUBMIT_NO_PRODUCTION_WRITE_CONFIRMED",
    "AICRM_PHASE5AL_QUESTIONNAIRE_STAGING_LIVE_APPROVED",
]


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "")).strip() == "1"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    if not args.dry_run_live_gate and not args.execute_staging_live:
        missing.append("not_executed_missing_execution_mode")
    if args.execute_staging_live:
        for env in REQUIRED_ENV:
            if not _enabled(env):
                missing.append(f"not_executed_missing_{env.lower()}")
        for attr, status in (
            ("confirm_live_call", "not_executed_missing_confirm_live_call"),
            ("confirm_staging_only", "not_executed_missing_confirm_staging_only"),
            ("confirm_no_production_write", "not_executed_missing_confirm_no_production_write"),
            ("confirm_no_outbound_send", "not_executed_missing_confirm_no_outbound_send"),
        ):
            if not getattr(args, attr):
                missing.append(status)
        if not args.idempotency_key:
            missing.append("not_executed_missing_idempotency_key")
        if not args.slug:
            missing.append("not_executed_missing_slug")
    if missing:
        return _blocked(missing[0], missing)
    adapter = build_questionnaire_external_submit_live_adapter(confirm_no_production_write=args.confirm_no_production_write, confirm_no_outbound_send=args.confirm_no_outbound_send)
    result = adapter.submit_public_live(slug=args.slug or "phase5al-staging", payload={"external_userid": "redacted-only"}, operator="phase5al_staging", idempotency_key=args.idempotency_key or "dry-run")
    return {**result, "mode": "questionnaire_external_submit_live_staging_evidence", "production_behavior_changed": False, "production_compat_changed": False, "fallback_removed": False}


def _blocked(status: str, missing: list[str]) -> dict[str, Any]:
    return {
        "ok": False,
        "mode": "questionnaire_external_submit_live_staging_evidence",
        "result_status": status,
        "missing_items": missing,
        "provider_call_executed": False,
        "production_public_submit_write_executed": False,
        "production_identity_write_executed": False,
        "production_tag_write_executed": False,
        "live_oauth_callback_cutover_executed": False,
        "outbound_send_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": {"production_write_allowed": False, "outbound_send_allowed": False},
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    keys = ("ok", "result_status", "production_public_submit_write_executed", "production_identity_write_executed", "production_tag_write_executed")
    Path(path).write_text("# Phase 5AL Questionnaire Staging Evidence\n\n" + "\n".join(f"- {key}: {report[key]}" for key in keys) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-live-gate", action="store_true")
    parser.add_argument("--execute-staging-live", action="store_true")
    parser.add_argument("--confirm-live-call", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-no-production-write", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--slug")
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
