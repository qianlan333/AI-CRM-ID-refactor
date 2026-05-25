#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from aicrm_next.integration_gateway.oauth_identity_live_adapter import build_live_oauth_identity_adapter

LIVE_ENV = {"AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED", "AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED", "AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED", "AICRM_OAUTH_IDENTITY_APP_ID", "AICRM_OAUTH_IDENTITY_APP_SECRET"}
STAGING_APPROVAL_ENV = "AICRM_PHASE5P_OAUTH_IDENTITY_STAGING_LIVE_APPROVED"


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    return bool(str(os.getenv(name, "") or "").strip())


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _base(mode: str, status: str, reason: str = "") -> dict[str, Any]:
    return {
        "ok": status == "ready_no_live_oauth_callback",
        "mode": mode,
        "result_status": status,
        "reason": reason,
        "live_oauth_call_executed": False,
        "live_callback_processed": False,
        "code_exchange_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "outbound_send_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "config_reviewed": _enabled("AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED"),
        "approval_present": _enabled("AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED") and _enabled(STAGING_APPROVAL_ENV),
        "request_hash": _hash({"mode": mode, "status": status}),
        "timestamp": _timestamp(),
    }


def _gate_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    for name in sorted(LIVE_ENV):
        if name in {"AICRM_OAUTH_IDENTITY_APP_ID", "AICRM_OAUTH_IDENTITY_APP_SECRET"}:
            if not _present(name):
                blockers.append(f"{name} is required")
        elif not _enabled(name):
            blockers.append(f"{name}=1 is required")
    if not _enabled(STAGING_APPROVAL_ENV):
        blockers.append(f"{STAGING_APPROVAL_ENV}=1 is required")
    if args.execute_live_staging and not args.confirm_live_oauth_callback:
        blockers.append("--confirm-live-oauth-callback is required")
    return blockers


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if not args.dry_run_live_gate and not args.execute_live_staging:
        return _base("blocked", "blocked_not_executed", "select --dry-run-live-gate or --execute-live-staging")
    blockers = _gate_blockers(args)
    mode = "dry_run_live_gate" if args.dry_run_live_gate else "execute_live_staging"
    if blockers:
        return _base(mode, "blocked_not_executed", "; ".join(blockers))
    if args.dry_run_live_gate:
        return _base(mode, "ready_no_live_oauth_callback")
    adapter = build_live_oauth_identity_adapter(confirm_live_oauth_callback=args.confirm_live_oauth_callback)
    result = adapter.exchange_code_live(code="phase5p_fake_code", state="phase5p_state", operator="phase5p_staging_runner", idempotency_key="phase5p-staging-live")
    report = _base(mode, str(result.get("result_status") or "blocked"), str(result.get("error_code") or ""))
    report["ok"] = bool(result.get("ok"))
    report["live_oauth_call_executed"] = bool(result.get("live_oauth_call_executed"))
    report["code_exchange_executed"] = bool(result.get("code_exchange_executed"))
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(f"# Phase 5P OAuth Live Staging Evidence\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- live_oauth_call_executed: {str(report.get('live_oauth_call_executed')).lower()}\n- code_exchange_executed: {str(report.get('code_exchange_executed')).lower()}\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run-live-gate", action="store_true")
    mode.add_argument("--execute-live-staging", action="store_true")
    parser.add_argument("--confirm-live-oauth-callback", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "FAIL", "ok": report.get("ok"), "status": report.get("result_status")}, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
