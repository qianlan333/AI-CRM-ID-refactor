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

from tools import run_phase5c_wecom_tag_live_staging_evidence as phase5c_staging


FLAG_ENV = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED": "not_executed_missing_live_call_approval",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED": "not_executed_missing_config_review",
    "AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_APPROVED": "not_executed_missing_staging_canary_approval",
    "AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_TARGET_APPROVED": "not_executed_missing_target_approval",
}
SECRET_ENV = {
    "AICRM_WECOM_TAG_CORP_ID": "not_executed_missing_config_review",
    "AICRM_WECOM_TAG_AGENT_SECRET": "not_executed_missing_config_review",
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


def _side_effect_safety(*, live_call_executed: bool = False, network_call_executed: bool = False, token_used: bool = False) -> dict[str, bool]:
    return {
        "live_call_executed": live_call_executed,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
        "outbound_send_executed": False,
        "token_used": token_used,
        "network_call_executed": network_call_executed,
        "oauth_callback_executed": False,
        "payment_executed": False,
        "media_upload_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _target_values(args: argparse.Namespace) -> tuple[str, list[str]]:
    return (args.external_userid or "").strip(), [tag.strip() for tag in args.tag_id or [] if tag.strip()]


def _base_report(args: argparse.Namespace, *, result_status: str, reason: str = "", phase5c_report: dict[str, Any] | None = None) -> dict[str, Any]:
    external_userid, tag_ids = _target_values(args)
    live_call_executed = bool(phase5c_report and phase5c_report.get("live_call_executed"))
    safety = _side_effect_safety(
        live_call_executed=live_call_executed,
        network_call_executed=bool(phase5c_report and phase5c_report.get("network_call_executed")),
        token_used=bool(phase5c_report and phase5c_report.get("token_used")),
    )
    request_payload = {
        "runner": "phase5d_staging_live_canary",
        "external_userid_redacted": _redact_external_userid(external_userid),
        "tag_ids": tag_ids,
        "idempotency_key": args.idempotency_key or "",
        "execute_staging_canary": bool(args.execute_staging_canary),
    }
    report: dict[str, Any] = {
        "ok": True,
        "mode": "phase5d_staging_live_canary",
        "result_status": result_status,
        "reason": reason,
        "live_call_executed": safety["live_call_executed"],
        "mark_tag_executed": safety["mark_tag_executed"],
        "unmark_tag_executed": safety["unmark_tag_executed"],
        "outbound_send_executed": safety["outbound_send_executed"],
        "token_used": safety["token_used"],
        "network_call_executed": safety["network_call_executed"],
        "config_reviewed": _enabled("AICRM_WECOM_TAG_CONFIG_REVIEWED"),
        "approval_present": _enabled("AICRM_WECOM_TAG_LIVE_CALL_APPROVED") and _enabled("AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_APPROVED"),
        "target_approval_present": _enabled("AICRM_PHASE5D_WECOM_TAG_STAGING_CANARY_TARGET_APPROVED"),
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _request_hash(request_payload),
        "external_userid_redacted": _redact_external_userid(external_userid),
        "requested_tag_ids": tag_ids,
        "normalized_tag_ids": tag_ids,
        "side_effect_safety": safety,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "cleanup_rollback_guidance": {
            "cleanup_requires_explicit_approval": True,
            "cleanup_runner_in_this_bundle": False,
            "automatic_cleanup_executed": False,
            "scope": "staging_only",
            "recommended_cleanup_shape": "separate approved Phase 5C guarded unmark evidence",
        },
        "timestamp": _timestamp(),
    }
    if phase5c_report is not None:
        report["phase5c_staging_evidence_summary"] = {
            "ok": bool(phase5c_report.get("ok")),
            "mode": phase5c_report.get("mode") or "",
            "result_status": phase5c_report.get("result_status") or "",
            "live_call_executed": bool(phase5c_report.get("live_call_executed")),
            "mark_tag_executed": bool(phase5c_report.get("mark_tag_executed")),
            "unmark_tag_executed": bool(phase5c_report.get("unmark_tag_executed")),
        }
        report["ok"] = bool(phase5c_report.get("ok"))
    return report


def _blocked(args: argparse.Namespace, status: str, reason: str) -> dict[str, Any]:
    return _base_report(args, result_status=status, reason=reason)


def _first_blocker(args: argparse.Namespace) -> tuple[str, str] | None:
    for name, status in FLAG_ENV.items():
        if not _enabled(name):
            return status, f"{name}=1 is required"
    for name, status in SECRET_ENV.items():
        if not _present(name):
            return status, f"{name} is required"
    external_userid, tag_ids = _target_values(args)
    if not args.execute_staging_canary:
        return "not_executed_missing_execute_staging_canary", "--execute-staging-canary is required"
    if not external_userid:
        return "not_executed_missing_external_userid", "--external-userid is required"
    if "," in external_userid or len(external_userid.split()) > 1:
        return "not_executed_batch_target_rejected", "only one external_userid is allowed"
    if not tag_ids:
        return "not_executed_missing_tag_id", "--tag-id is required"
    if len(tag_ids) != 1:
        return "not_executed_batch_target_rejected", "batch tag targets are rejected by default"
    if not (args.idempotency_key or "").strip():
        return "not_executed_missing_idempotency_key", "--idempotency-key is required"
    if not args.confirm_live_wecom_call:
        return "not_executed_missing_confirm_live_call", "--confirm-live-wecom-call is required"
    if not args.confirm_staging_only:
        return "not_executed_missing_confirm_staging_only", "--confirm-staging-only is required"
    if not args.confirm_approved_target:
        return "not_executed_missing_confirm_approved_target", "--confirm-approved-target is required"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    blocker = _first_blocker(args)
    if blocker:
        status, reason = blocker
        return _blocked(args, status, reason)

    phase5c_args = argparse.Namespace(
        dry_run_live_gate=False,
        execute_live_staging=True,
        confirm_live_wecom_call=True,
        output_json=None,
        output_md=None,
    )
    phase5c_report = phase5c_staging.build_report(phase5c_args)
    status = "staging_canary_live_evidence_completed" if phase5c_report.get("live_call_executed") else "staging_canary_phase5c_blocked"
    reason = str(phase5c_report.get("reason") or "")
    return _base_report(args, result_status=status, reason=reason, phase5c_report=phase5c_report)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5D WeCom Tag Staging Live Canary Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- live_call_executed: {str(report.get('live_call_executed')).lower()}",
        f"- mark_tag_executed: {str(report.get('mark_tag_executed')).lower()}",
        f"- unmark_tag_executed: {str(report.get('unmark_tag_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- network_call_executed: {str(report.get('network_call_executed')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- external_userid_redacted: {report.get('external_userid_redacted') or 'none'}",
        f"- requested_tag_ids: {', '.join(report.get('requested_tag_ids') or []) or 'none'}",
        f"- reason: {report.get('reason') or 'none'}",
        "",
        "## Cleanup / Rollback",
        "",
        "- cleanup_requires_explicit_approval: true",
        "- automatic_cleanup_executed: false",
        "- scope: staging_only",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5D WeCom tag staging live canary evidence gate.")
    parser.add_argument("--execute-staging-canary", action="store_true")
    parser.add_argument("--confirm-live-wecom-call", action="store_true")
    parser.add_argument("--confirm-staging-only", action="store_true")
    parser.add_argument("--confirm-approved-target", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--external-userid")
    parser.add_argument("--tag-id", action="append")
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
