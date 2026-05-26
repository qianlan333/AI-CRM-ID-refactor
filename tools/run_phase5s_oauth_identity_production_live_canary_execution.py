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

from aicrm_next.integration_gateway.oauth_identity_application import build_live_oauth_identity_application_service


FLAG_ENV = {
    "AICRM_OAUTH_IDENTITY_LIVE_ADAPTER_ENABLED": "not_executed_missing_canary_approval",
    "AICRM_OAUTH_IDENTITY_LIVE_CALLBACK_APPROVED": "not_executed_missing_canary_approval",
    "AICRM_OAUTH_IDENTITY_CONFIG_REVIEWED": "not_executed_missing_canary_approval",
    "AICRM_PHASE5S_OAUTH_IDENTITY_PRODUCTION_CANARY_APPROVED": "not_executed_missing_canary_approval",
    "AICRM_PHASE5S_OAUTH_IDENTITY_CALLBACK_TARGET_APPROVED": "not_executed_missing_callback_target_approval",
    "AICRM_PHASE5S_OAUTH_IDENTITY_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5S_OAUTH_IDENTITY_CLEANUP_STRATEGY_APPROVED": "not_executed_missing_cleanup_strategy",
}
CONFIG_ENV = {
    "AICRM_OAUTH_IDENTITY_APP_ID": "not_executed_missing_canary_approval",
    "AICRM_OAUTH_IDENTITY_APP_SECRET": "not_executed_missing_canary_approval",
}
SECRET_OR_TOKEN_KEYS = {
    "access_token",
    "refresh_token",
    "token",
    "raw_token",
    "client_secret",
    "app_secret",
    "secret",
    "raw_code",
    "raw_state",
}
ACCEPTABLE_STAGING_STATUSES = {
    "staging_live_oauth_canary_evidence_completed",
    "staging_canary_phase5p_blocked",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    return bool(str(os.getenv(name, "") or "").strip())


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


def _contains_secret_or_token(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key).lower()
            if key_text in SECRET_OR_TOKEN_KEYS:
                return True
            if key_text in {"code", "state"}:
                return True
            if _contains_secret_or_token(item):
                return True
    elif isinstance(value, list):
        return any(_contains_secret_or_token(item) for item in value)
    elif isinstance(value, str):
        lowered = value.lower()
        if "access_token=" in lowered or "refresh_token=" in lowered or "app_secret=" in lowered or "secret=" in lowered:
            return True
    return False


def _read_json(path: str | None, missing_status: str, invalid_status: str) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, missing_status
    candidate = Path(path)
    if not candidate.exists():
        return {}, missing_status
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, invalid_status
    if not isinstance(data, dict):
        return {}, invalid_status
    if _contains_secret_or_token(data):
        return data, "not_executed_secret_or_token_leak_risk"
    return data, None


def _phase5r_blocker(evidence: dict[str, Any], read_error: str | None) -> str | None:
    if read_error:
        return read_error
    if evidence.get("ready_for_phase5s_production_canary_execution") is not True:
        return "not_executed_invalid_phase5r_readiness"
    for key in (
        "production_live_oauth_call_executed",
        "production_callback_cutover_executed",
        "production_session_write_executed",
        "production_identity_write_executed",
        "token_persisted",
    ):
        if evidence.get(key) is not False:
            return "not_executed_invalid_phase5r_readiness"
    staging_summary = evidence.get("staging_evidence_summary")
    if not isinstance(staging_summary, dict) or not staging_summary.get("redacted_code_present") or not staging_summary.get("redacted_state_present"):
        return "not_executed_invalid_phase5r_readiness"
    return None


def _staging_blocker(evidence: dict[str, Any], read_error: str | None) -> str | None:
    if read_error:
        return read_error
    result_status = str(evidence.get("result_status") or "")
    if not result_status or result_status.startswith(("not_executed_", "blocked")):
        return "not_executed_invalid_staging_evidence"
    if result_status not in ACCEPTABLE_STAGING_STATUSES:
        return "not_executed_invalid_staging_evidence"
    if not isinstance(evidence.get("side_effect_safety"), dict):
        return "not_executed_invalid_staging_evidence"
    if not evidence.get("redacted_code") or not evidence.get("redacted_state") or evidence.get("token_redacted") is not True:
        return "not_executed_invalid_staging_evidence"
    for key in (
        "production_callback_cutover_executed",
        "production_session_write_executed",
        "production_identity_write_executed",
    ):
        if evidence.get(key) is not False:
            return "not_executed_invalid_staging_evidence"
    return None


def _selected_code(args: argparse.Namespace) -> str:
    return str(args.code or args.safe_test_code or "").strip()


def _side_effect_safety(*, production_live_oauth_call_executed: bool = False, code_exchange_executed: bool = False) -> dict[str, bool]:
    return {
        "production_live_oauth_call_executed": production_live_oauth_call_executed,
        "code_exchange_executed": code_exchange_executed,
        "production_callback_cutover_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "token_persisted": False,
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
        "batch_replay_executed": False,
    }


def _base_report(
    args: argparse.Namespace,
    *,
    result_status: str,
    phase5r: dict[str, Any],
    staging: dict[str, Any],
    live_result: dict[str, Any] | None = None,
    reason: str = "",
) -> dict[str, Any]:
    live_executed = bool(live_result and live_result.get("live_oauth_call_executed"))
    code_exchange_executed = bool(live_result and live_result.get("code_exchange_executed"))
    safety = _side_effect_safety(production_live_oauth_call_executed=live_executed, code_exchange_executed=code_exchange_executed)
    state = str(args.state or "")
    code = _selected_code(args)
    payload = {
        "operation": "phase5s_oauth_identity_production_live_canary",
        "redacted_state": _redact(state, label="state"),
        "redacted_code": _redact(code, label="code"),
        "idempotency_key": args.idempotency_key or "",
    }
    report: dict[str, Any] = {
        "ok": bool(live_result.get("ok")) if live_result is not None else not result_status.startswith("not_executed_"),
        "mode": "oauth_identity_production_live_canary_execution",
        "result_status": result_status,
        "reason": reason,
        **safety,
        "single_callback_attempt": True,
        "state_redacted": _redact(state, label="state"),
        "code_redacted": _redact(code, label="code"),
        "token_redacted": True,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _request_hash(payload),
        "rollback_required": live_executed,
        "cleanup_strategy": "cleanup_local_canary_evidence_only_no_session_or_identity_delete",
        "cleanup_runner": "tools/run_phase5s_oauth_identity_production_canary_cleanup.py",
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "side_effect_safety": safety,
        "phase5r_readiness_summary": {
            "present": bool(phase5r),
            "ready_for_phase5s_production_canary_execution": bool(phase5r.get("ready_for_phase5s_production_canary_execution")),
            "result_status": phase5r.get("result_status") or "",
        },
        "staging_evidence_summary": {
            "present": bool(staging),
            "result_status": staging.get("result_status") or "",
            "redacted_code_present": bool(staging.get("redacted_code")),
            "redacted_state_present": bool(staging.get("redacted_state")),
            "token_redacted": bool(staging.get("token_redacted")),
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


def _first_blocker(
    args: argparse.Namespace,
    phase5r: dict[str, Any],
    phase5r_error: str | None,
    staging: dict[str, Any],
    staging_error: str | None,
) -> tuple[str, str] | None:
    phase5r_blocker = _phase5r_blocker(phase5r, phase5r_error)
    if phase5r_blocker:
        return phase5r_blocker, "Phase 5R readiness evidence is missing or invalid"
    staging_blocker = _staging_blocker(staging, staging_error)
    if staging_blocker:
        return staging_blocker, "Phase 5Q staging evidence is missing or invalid"
    for name, status in FLAG_ENV.items():
        if not _enabled(name):
            return status, f"{name}=1 is required"
    for name, status in CONFIG_ENV.items():
        if not _present(name):
            return status, f"{name} is required"
    state = str(args.state or "").strip()
    code = _selected_code(args)
    if not state:
        return "not_executed_missing_state", "--state is required"
    if not code:
        return "not_executed_missing_code", "--code or --safe-test-code is required"
    if "," in state or "," in code:
        return "not_executed_missing_confirm_no_batch_replay", "batch replay is not allowed"
    if not str(args.idempotency_key or "").strip():
        return "not_executed_missing_idempotency_key", "--idempotency-key is required"
    if not args.confirm_production_live_oauth_call:
        return "not_executed_missing_confirm_production_live_oauth_call", "--confirm-production-live-oauth-call is required"
    if not args.confirm_single_approved_callback:
        return "not_executed_missing_confirm_single_callback", "--confirm-single-approved-callback is required"
    if not args.confirm_no_production_callback_cutover:
        return "not_executed_missing_confirm_no_callback_cutover", "--confirm-no-production-callback-cutover is required"
    if not args.confirm_no_production_session_write:
        return "not_executed_missing_confirm_no_session_write", "--confirm-no-production-session-write is required"
    if not args.confirm_no_production_identity_write:
        return "not_executed_missing_confirm_no_identity_write", "--confirm-no-production-identity-write is required"
    if not args.confirm_no_token_persistence:
        return "not_executed_missing_confirm_no_token_persistence", "--confirm-no-token-persistence is required"
    if not args.confirm_rollback_owner_approved:
        return "not_executed_missing_rollback_owner", "--confirm-rollback-owner-approved is required"
    if not args.confirm_no_batch_replay:
        return "not_executed_missing_confirm_no_batch_replay", "--confirm-no-batch-replay is required"
    raw_payload = json.dumps({"state_redacted": _redact(state, label="state"), "code_redacted": _redact(code, label="code")}, ensure_ascii=False).lower()
    if "access_token" in raw_payload or "refresh_token" in raw_payload or "app_secret" in raw_payload or "secret=" in raw_payload:
        return "not_executed_secret_or_token_leak_risk", "secret or token-like input is forbidden"
    return None


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    phase5r, phase5r_error = _read_json(args.phase5r_readiness_json, "not_executed_missing_phase5r_readiness", "not_executed_invalid_phase5r_readiness")
    staging, staging_error = _read_json(args.staging_evidence_json, "not_executed_missing_staging_evidence", "not_executed_invalid_staging_evidence")
    blocker = _first_blocker(args, phase5r, phase5r_error, staging, staging_error)
    if blocker:
        status, reason = blocker
        return _base_report(args, result_status=status, reason=reason, phase5r=phase5r, staging=staging)

    adapter = build_live_oauth_identity_application_service(confirm_live_oauth_callback=True)
    live_result = adapter.exchange_code_live(
        code=_selected_code(args),
        state=str(args.state or "").strip(),
        operator=os.getenv("AICRM_OAUTH_IDENTITY_OPERATOR", "phase5s_production_canary"),
        idempotency_key=str(args.idempotency_key or "").strip(),
    )
    result_status = "production_oauth_live_canary_completed" if live_result.get("ok") else str(live_result.get("result_status") or "production_oauth_live_canary_failed")
    return _base_report(args, result_status=result_status, phase5r=phase5r, staging=staging, live_result=live_result)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5S OAuth Identity Production Live Canary Execution",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- production_live_oauth_call_executed: {str(report.get('production_live_oauth_call_executed')).lower()}",
        f"- production_callback_cutover_executed: {str(report.get('production_callback_cutover_executed')).lower()}",
        f"- production_session_write_executed: {str(report.get('production_session_write_executed')).lower()}",
        f"- production_identity_write_executed: {str(report.get('production_identity_write_executed')).lower()}",
        f"- token_persisted: {str(report.get('token_persisted')).lower()}",
        f"- single_callback_attempt: {str(report.get('single_callback_attempt')).lower()}",
        f"- state_redacted: {report.get('state_redacted') or 'none'}",
        f"- code_redacted: {report.get('code_redacted') or 'none'}",
        f"- token_redacted: {str(report.get('token_redacted')).lower()}",
        f"- cleanup_runner: {report.get('cleanup_runner')}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5S OAuth identity production live canary execution gate.")
    parser.add_argument("--phase5r-readiness-json")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--state")
    code_group = parser.add_mutually_exclusive_group()
    code_group.add_argument("--code")
    code_group.add_argument("--safe-test-code")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-production-live-oauth-call", action="store_true")
    parser.add_argument("--confirm-single-approved-callback", action="store_true")
    parser.add_argument("--confirm-no-production-callback-cutover", action="store_true")
    parser.add_argument("--confirm-no-production-session-write", action="store_true")
    parser.add_argument("--confirm-no-production-identity-write", action="store_true")
    parser.add_argument("--confirm-no-token-persistence", action="store_true")
    parser.add_argument("--confirm-rollback-owner-approved", action="store_true")
    parser.add_argument("--confirm-no-batch-replay", action="store_true")
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
