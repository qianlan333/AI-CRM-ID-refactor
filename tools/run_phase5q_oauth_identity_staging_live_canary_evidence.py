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

from tools import run_phase5p_oauth_identity_live_staging_evidence as phase5p_staging


FLAG_ENV = {
    "AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED": "not_executed_missing_live_callback_approval",
    "AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED": "not_executed_missing_config_review",
    "AICRM_PHASE5Q_OAUTH_IDENTITY_STAGING_CANARY_APPROVED": "not_executed_missing_staging_canary_approval",
    "AICRM_PHASE5Q_OAUTH_IDENTITY_STAGING_TARGET_APPROVED": "not_executed_missing_target_approval",
}
CONFIG_ENV = {
    "AICRM_OAUTH_IDENTITY_APP_ID": "not_executed_missing_config_review",
    "AICRM_OAUTH_IDENTITY_APP_SECRET": "not_executed_missing_config_review",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    return bool(str(os.getenv(name, "") or "").strip())


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redact(value: str, *, label: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return f"{label}_***"
    return f"{value[:3]}***{value[-3:]}"


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety(*, live_oauth_call_executed: bool = False, code_exchange_executed: bool = False) -> dict[str, bool]:
    return {
        "live_oauth_call_executed": live_oauth_call_executed,
        "code_exchange_executed": code_exchange_executed,
        "production_callback_cutover_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "token_persisted": False,
        "db_write_executed": False,
        "wecom_live_call_executed": False,
        "payment_executed": False,
        "media_upload_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def _selected_code(args: argparse.Namespace) -> str:
    return str(args.code or args.fake_safe_code or "").strip()


def _base_report(args: argparse.Namespace, *, result_status: str, reason: str = "", phase5p_report: dict[str, Any] | None = None) -> dict[str, Any]:
    live_oauth_call_executed = bool(phase5p_report and phase5p_report.get("live_oauth_call_executed"))
    code_exchange_executed = bool(phase5p_report and phase5p_report.get("code_exchange_executed"))
    safety = _side_effect_safety(live_oauth_call_executed=live_oauth_call_executed, code_exchange_executed=code_exchange_executed)
    state = str(args.state or "")
    code = _selected_code(args)
    request_payload = {
        "runner": "phase5q_oauth_identity_staging_live_canary",
        "redacted_state": _redact(state, label="state"),
        "redacted_code": _redact(code, label="code"),
        "idempotency_key": args.idempotency_key or "",
        "execute_staging_canary": bool(args.execute_staging_canary),
    }
    report: dict[str, Any] = {
        "ok": not result_status.startswith("not_executed_"),
        "mode": "oauth_identity_staging_live_canary_evidence",
        "result_status": result_status,
        "reason": reason,
        **safety,
        "config_reviewed": _enabled("AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED"),
        "approval_present": _enabled("AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED") and _enabled("AICRM_PHASE5Q_OAUTH_IDENTITY_STAGING_CANARY_APPROVED"),
        "target_approval_present": _enabled("AICRM_PHASE5Q_OAUTH_IDENTITY_STAGING_TARGET_APPROVED"),
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _request_hash(request_payload),
        "redacted_state": _redact(state, label="state"),
        "redacted_code": _redact(code, label="code"),
        "token_redacted": True,
        "cleanup_required": False,
        "cleanup_rollback_guidance": {
            "cleanup_requires_separate_approval": True,
            "production_cleanup_executed": False,
            "token_persistence_enabled": False,
            "scope": "staging_only_single_callback_attempt",
        },
        "side_effect_safety": safety,
        "timestamp": _timestamp(),
    }
    if phase5p_report is not None:
        report["phase5p_staging_evidence_summary"] = {
            "ok": bool(phase5p_report.get("ok")),
            "mode": phase5p_report.get("mode") or "",
            "result_status": phase5p_report.get("result_status") or "",
            "live_oauth_call_executed": bool(phase5p_report.get("live_oauth_call_executed")),
            "code_exchange_executed": bool(phase5p_report.get("code_exchange_executed")),
        }
        report["ok"] = bool(phase5p_report.get("ok"))
    return report


def _first_blocker(args: argparse.Namespace) -> tuple[str, str] | None:
    for name, status in FLAG_ENV.items():
        if not _enabled(name):
            return status, f"{name}=1 is required"
    for name, status in CONFIG_ENV.items():
        if not _present(name):
            return status, f"{name} is required"
    if not args.execute_staging_canary:
        return "not_executed_missing_execute_staging_canary", "--execute-staging-canary is required"
    code = _selected_code(args)
    if not code:
        return "not_executed_missing_code_or_safe_code", "--code or --fake-safe-code is required"
    if not str(args.state or "").strip():
        return "not_executed_missing_state", "--state is required"
    if not str(args.idempotency_key or "").strip():
        return "not_executed_missing_idempotency_key", "--idempotency-key is required"
    if not args.confirm_live_oauth_call:
        return "not_executed_missing_confirm_live_oauth_call", "--confirm-live-oauth-call is required"
    if not args.confirm_staging_only:
        return "not_executed_missing_confirm_staging_only", "--confirm-staging-only is required"
    if not args.confirm_approved_target:
        return "not_executed_missing_confirm_approved_target", "--confirm-approved-target is required"
    callback_url = str(args.callback_url or "").strip().lower()
    if callback_url and "staging" not in callback_url and "localhost" not in callback_url and "127.0.0.1" not in callback_url:
        return "not_executed_production_callback_url_forbidden", "production callback URL is forbidden"
    if "," in code or "," in str(args.state or ""):
        return "not_executed_batch_replay_rejected", "batch replay is not allowed"
    raw_payload = json.dumps({"state": args.state or "", "code": code, "callback_url": args.callback_url or ""}, ensure_ascii=False).lower()
    if "access_token" in raw_payload or "refresh_token" in raw_payload or "app_secret=" in raw_payload:
        return "not_executed_secret_or_token_leak_risk", "secret or token-like input is forbidden"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    blocker = _first_blocker(args)
    if blocker:
        status, reason = blocker
        return _base_report(args, result_status=status, reason=reason)
    phase5p_args = argparse.Namespace(dry_run_live_gate=False, execute_live_staging=True, confirm_live_oauth_callback=True, output_json=None, output_md=None)
    phase5p_report = phase5p_staging.build_report(phase5p_args)
    status = "staging_live_oauth_canary_evidence_completed" if phase5p_report.get("live_oauth_call_executed") else "staging_canary_phase5p_blocked"
    return _base_report(args, result_status=status, reason=str(phase5p_report.get("reason") or ""), phase5p_report=phase5p_report)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5Q OAuth Identity Staging Live Canary Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- live_oauth_call_executed: {str(report.get('live_oauth_call_executed')).lower()}",
        f"- production_callback_cutover_executed: {str(report.get('production_callback_cutover_executed')).lower()}",
        f"- production_session_write_executed: {str(report.get('production_session_write_executed')).lower()}",
        f"- production_identity_write_executed: {str(report.get('production_identity_write_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- redacted_state: {report.get('redacted_state') or 'none'}",
        f"- redacted_code: {report.get('redacted_code') or 'none'}",
        f"- token_redacted: {str(report.get('token_redacted')).lower()}",
        f"- reason: {report.get('reason') or 'none'}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5Q OAuth identity staging live canary evidence.")
    parser.add_argument("--execute-staging-canary", action="store_true")
    parser.add_argument("--confirm-live-oauth-call", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-approved-target", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--state")
    code_group = parser.add_mutually_exclusive_group()
    code_group.add_argument("--code")
    code_group.add_argument("--fake-safe-code")
    parser.add_argument("--callback-url")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
