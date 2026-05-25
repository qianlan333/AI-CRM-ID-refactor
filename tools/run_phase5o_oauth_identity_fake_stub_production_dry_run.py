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

from aicrm_next.integration_gateway.oauth_identity_adapter import DETERMINISTIC_OAUTH_EVENTS
from aicrm_next.integration_gateway.oauth_identity_application import build_oauth_identity_application_service, reset_oauth_identity_fake_stub_state

APPROVAL_ENV = "AICRM_PHASE5O_OAUTH_IDENTITY_PRODUCTION_DRY_RUN_APPROVED"
CONFIG_ENV = "AICRM_PHASE5O_OAUTH_IDENTITY_PRODUCTION_CONFIG_REVIEWED"


def build_report(*, dry_run: bool, confirm_no_live_oauth_callback: bool) -> dict[str, Any]:
    missing_items: list[str] = []
    if os.getenv(APPROVAL_ENV) != "1":
        missing_items.append("production_dry_run_approval")
    if os.getenv(CONFIG_ENV) != "1":
        missing_items.append("production_config_review")
    if not dry_run:
        missing_items.append("dry_run_arg")
    if not confirm_no_live_oauth_callback:
        missing_items.append("confirm_no_live_oauth_callback")
    ok = not missing_items
    report: dict[str, Any] = {
        "ok": ok,
        "mode": "production_fake_stub_dry_run",
        "result_status": "production_fake_stub_dry_run_evidence" if ok else "blocked_missing_required_gate",
        "missing_items": missing_items,
        "live_oauth_call_executed": False,
        "live_callback_processed": False,
        "code_exchange_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "network_call_executed": False,
        "db_write_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }
    if not ok:
        return report
    reset_oauth_identity_fake_stub_state()
    service = build_oauth_identity_application_service()
    report["dry_run_record_oauth_identity"] = service.dry_run_record_oauth_identity(event=DETERMINISTIC_OAUTH_EVENTS[0], operator="phase5o_production_fake_stub_dry_run", idempotency_key="phase5o-production-record")
    report["dry_run_session_identity_evidence"] = service.dry_run_session_identity_evidence(event=DETERMINISTIC_OAUTH_EVENTS[1], operator="phase5o_production_fake_stub_dry_run", idempotency_key="phase5o-production-session")
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(f"# Phase 5O OAuth Identity Fake/Stub Production Dry-Run\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- missing_items: {', '.join(report.get('missing_items', []))}\n- live_oauth_call_executed: false\n- production_session_write_executed: false\n- production_identity_write_executed: false\n", encoding="utf-8")


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
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "result_status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
