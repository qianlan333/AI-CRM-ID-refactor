#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


APPROVAL_ENV = "AICRM_PHASE5J_WECOM_CONTACT_PRODUCTION_DRY_RUN_APPROVED"
CONFIG_ENV = "AICRM_WECOM_CONTACT_CALLBACK_CONFIG_REVIEWED"


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_callback_processed": False,
        "production_write_executed": False,
        "production_contact_write_executed": False,
        "production_identity_mapping_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
        "customer_sync_executed": False,
        "token_used": False,
        "aes_key_used": False,
        "decrypt_executed": False,
        "network_call_executed": False,
        "db_write_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def build_report(*, dry_run: bool, confirm_no_live_callback: bool) -> dict[str, Any]:
    missing_items: list[str] = []
    if not _enabled(APPROVAL_ENV):
        missing_items.append("production_dry_run_approval")
    if not _enabled(CONFIG_ENV):
        missing_items.append("callback_config_review")
    if not dry_run:
        missing_items.append("dry_run_arg")
    if not confirm_no_live_callback:
        missing_items.append("confirm_no_live_callback")
    ok = not missing_items
    safety = _side_effect_safety()
    return {
        "ok": ok,
        "mode": "production_live_callback_dry_run_gate",
        "result_status": "ready_no_live_callback" if ok else "blocked_missing_required_gate",
        "missing_items": missing_items,
        "production_live_callback_processed": False,
        **safety,
        "side_effect_safety": safety,
        "request_hash": _request_hash({"mode": "production_live_callback_dry_run_gate", "dry_run": dry_run, "confirm_no_live_callback": confirm_no_live_callback}),
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5J WeCom Contact Live Callback Production Dry-Run Gate",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- missing_items: {', '.join(report.get('missing_items', []))}",
        f"- live_callback_processed: {str(report.get('live_callback_processed')).lower()}",
        f"- production_contact_write_executed: {str(report.get('production_contact_write_executed')).lower()}",
        f"- production_identity_mapping_write_executed: {str(report.get('production_identity_mapping_write_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5J production dry-run gate without live callback processing.")
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
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
