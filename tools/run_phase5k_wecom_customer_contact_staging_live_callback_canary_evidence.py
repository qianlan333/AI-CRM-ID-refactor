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

from tools import run_phase5j_wecom_customer_contact_live_callback_staging_evidence as phase5j_staging


FLAG_ENV = {
    "AICRM_WECOM_CONTACT_CALLBACK_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_WECOM_CONTACT_CALLBACK_LIVE_PROCESSING_APPROVED": "not_executed_missing_live_callback_approval",
    "AICRM_WECOM_CONTACT_CALLBACK_CONFIG_REVIEWED": "not_executed_missing_config_review",
    "AICRM_PHASE5K_WECOM_CONTACT_STAGING_CANARY_APPROVED": "not_executed_missing_staging_canary_approval",
    "AICRM_PHASE5K_WECOM_CONTACT_STAGING_CANARY_TARGET_APPROVED": "not_executed_missing_target_approval",
}
SECRET_ENV = {
    "AICRM_WECOM_CONTACT_CALLBACK_CORP_ID": "not_executed_missing_config_review",
    "AICRM_WECOM_CONTACT_CALLBACK_TOKEN": "not_executed_missing_config_review",
    "AICRM_WECOM_CONTACT_CALLBACK_AES_KEY": "not_executed_missing_config_review",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    return bool(str(os.getenv(name, "") or "").strip())


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _redact_external_userid(value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "ext_***"
    return f"{value[:4]}***{value[-4:]}"


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety(*, live_callback_processed: bool = False, decrypt_executed: bool = False) -> dict[str, bool]:
    return {
        "live_callback_processed": live_callback_processed,
        "production_write_executed": False,
        "production_contact_write_executed": False,
        "production_identity_mapping_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
        "customer_sync_executed": False,
        "token_used": decrypt_executed,
        "aes_key_used": decrypt_executed,
        "decrypt_executed": decrypt_executed,
        "network_call_executed": False,
        "db_write_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "oauth_callback_executed": False,
        "payment_executed": False,
        "media_upload_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def _base_report(args: argparse.Namespace, *, result_status: str, reason: str = "", phase5j_report: dict[str, Any] | None = None) -> dict[str, Any]:
    live_callback_processed = bool(phase5j_report and phase5j_report.get("live_callback_processed"))
    decrypt_executed = bool(phase5j_report and phase5j_report.get("decrypt_executed"))
    safety = _side_effect_safety(live_callback_processed=live_callback_processed, decrypt_executed=decrypt_executed)
    external_userid = (args.external_userid or "").strip()
    request_payload = {
        "runner": "phase5k_contact_staging_live_callback_canary",
        "external_userid_redacted": _redact_external_userid(external_userid),
        "event_key": args.event_key or "",
        "idempotency_key": args.idempotency_key or "",
        "execute_staging_canary": bool(args.execute_staging_canary),
    }
    report: dict[str, Any] = {
        "ok": True,
        "mode": "phase5k_staging_live_callback_canary",
        "result_status": result_status,
        "reason": reason,
        **safety,
        "config_reviewed": _enabled("AICRM_WECOM_CONTACT_CALLBACK_CONFIG_REVIEWED"),
        "approval_present": _enabled("AICRM_WECOM_CONTACT_CALLBACK_LIVE_PROCESSING_APPROVED") and _enabled("AICRM_PHASE5K_WECOM_CONTACT_STAGING_CANARY_APPROVED"),
        "target_approval_present": _enabled("AICRM_PHASE5K_WECOM_CONTACT_STAGING_CANARY_TARGET_APPROVED"),
        "external_userid_redacted": _redact_external_userid(external_userid),
        "event_key": args.event_key or "",
        "change_type": args.change_type or "",
        "idempotency_key": args.idempotency_key or "",
        "target_count": 1 if external_userid else 0,
        "event_count": 1 if args.event_key else 0,
        "request_hash": _request_hash(request_payload),
        "side_effect_safety": safety,
        "cleanup_rollback_guidance": {
            "cleanup_requires_explicit_approval": True,
            "automatic_cleanup_executed": False,
            "scope": "staging_only_same_event_and_target",
        },
        "timestamp": _timestamp(),
    }
    if phase5j_report is not None:
        report["phase5j_staging_evidence_summary"] = {
            "ok": bool(phase5j_report.get("ok")),
            "mode": phase5j_report.get("mode") or "",
            "result_status": phase5j_report.get("result_status") or "",
            "live_callback_processed": bool(phase5j_report.get("live_callback_processed")),
        }
        report["ok"] = bool(phase5j_report.get("ok"))
    return report


def _first_blocker(args: argparse.Namespace) -> tuple[str, str] | None:
    for name, status in FLAG_ENV.items():
        if not _enabled(name):
            return status, f"{name}=1 is required"
    for name, status in SECRET_ENV.items():
        if not _present(name):
            return status, f"{name} is required"
    external_userid = (args.external_userid or "").strip()
    if not args.execute_staging_canary:
        return "not_executed_missing_execute_staging_canary", "--execute-staging-canary is required"
    if not external_userid:
        return "not_executed_missing_external_userid", "--external-userid is required"
    if "," in external_userid or len(external_userid.split()) > 1:
        return "not_executed_batch_target_rejected", "only one external_userid is allowed"
    if not (args.event_key or "").strip():
        return "not_executed_missing_event_key", "--event-key is required"
    if "," in (args.event_key or ""):
        return "not_executed_batch_event_rejected", "only one event_key is allowed"
    if not (args.idempotency_key or "").strip():
        return "not_executed_missing_idempotency_key", "--idempotency-key is required"
    if not args.confirm_live_wecom_callback:
        return "not_executed_missing_confirm_live_callback", "--confirm-live-wecom-callback is required"
    if not args.confirm_staging_only:
        return "not_executed_missing_confirm_staging_only", "--confirm-staging-only is required"
    if not args.confirm_approved_event:
        return "not_executed_missing_confirm_approved_event", "--confirm-approved-event is required"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    blocker = _first_blocker(args)
    if blocker:
        status, reason = blocker
        return _base_report(args, result_status=status, reason=reason)
    phase5j_args = argparse.Namespace(dry_run_live_gate=False, execute_live_staging=True, confirm_live_wecom_callback=True, output_json=None, output_md=None)
    phase5j_report = phase5j_staging.build_report(phase5j_args)
    status = "staging_live_callback_canary_evidence_completed" if phase5j_report.get("live_callback_processed") else "staging_canary_phase5j_blocked"
    return _base_report(args, result_status=status, reason=str(phase5j_report.get("reason") or ""), phase5j_report=phase5j_report)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5K WeCom Contact Staging Live Callback Canary Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- live_callback_processed: {str(report.get('live_callback_processed')).lower()}",
        f"- production_contact_write_executed: {str(report.get('production_contact_write_executed')).lower()}",
        f"- production_identity_mapping_write_executed: {str(report.get('production_identity_mapping_write_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- external_userid_redacted: {report.get('external_userid_redacted') or 'none'}",
        f"- event_key: {report.get('event_key') or 'none'}",
        f"- reason: {report.get('reason') or 'none'}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5K WeCom contact staging live callback canary evidence.")
    parser.add_argument("--execute-staging-canary", action="store_true")
    parser.add_argument("--confirm-live-wecom-callback", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-approved-event", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--external-userid")
    parser.add_argument("--event-key")
    parser.add_argument("--change-type", default="add_external_contact")
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
