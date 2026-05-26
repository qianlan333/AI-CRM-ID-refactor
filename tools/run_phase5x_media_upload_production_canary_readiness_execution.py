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
    "AICRM_PHASE5X_MEDIA_UPLOAD_PRODUCTION_CANARY_APPROVED": "not_executed_missing_production_canary_approval",
    "AICRM_PHASE5X_MEDIA_UPLOAD_PRODUCTION_TARGET_APPROVED": "not_executed_missing_target_approval",
    "AICRM_PHASE5X_MEDIA_UPLOAD_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5X_MEDIA_UPLOAD_CLEANUP_STRATEGY_APPROVED": "not_executed_missing_cleanup_strategy",
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


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        value = json.loads(file_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _valid_staging_evidence(evidence: dict[str, Any] | None) -> bool:
    if not evidence:
        return False
    status = str(evidence.get("result_status") or "")
    if status.startswith("not_executed"):
        return False
    return (
        evidence.get("mode") == "media_upload_staging_live_canary_evidence"
        and evidence.get("production_upload_executed") is False
        and evidence.get("public_media_url_published") is False
        and evidence.get("destructive_delete_executed") is False
        and isinstance(evidence.get("side_effect_safety"), dict)
        and bool(evidence.get("file_name_redacted"))
    )


def _side_effect_safety() -> dict[str, bool]:
    return {
        "production_live_upload_executed": False,
        "public_media_url_published": False,
        "destructive_delete_executed": False,
        "raw_file_exposed": False,
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


def _redact(value: str) -> str:
    value = str(value or "")
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def _blocked(status: str, args: argparse.Namespace, evidence: dict[str, Any] | None = None) -> dict[str, Any]:
    safety = _side_effect_safety()
    return {
        "ok": False,
        "mode": "media_upload_production_canary_readiness_execution",
        "result_status": status,
        "ready_for_media_family_acceptance": False,
        "production_live_upload_executed": False,
        "public_media_url_published": False,
        "destructive_delete_executed": False,
        "target_count": 1 if args.file_name else 0,
        "file_name_redacted": _redact(args.file_name or ""),
        "content_type": args.content_type or "",
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _hash({"file_name": args.file_name or "", "content_type": args.content_type or "", "idempotency_key": args.idempotency_key or ""}),
        "staging_evidence_summary": {"result_status": (evidence or {}).get("result_status")},
        "rollback_required": False,
        "cleanup_runner": "tools/run_phase5x_media_upload_production_canary_cleanup.py",
        **safety,
        "side_effect_safety": safety,
        "timestamp": _timestamp(),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence = _load_json(args.staging_evidence_json)
    if evidence is None:
        return _blocked("not_executed_missing_staging_evidence", args)
    if not _valid_staging_evidence(evidence):
        return _blocked("not_executed_invalid_staging_evidence", args, evidence)
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            return _blocked(status, args, evidence)
    for env, status in CONFIG_ENV.items():
        if not os.getenv(env, "").strip():
            return _blocked(status, args, evidence)
    if not args.file_name:
        return _blocked("not_executed_missing_file_name", args, evidence)
    if "," in args.file_name:
        return _blocked("not_executed_batch_upload_rejected", args, evidence)
    if not args.content_type:
        return _blocked("not_executed_missing_content_type", args, evidence)
    if not args.idempotency_key:
        return _blocked("not_executed_missing_idempotency_key", args, evidence)
    if not args.confirm_production_live_media_upload:
        return _blocked("not_executed_missing_confirm_production_live_media_upload", args, evidence)
    if not args.confirm_single_approved_file:
        return _blocked("not_executed_missing_confirm_single_approved_file", args, evidence)
    if not args.confirm_no_public_publish:
        return _blocked("not_executed_missing_confirm_no_public_publish", args, evidence)
    if not args.confirm_no_delete:
        return _blocked("not_executed_missing_confirm_no_delete", args, evidence)
    if not args.confirm_rollback_owner_approved:
        return _blocked("not_executed_missing_confirm_rollback_owner", args, evidence)
    if not args.confirm_no_batch_upload:
        return _blocked("not_executed_missing_confirm_no_batch_upload", args, evidence)

    result = build_media_upload_live_adapter(confirm_live_media_upload=True).upload_media_live(
        data_base64="ZmFrZQ==",
        file_name=args.file_name,
        content_type=args.content_type,
        operator="phase5x_production_canary_runner",
        idempotency_key=args.idempotency_key,
    )
    live_executed = bool(result.get("live_provider_upload_executed"))
    safety = _side_effect_safety()
    return {
        "ok": bool(result.get("ok")),
        "mode": "media_upload_production_canary_readiness_execution",
        "result_status": "production_media_canary_completed" if result.get("ok") else str(result.get("result_status") or "blocked"),
        "ready_for_media_family_acceptance": True,
        "production_live_upload_executed": live_executed,
        "public_media_url_published": False,
        "destructive_delete_executed": False,
        "target_count": 1,
        "file_name_redacted": _redact(args.file_name),
        "content_type": args.content_type,
        "idempotency_key": args.idempotency_key,
        "request_hash": _hash({"file_name": args.file_name, "content_type": args.content_type, "idempotency_key": args.idempotency_key}),
        "staging_evidence_summary": {"result_status": evidence.get("result_status"), "file_name_redacted": evidence.get("file_name_redacted")},
        "rollback_required": live_executed,
        "cleanup_runner": "tools/run_phase5x_media_upload_production_canary_cleanup.py",
        **safety,
        "side_effect_safety": {**safety, "production_live_upload_executed": live_executed},
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5X Media Production Canary\n\n" + "\n".join(f"- {key}: {report.get(key)}" for key in ("ok", "result_status", "production_live_upload_executed", "public_media_url_published", "destructive_delete_executed")) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--file-name")
    parser.add_argument("--content-type")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-production-live-media-upload", action="store_true")
    parser.add_argument("--confirm-single-approved-file", action="store_true")
    parser.add_argument("--confirm-no-public-publish", action="store_true")
    parser.add_argument("--confirm-no-delete", action="store_true")
    parser.add_argument("--confirm-rollback-owner-approved", action="store_true")
    parser.add_argument("--confirm-no-batch-upload", action="store_true")
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
