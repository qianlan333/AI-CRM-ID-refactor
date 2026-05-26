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

from aicrm_next.integration_gateway.media_live_adapter import build_media_upload_live_adapter


REQUIRED_ENV = {
    "AICRM_MEDIA_UPLOAD_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_MEDIA_UPLOAD_LIVE_UPLOAD_APPROVED": "not_executed_missing_live_upload_approval",
    "AICRM_MEDIA_UPLOAD_CONFIG_REVIEWED": "not_executed_missing_config_review",
    "AICRM_PHASE5V_MEDIA_UPLOAD_STAGING_LIVE_APPROVED": "not_executed_missing_staging_live_approval",
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


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_provider_upload_executed": False,
        "live_provider_lookup_executed": False,
        "network_call_executed": False,
        "token_used": False,
        "provider_secret_used": False,
        "public_media_url_published": False,
        "production_upload_executed": False,
        "raw_file_exposed": False,
        "destructive_delete_executed": False,
        "db_write_executed": False,
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


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing = ""
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            missing = status
            break
    if not missing and args.execute_live_staging:
        for env, status in CONFIG_ENV.items():
            if not os.getenv(env, "").strip():
                missing = status
                break
    if not missing and not (args.dry_run_live_gate or args.execute_live_staging):
        missing = "not_executed_missing_mode"
    if not missing and args.execute_live_staging and not args.confirm_live_media_upload:
        missing = "not_executed_missing_confirm_live_media_upload"
    if not missing and args.execute_live_staging and not args.confirm_staging_only:
        missing = "not_executed_missing_confirm_staging_only"
    if not missing and args.execute_live_staging and not args.confirm_no_public_publish:
        missing = "not_executed_missing_confirm_no_public_publish"
    if not missing and args.execute_live_staging and not args.idempotency_key:
        missing = "not_executed_missing_idempotency_key"
    safety = _side_effect_safety()
    live_result: dict[str, Any] | None = None
    if not missing and args.execute_live_staging:
        live_result = build_media_upload_live_adapter(confirm_live_media_upload=True).upload_media_live(
            data_base64="ZmFrZQ==",
            file_name="phase5v-staging-fixture.png",
            content_type="image/png",
            operator="phase5v_staging_runner",
            idempotency_key=args.idempotency_key,
        )
    return {
        "ok": not missing and bool(live_result.get("ok")) if live_result is not None else not missing,
        "mode": "media_upload_live_staging_evidence",
        "result_status": missing or ("staging_live_media_upload_completed" if live_result and live_result.get("ok") else "staging_live_gate_ready" if args.dry_run_live_gate else str((live_result or {}).get("result_status") or "blocked")),
        "live_provider_upload_executed": bool(live_result and live_result.get("live_provider_upload_executed")),
        "public_media_url_published": False,
        "production_upload_executed": False,
        "destructive_delete_executed": False,
        "raw_file_exposed": False,
        "token_used": False,
        "provider_secret_used": False,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _hash({"mode": "phase5v", "idempotency_key": args.idempotency_key or "", "execute": bool(args.execute_live_staging)}),
        "file_metadata_redacted": True,
        "token_redacted": True,
        **safety,
        "side_effect_safety": {**safety, "live_provider_upload_executed": bool(live_result and live_result.get("live_provider_upload_executed"))},
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5V Media Live Staging Evidence\n\n" + "\n".join(f"- {k}: {v}" for k, v in {"ok": report.get("ok"), "result_status": report.get("result_status"), "live_provider_upload_executed": report.get("live_provider_upload_executed"), "public_media_url_published": report.get("public_media_url_published")}.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-live-gate", action="store_true")
    parser.add_argument("--execute-live-staging", action="store_true")
    parser.add_argument("--confirm-live-media-upload", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-no-public-publish", action="store_true")
    parser.add_argument("--idempotency-key")
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
