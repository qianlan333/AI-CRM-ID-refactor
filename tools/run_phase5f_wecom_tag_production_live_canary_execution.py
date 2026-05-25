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

from aicrm_next.customer_tags.wecom_tag_live_adapter import build_live_wecom_tag_adapter


FLAG_ENV = {
    "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_CANARY_APPROVED": "not_executed_missing_canary_approval",
    "AICRM_PHASE5F_WECOM_TAG_PRODUCTION_TARGET_APPROVED": "not_executed_missing_target_approval",
    "AICRM_PHASE5F_WECOM_TAG_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5F_WECOM_TAG_CLEANUP_STRATEGY_APPROVED": "not_executed_missing_cleanup_strategy",
}
LIVE_ENV = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED": "not_executed_missing_canary_approval",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED": "not_executed_missing_canary_approval",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED": "not_executed_missing_canary_approval",
}
SECRET_ENV = {"AICRM_WECOM_TAG_CORP_ID", "AICRM_WECOM_TAG_AGENT_SECRET"}
SECRET_OR_TOKEN_KEYS = {"secret", "corp_secret", "agent_secret", "access_token", "refresh_token", "token"}
ACCEPTABLE_STAGING_STATUSES = {"staging_canary_live_evidence_completed", "ready_for_phase5e_production_canary_planning"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    return bool(str(os.getenv(name, "") or "").strip())


def _redact_external_userid(value: str) -> str:
    value = str(value or "").strip()
    if not value:
        return ""
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contains_secret_or_token(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in SECRET_OR_TOKEN_KEYS:
                return True
            if _contains_secret_or_token(item):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_or_token(item) for item in value)
    elif isinstance(value, str):
        lowered = value.lower()
        if "access_token=" in lowered or "agent_secret=" in lowered or "secret=" in lowered:
            return True
    return False


def _read_json(path: str | None, missing_status: str, invalid_status: str) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, missing_status
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {}, missing_status
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, invalid_status
    if not isinstance(data, dict):
        return {}, invalid_status
    if _contains_secret_or_token(data):
        return data, "not_executed_secret_or_token_leak_risk"
    return data, None


def _phase5e_blocker(evidence: dict[str, Any], read_error: str | None) -> str | None:
    if read_error:
        return read_error
    if evidence.get("ready_for_phase5f_production_canary_execution") is not True:
        return "not_executed_invalid_phase5e_readiness"
    if evidence.get("production_live_call_executed") is not False:
        return "not_executed_invalid_phase5e_readiness"
    if evidence.get("production_tag_write_executed") is not False:
        return "not_executed_invalid_phase5e_readiness"
    target_summary = evidence.get("staging_evidence_summary") or {}
    if not isinstance(target_summary, dict) or not target_summary.get("external_userid_redacted"):
        return "not_executed_invalid_phase5e_readiness"
    return None


def _staging_blocker(evidence: dict[str, Any], read_error: str | None) -> str | None:
    if read_error:
        return read_error
    result_status = str(evidence.get("result_status") or "")
    if not result_status or result_status.startswith(("not_executed", "blocked")) or "blocked" in result_status:
        return "not_executed_invalid_staging_evidence"
    if result_status not in ACCEPTABLE_STAGING_STATUSES:
        return "not_executed_invalid_staging_evidence"
    if not isinstance(evidence.get("side_effect_safety"), dict):
        return "not_executed_invalid_staging_evidence"
    if not evidence.get("external_userid_redacted"):
        return "not_executed_invalid_staging_evidence"
    return None


def _side_effect_safety(*, production_live_call_executed: bool = False, production_tag_write_executed: bool = False) -> dict[str, bool]:
    return {
        "production_live_call_executed": production_live_call_executed,
        "production_tag_write_executed": production_tag_write_executed,
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
        "batch_target_executed": False,
        "customer_pool_target_executed": False,
        "automatic_segment_target_executed": False,
    }


def _target_values(args: argparse.Namespace) -> tuple[str, list[str]]:
    return (args.external_userid or "").strip(), [str(tag or "").strip() for tag in args.tag_id or [] if str(tag or "").strip()]


def _base_report(args: argparse.Namespace, *, result_status: str, phase5e: dict[str, Any], staging: dict[str, Any], live_result: dict[str, Any] | None = None) -> dict[str, Any]:
    external_userid, tag_ids = _target_values(args)
    tag_id = tag_ids[0] if len(tag_ids) == 1 else ""
    production_live_call_executed = bool(live_result and live_result.get("live_call_executed"))
    production_tag_write_executed = bool(live_result and live_result.get("ok") and live_result.get("mark_tag_executed"))
    safety = _side_effect_safety(
        production_live_call_executed=production_live_call_executed,
        production_tag_write_executed=production_tag_write_executed,
    )
    payload = {
        "operation": "phase5f_production_live_canary_mark_tag",
        "external_userid": external_userid,
        "tag_id": tag_id,
        "idempotency_key": args.idempotency_key or "",
    }
    report: dict[str, Any] = {
        "ok": bool(live_result.get("ok")) if live_result is not None else True,
        "mode": "production_live_canary_execution",
        "result_status": result_status,
        "production_live_call_executed": production_live_call_executed,
        "production_tag_write_executed": production_tag_write_executed,
        "target_count": 1 if external_userid else 0,
        "tag_count": len(tag_ids),
        "external_userid_redacted": _redact_external_userid(external_userid),
        "tag_id": tag_id,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _request_hash(payload),
        "rollback_required": production_tag_write_executed,
        "cleanup_strategy": "same_target_same_tag_unmark_with_explicit_rollback_approval",
        "cleanup_runner": "tools/run_phase5f_wecom_tag_production_canary_cleanup.py",
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "side_effect_safety": safety,
        **safety,
        "phase5e_readiness_summary": {
            "present": bool(phase5e),
            "ready_for_phase5f_production_canary_execution": bool(phase5e.get("ready_for_phase5f_production_canary_execution")),
            "result_status": phase5e.get("result_status") or "",
        },
        "staging_evidence_summary": {
            "present": bool(staging),
            "result_status": staging.get("result_status") or "",
            "external_userid_redacted": staging.get("external_userid_redacted") or "",
        },
        "timestamp": _timestamp(),
    }
    if live_result is not None:
        report["live_result_summary"] = {
            "ok": bool(live_result.get("ok")),
            "result_status": live_result.get("result_status") or "",
            "error_code": live_result.get("error_code") or "",
        }
    return report


def _first_blocker(args: argparse.Namespace, phase5e: dict[str, Any], phase5e_error: str | None, staging: dict[str, Any], staging_error: str | None) -> str | None:
    phase5e_blocker = _phase5e_blocker(phase5e, phase5e_error)
    if phase5e_blocker:
        return phase5e_blocker
    staging_blocker = _staging_blocker(staging, staging_error)
    if staging_blocker:
        return staging_blocker
    for name, status in FLAG_ENV.items():
        if not _enabled(name):
            return status
    for name, status in LIVE_ENV.items():
        if not _enabled(name):
            return status
    for name in SECRET_ENV:
        if not _present(name):
            return "not_executed_missing_canary_approval"
    external_userid, tag_ids = _target_values(args)
    if not external_userid:
        return "not_executed_missing_external_userid"
    if "," in external_userid or len(external_userid.split()) > 1:
        return "not_executed_missing_confirm_single_target"
    if not tag_ids:
        return "not_executed_missing_tag_id"
    if len(tag_ids) != 1:
        return "not_executed_missing_confirm_no_batch"
    if not (args.idempotency_key or "").strip():
        return "not_executed_missing_idempotency_key"
    if not args.confirm_production_live_wecom_call:
        return "not_executed_missing_confirm_production_live_call"
    if not args.confirm_single_approved_target:
        return "not_executed_missing_confirm_single_target"
    if not args.confirm_single_approved_tag:
        return "not_executed_missing_confirm_single_tag"
    if not args.confirm_rollback_owner_approved:
        return "not_executed_missing_rollback_owner"
    if not args.confirm_no_batch_target:
        return "not_executed_missing_confirm_no_batch"
    if not args.confirm_no_outbound_send:
        return "not_executed_missing_confirm_no_outbound_send"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    phase5e, phase5e_error = _read_json(args.phase5e_readiness_json, "not_executed_missing_phase5e_readiness", "not_executed_invalid_phase5e_readiness")
    staging, staging_error = _read_json(args.staging_evidence_json, "not_executed_missing_staging_evidence", "not_executed_invalid_staging_evidence")
    blocker = _first_blocker(args, phase5e, phase5e_error, staging, staging_error)
    if blocker:
        return _base_report(args, result_status=blocker, phase5e=phase5e, staging=staging)

    external_userid, tag_ids = _target_values(args)
    adapter = build_live_wecom_tag_adapter(confirm_live_wecom_call=True)
    live_result = adapter.mark_tags_live(
        external_userid=external_userid,
        tag_ids=tag_ids,
        operator=os.getenv("AICRM_WECOM_TAG_OPERATOR", "phase5f_production_canary"),
        idempotency_key=str(args.idempotency_key or "").strip(),
    )
    result_status = "production_live_canary_completed" if live_result.get("ok") else str(live_result.get("result_status") or "production_live_canary_failed")
    return _base_report(args, result_status=result_status, phase5e=phase5e, staging=staging, live_result=live_result)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5F WeCom Tag Production Live Canary Execution",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- production_live_call_executed: {str(report.get('production_live_call_executed')).lower()}",
        f"- production_tag_write_executed: {str(report.get('production_tag_write_executed')).lower()}",
        f"- target_count: {report.get('target_count')}",
        f"- tag_count: {report.get('tag_count')}",
        f"- external_userid_redacted: {report.get('external_userid_redacted') or 'none'}",
        f"- tag_id: {report.get('tag_id') or 'none'}",
        f"- rollback_required: {str(report.get('rollback_required')).lower()}",
        f"- cleanup_runner: {report.get('cleanup_runner')}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5F WeCom tag production live canary execution gate.")
    parser.add_argument("--phase5e-readiness-json")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--external-userid")
    parser.add_argument("--tag-id", action="append")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-production-live-wecom-call", action="store_true")
    parser.add_argument("--confirm-single-approved-target", action="store_true")
    parser.add_argument("--confirm-single-approved-tag", action="store_true")
    parser.add_argument("--confirm-rollback-owner-approved", action="store_true")
    parser.add_argument("--confirm-no-batch-target", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
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
