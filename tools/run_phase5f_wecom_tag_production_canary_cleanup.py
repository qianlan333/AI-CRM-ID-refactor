#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.customer_tags.wecom_tag_live_adapter import build_live_wecom_tag_adapter


REQUIRED_ENV = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED": "not_executed_missing_cleanup_approval",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED": "not_executed_missing_cleanup_approval",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED": "not_executed_missing_cleanup_approval",
    "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_CLEANUP_APPROVED": "not_executed_missing_cleanup_approval",
    "AICRM_PHASE5F_WECOM_TAG_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_json(path: str | None) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, "not_executed_missing_canary_evidence"
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {}, "not_executed_missing_canary_evidence"
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "not_executed_invalid_canary_evidence"
    if not isinstance(data, dict):
        return {}, "not_executed_invalid_canary_evidence"
    return data, None


def _side_effect_safety(*, cleanup_executed: bool = False, unmark_tag_executed: bool = False) -> dict[str, bool]:
    return {
        "cleanup_executed": cleanup_executed,
        "unmark_tag_executed": unmark_tag_executed,
        "batch_cleanup_executed": False,
        "automatic_cleanup_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "oauth_callback_executed": False,
        "payment_executed": False,
        "media_upload_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def _base_report(*, result_status: str, evidence: dict[str, Any], cleanup_result: dict[str, Any] | None = None) -> dict[str, Any]:
    cleanup_executed = bool(cleanup_result and cleanup_result.get("live_call_executed"))
    unmark_tag_executed = bool(cleanup_result and cleanup_result.get("ok") and cleanup_result.get("unmark_tag_executed"))
    safety = _side_effect_safety(cleanup_executed=cleanup_executed, unmark_tag_executed=unmark_tag_executed)
    report: dict[str, Any] = {
        "ok": bool(cleanup_result.get("ok")) if cleanup_result is not None else True,
        "mode": "production_canary_cleanup",
        "result_status": result_status,
        "cleanup_executed": cleanup_executed,
        "unmark_tag_executed": unmark_tag_executed,
        "same_target_and_tag_confirmed": False,
        "batch_cleanup_executed": False,
        "automatic_cleanup_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": safety,
        **safety,
        "canary_evidence_summary": {
            "present": bool(evidence),
            "mode": evidence.get("mode") or "",
            "result_status": evidence.get("result_status") or "",
            "production_tag_write_executed": bool(evidence.get("production_tag_write_executed")),
            "external_userid_redacted": evidence.get("external_userid_redacted") or "",
            "tag_id": evidence.get("tag_id") or "",
        },
        "timestamp": _timestamp(),
    }
    if cleanup_result is not None:
        report["same_target_and_tag_confirmed"] = True
        report["cleanup_result_summary"] = {
            "ok": bool(cleanup_result.get("ok")),
            "result_status": cleanup_result.get("result_status") or "",
            "error_code": cleanup_result.get("error_code") or "",
        }
    return report


def _first_blocker(args: argparse.Namespace, evidence: dict[str, Any], read_error: str | None) -> str | None:
    if read_error:
        return read_error
    if evidence.get("mode") != "production_live_canary_execution" or evidence.get("production_tag_write_executed") is not True:
        return "not_executed_invalid_canary_evidence"
    if not evidence.get("external_userid_redacted") or not evidence.get("tag_id"):
        return "not_executed_invalid_canary_evidence"
    for name, status in REQUIRED_ENV.items():
        if not _enabled(name):
            return status
    if not args.confirm_production_cleanup_live_wecom_call:
        return "not_executed_missing_confirm_cleanup_live_call"
    if not args.confirm_same_target_and_same_tag:
        return "not_executed_missing_confirm_same_target_and_same_tag"
    if not args.confirm_rollback_owner_approved:
        return "not_executed_missing_rollback_owner"
    if not args.confirm_no_batch_cleanup:
        return "not_executed_missing_confirm_no_batch_cleanup"
    if not evidence.get("external_userid_for_cleanup"):
        return "not_executed_invalid_canary_evidence"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence, read_error = _read_json(args.canary_evidence_json)
    blocker = _first_blocker(args, evidence, read_error)
    if blocker:
        return _base_report(result_status=blocker, evidence=evidence)
    adapter = build_live_wecom_tag_adapter(confirm_live_wecom_call=True)
    cleanup_result = adapter.unmark_tags_live(
        external_userid=str(evidence.get("external_userid_for_cleanup") or ""),
        tag_ids=[str(evidence.get("tag_id") or "")],
        operator=os.getenv("AICRM_WECOM_TAG_OPERATOR", "phase5f_production_cleanup"),
        idempotency_key=f"cleanup:{evidence.get('idempotency_key') or evidence.get('request_hash') or 'phase5f'}",
    )
    result_status = "production_canary_cleanup_completed" if cleanup_result.get("ok") else str(cleanup_result.get("result_status") or "production_canary_cleanup_failed")
    return _base_report(result_status=result_status, evidence=evidence, cleanup_result=cleanup_result)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5F WeCom Tag Production Canary Cleanup",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- cleanup_executed: {str(report.get('cleanup_executed')).lower()}",
        f"- unmark_tag_executed: {str(report.get('unmark_tag_executed')).lower()}",
        f"- same_target_and_tag_confirmed: {str(report.get('same_target_and_tag_confirmed')).lower()}",
        f"- batch_cleanup_executed: {str(report.get('batch_cleanup_executed')).lower()}",
        f"- automatic_cleanup_executed: {str(report.get('automatic_cleanup_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5F WeCom tag production canary cleanup gate.")
    parser.add_argument("--canary-evidence-json")
    parser.add_argument("--confirm-production-cleanup-live-wecom-call", action="store_true")
    parser.add_argument("--confirm-same-target-and-same-tag", action="store_true")
    parser.add_argument("--confirm-rollback-owner-approved", action="store_true")
    parser.add_argument("--confirm-no-batch-cleanup", action="store_true")
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
