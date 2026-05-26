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

from tools.run_phase5v_media_upload_live_staging_evidence import build_report as build_phase5v_staging_report


REQUIRED_ENV = {
    "AICRM_MEDIA_UPLOAD_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_MEDIA_UPLOAD_LIVE_UPLOAD_APPROVED": "not_executed_missing_live_upload_approval",
    "AICRM_MEDIA_UPLOAD_CONFIG_REVIEWED": "not_executed_missing_config_review",
    "AICRM_PHASE5V_MEDIA_UPLOAD_STAGING_LIVE_APPROVED": "not_executed_missing_phase5v_staging_live_approval",
    "AICRM_PHASE5W_MEDIA_UPLOAD_STAGING_CANARY_APPROVED": "not_executed_missing_staging_canary_approval",
    "AICRM_PHASE5W_MEDIA_UPLOAD_STAGING_TARGET_APPROVED": "not_executed_missing_target_approval",
}
CONFIG_ENV = {
    "AICRM_MEDIA_UPLOAD_PROVIDER_NAME": "not_executed_missing_provider_config",
    "AICRM_MEDIA_UPLOAD_PROVIDER_SECRET": "not_executed_missing_provider_config",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _redact(value: str) -> str:
    value = str(value or "")
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_provider_upload_executed": False,
        "production_upload_executed": False,
        "public_media_url_published": False,
        "raw_file_exposed": False,
        "destructive_delete_executed": False,
        "batch_upload_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "payment_executed": False,
        "oauth_callback_executed": False,
        "wecom_live_call_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def _blocked(status: str, args: argparse.Namespace) -> dict[str, Any]:
    safety = _side_effect_safety()
    return {
        "ok": False,
        "mode": "media_upload_staging_live_canary_evidence",
        "result_status": status,
        "live_provider_upload_executed": False,
        "production_upload_executed": False,
        "public_media_url_published": False,
        "destructive_delete_executed": False,
        "single_test_file_only": True,
        "file_name_redacted": _redact(args.file_name or ""),
        "content_type": args.content_type or "",
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _hash({"file_name": args.file_name or "", "content_type": args.content_type or "", "idempotency_key": args.idempotency_key or ""}),
        "cleanup_required": False,
        "cleanup_guidance": "cleanup requires separate explicit approval and same test file evidence",
        **safety,
        "side_effect_safety": safety,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            return _blocked(status, args)
    for env, status in CONFIG_ENV.items():
        if not os.getenv(env, "").strip():
            return _blocked(status, args)
    if not args.execute_staging_canary:
        return _blocked("not_executed_missing_execute_staging_canary", args)
    if not args.confirm_live_media_upload:
        return _blocked("not_executed_missing_confirm_live_media_upload", args)
    if not args.confirm_staging_only:
        return _blocked("not_executed_missing_confirm_staging_only", args)
    if not args.confirm_approved_test_file:
        return _blocked("not_executed_missing_confirm_approved_test_file", args)
    if not args.confirm_no_public_publish:
        return _blocked("not_executed_missing_confirm_no_public_publish", args)
    if not args.idempotency_key:
        return _blocked("not_executed_missing_idempotency_key", args)
    if not args.file_name:
        return _blocked("not_executed_missing_file_name", args)
    if "," in args.file_name:
        return _blocked("not_executed_batch_file_target_rejected", args)
    if not args.content_type:
        return _blocked("not_executed_missing_content_type", args)

    phase5v_args = argparse.Namespace(
        dry_run_live_gate=False,
        execute_live_staging=True,
        confirm_live_media_upload=True,
        confirm_staging_only=True,
        confirm_no_public_publish=True,
        idempotency_key=args.idempotency_key,
    )
    phase5v = build_phase5v_staging_report(phase5v_args)
    safety = _side_effect_safety()
    live_executed = bool(phase5v.get("live_provider_upload_executed"))
    return {
        "ok": bool(phase5v.get("ok")),
        "mode": "media_upload_staging_live_canary_evidence",
        "result_status": "staging_media_canary_completed" if phase5v.get("ok") else str(phase5v.get("result_status") or "blocked"),
        "live_provider_upload_executed": live_executed,
        "production_upload_executed": False,
        "public_media_url_published": False,
        "destructive_delete_executed": False,
        "single_test_file_only": True,
        "file_name_redacted": _redact(args.file_name),
        "content_type": args.content_type,
        "idempotency_key": args.idempotency_key,
        "request_hash": _hash({"file_name": args.file_name, "content_type": args.content_type, "idempotency_key": args.idempotency_key}),
        "cleanup_required": live_executed,
        "cleanup_guidance": "if a staging object was created, cleanup must use the same approved test file and separate cleanup approval",
        **safety,
        "side_effect_safety": {**safety, "live_provider_upload_executed": live_executed},
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5W Media Staging Canary Evidence\n\n" + "\n".join(f"- {key}: {report.get(key)}" for key in ("ok", "result_status", "live_provider_upload_executed", "public_media_url_published", "production_upload_executed")) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-staging-canary", action="store_true")
    parser.add_argument("--confirm-live-media-upload", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-approved-test-file", action="store_true")
    parser.add_argument("--confirm-no-public-publish", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--file-name")
    parser.add_argument("--content-type")
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
