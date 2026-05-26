#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_PHASE5S_OAUTH_IDENTITY_PRODUCTION_CLEANUP_APPROVED": "not_executed_missing_cleanup_approval",
    "AICRM_PHASE5S_OAUTH_IDENTITY_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _read_json(path: str | None) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, "not_executed_missing_canary_evidence"
    candidate = Path(path)
    if not candidate.exists():
        return {}, "not_executed_missing_canary_evidence"
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "not_executed_invalid_canary_evidence"
    if not isinstance(data, dict):
        return {}, "not_executed_invalid_canary_evidence"
    return data, None


def _side_effect_safety(*, cleanup_executed: bool = False) -> dict[str, bool]:
    return {
        "cleanup_executed": cleanup_executed,
        "token_revocation_executed": False,
        "production_session_delete_executed": False,
        "production_identity_delete_executed": False,
        "batch_cleanup_executed": False,
        "automatic_cleanup_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "payment_executed": False,
        "media_upload_executed": False,
        "wecom_live_call_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def _base_report(*, result_status: str, evidence: dict[str, Any], cleanup_executed: bool = False) -> dict[str, Any]:
    safety = _side_effect_safety(cleanup_executed=cleanup_executed)
    return {
        "ok": cleanup_executed,
        "mode": "oauth_identity_production_canary_cleanup",
        "result_status": result_status,
        **safety,
        "side_effect_safety": safety,
        "canary_evidence_summary": {
            "present": bool(evidence),
            "mode": evidence.get("mode") or "",
            "result_status": evidence.get("result_status") or "",
            "production_live_oauth_call_executed": bool(evidence.get("production_live_oauth_call_executed")),
            "production_session_write_executed": bool(evidence.get("production_session_write_executed")),
            "production_identity_write_executed": bool(evidence.get("production_identity_write_executed")),
            "token_persisted": bool(evidence.get("token_persisted")),
            "state_redacted": evidence.get("state_redacted") or "",
            "code_redacted": evidence.get("code_redacted") or "",
        },
        "cleanup_scope": "local_canary_evidence_only_no_production_session_or_identity_delete",
        "timestamp": _timestamp(),
    }


def _first_blocker(args: argparse.Namespace, evidence: dict[str, Any], read_error: str | None) -> str | None:
    if read_error:
        return read_error
    if evidence.get("mode") != "oauth_identity_production_live_canary_execution":
        return "not_executed_invalid_canary_evidence"
    if evidence.get("production_session_write_executed") is not False or evidence.get("production_identity_write_executed") is not False:
        return "not_executed_invalid_canary_evidence"
    if evidence.get("token_persisted") is not False:
        return "not_executed_invalid_canary_evidence"
    for name, status in REQUIRED_ENV.items():
        if not _enabled(name):
            return status
    if not args.confirm_production_cleanup_reviewed:
        return "not_executed_missing_confirm_cleanup_reviewed"
    if not args.confirm_no_production_session_delete:
        return "not_executed_missing_confirm_no_production_session_delete"
    if not args.confirm_no_production_identity_delete:
        return "not_executed_missing_confirm_no_production_identity_delete"
    if not args.confirm_rollback_owner_approved:
        return "not_executed_missing_rollback_owner"
    if not args.confirm_no_batch_cleanup:
        return "not_executed_missing_confirm_no_batch_cleanup"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence, read_error = _read_json(args.canary_evidence_json)
    blocker = _first_blocker(args, evidence, read_error)
    if blocker:
        return _base_report(result_status=blocker, evidence=evidence)
    return _base_report(result_status="production_canary_cleanup_review_completed", evidence=evidence, cleanup_executed=True)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5S OAuth Identity Production Canary Cleanup",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- cleanup_executed: {str(report.get('cleanup_executed')).lower()}",
        f"- token_revocation_executed: {str(report.get('token_revocation_executed')).lower()}",
        f"- production_session_delete_executed: {str(report.get('production_session_delete_executed')).lower()}",
        f"- production_identity_delete_executed: {str(report.get('production_identity_delete_executed')).lower()}",
        f"- batch_cleanup_executed: {str(report.get('batch_cleanup_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5S OAuth identity production canary cleanup gate.")
    parser.add_argument("--canary-evidence-json")
    parser.add_argument("--confirm-production-cleanup-reviewed", action="store_true")
    parser.add_argument("--confirm-no-production-session-delete", action="store_true")
    parser.add_argument("--confirm-no-production-identity-delete", action="store_true")
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
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
