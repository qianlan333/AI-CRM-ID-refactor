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

from aicrm_next.integration_gateway.wecom_contact_callback_adapter import DETERMINISTIC_EVENTS
from aicrm_next.integration_gateway.wecom_contact_callback_application import (
    build_wecom_contact_callback_application_service,
    reset_wecom_contact_callback_fake_stub_state,
)


APPROVAL_ENV = "AICRM_PHASE5I_WECOM_CONTACT_PRODUCTION_DRY_RUN_APPROVED"
CONFIG_ENV = "AICRM_PHASE5I_WECOM_CONTACT_PRODUCTION_CONFIG_REVIEWED"


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_callback_cutover_allowed": False,
        "production_contact_write_allowed": False,
        "production_identity_mapping_write_allowed": False,
        "production_tag_write_allowed": False,
        "live_customer_sync_allowed": False,
        "outbound_send_allowed": False,
        "token_refresh_allowed": False,
        "decrypt_allowed": False,
        "network_call_allowed": False,
        "db_write_allowed": False,
    }


def build_report(*, dry_run: bool, confirm_no_live_callback: bool) -> dict[str, Any]:
    approval_present = os.getenv(APPROVAL_ENV) == "1"
    config_reviewed = os.getenv(CONFIG_ENV) == "1"
    missing_items: list[str] = []
    if not approval_present:
        missing_items.append("production_dry_run_approval")
    if not config_reviewed:
        missing_items.append("production_config_review")
    if not dry_run:
        missing_items.append("dry_run_arg")
    if not confirm_no_live_callback:
        missing_items.append("confirm_no_live_callback")

    ok = not missing_items
    report: dict[str, Any] = {
        "ok": ok,
        "mode": "production_fake_stub_dry_run",
        "result_status": "production_fake_stub_dry_run_evidence" if ok else "blocked_missing_required_gate",
        "missing_items": missing_items,
        "approval_present": approval_present,
        "config_reviewed": config_reviewed,
        "dry_run": dry_run,
        "confirm_no_live_callback": confirm_no_live_callback,
        "live_callback_processed": False,
        "production_write_executed": False,
        "production_contact_write_executed": False,
        "production_identity_mapping_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "aes_key_used": False,
        "decrypt_executed": False,
        "network_call_executed": False,
        "db_write_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": _side_effect_safety(),
    }
    if not ok:
        return report

    reset_wecom_contact_callback_fake_stub_state()
    service = build_wecom_contact_callback_application_service()
    event = DETERMINISTIC_EVENTS[0]
    report["dry_run_record_contact_event"] = service.dry_run_record_contact_event(
        event=event,
        operator="phase5i_production_fake_stub_dry_run",
        idempotency_key="phase5i-production-dry-run-record",
    )
    report["dry_run_identity_mapping"] = service.dry_run_identity_mapping(
        event=DETERMINISTIC_EVENTS[1],
        operator="phase5i_production_fake_stub_dry_run",
        idempotency_key="phase5i-production-dry-run-identity",
    )
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5I WeCom Customer Contact Fake/Stub Production Dry-Run",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- missing_items: {', '.join(report.get('missing_items', []))}",
        f"- live_callback_processed: {str(report.get('live_callback_processed')).lower()}",
        f"- production_contact_write_executed: {str(report.get('production_contact_write_executed')).lower()}",
        f"- production_identity_mapping_write_executed: {str(report.get('production_identity_mapping_write_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- token_used: {str(report.get('token_used')).lower()}",
        f"- aes_key_used: {str(report.get('aes_key_used')).lower()}",
        f"- network_call_executed: {str(report.get('network_call_executed')).lower()}",
        f"- db_write_executed: {str(report.get('db_write_executed')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5I fake/stub production dry-run evidence for WeCom contact callback.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--confirm-no-live-callback", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    report = build_report(dry_run=args.dry_run, confirm_no_live_callback=args.confirm_no_live_callback)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "result_status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
