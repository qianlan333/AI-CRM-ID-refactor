#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_PHASE5R_OAUTH_IDENTITY_PRODUCTION_CANARY_PLANNING_APPROVED": "not_executed_missing_production_canary_planning_approval",
    "AICRM_PHASE5R_OAUTH_IDENTITY_PRODUCTION_CONFIG_REVIEWED": "not_executed_missing_production_config_review",
    "AICRM_PHASE5R_OAUTH_IDENTITY_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5R_OAUTH_IDENTITY_CALLBACK_TARGET_POLICY_REVIEWED": "not_executed_missing_callback_target_policy",
    "AICRM_PHASE5R_OAUTH_IDENTITY_TOKEN_POLICY_REVIEWED": "not_executed_missing_token_policy",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _load_json(path: str | None) -> dict[str, Any] | None:
    if not path:
        return None
    candidate = Path(path)
    if not candidate.exists():
        return None
    try:
        value = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _has_leak_risk(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    serialized = json.dumps(report, ensure_ascii=False).lower()
    leak_terms = (
        "access_token",
        "refresh_token",
        "app_secret_value",
        "token_value",
        "secret_value",
        '"code":',
        '"state":',
        '"raw_code"',
        '"raw_state"',
    )
    return any(term in serialized for term in leak_terms)


def _staging_evidence_ok(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    status = str(report.get("result_status", ""))
    if status.startswith("not_executed_") or status.startswith("blocked"):
        return False
    if "redacted_code" not in report or "redacted_state" not in report or report.get("token_redacted") is not True:
        return False
    if not isinstance(report.get("side_effect_safety"), dict):
        return False
    if bool(report.get("production_live_oauth_call_executed")):
        return False
    for key in (
        "production_callback_cutover_executed",
        "production_session_write_executed",
        "production_identity_write_executed",
    ):
        if report.get(key) is not False:
            return False
    return not _has_leak_risk(report)


def _blocked_status(args: argparse.Namespace, evidence: dict[str, Any] | None) -> str:
    if not evidence:
        return "not_executed_missing_staging_evidence"
    if _has_leak_risk(evidence):
        return "not_executed_secret_or_token_leak_risk"
    if not _staging_evidence_ok(evidence):
        return "not_executed_invalid_staging_evidence"
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            return status
    if not args.confirm_no_production_live_oauth_call:
        return "not_executed_missing_confirm_no_production_live_oauth_call"
    if not args.confirm_no_production_callback_cutover:
        return "not_executed_missing_confirm_no_production_callback_cutover"
    if not args.confirm_no_production_session_write:
        return "not_executed_missing_confirm_no_production_session_write"
    if not args.confirm_no_production_identity_write:
        return "not_executed_missing_confirm_no_production_identity_write"
    if not args.confirm_no_token_persistence:
        return "not_executed_missing_confirm_no_token_persistence"
    return ""


def _side_effect_safety() -> dict[str, bool]:
    return {
        "production_live_oauth_call_executed": False,
        "production_callback_cutover_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "token_persisted": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "wecom_live_call_executed": False,
        "payment_executed": False,
        "media_upload_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence = _load_json(args.staging_evidence_json)
    blocked_status = _blocked_status(args, evidence)
    ready = not blocked_status
    safety = _side_effect_safety()
    return {
        "ok": ready,
        "mode": "oauth_identity_production_canary_readiness",
        "result_status": "ready_for_phase5s_production_canary_execution" if ready else blocked_status,
        "ready_for_phase5s_production_canary_execution": ready,
        **safety,
        "staging_evidence_summary": {
            "present": evidence is not None,
            "acceptable": _staging_evidence_ok(evidence),
            "result_status": (evidence or {}).get("result_status", ""),
            "redacted_code_present": bool((evidence or {}).get("redacted_code")),
            "redacted_state_present": bool((evidence or {}).get("redacted_state")),
            "token_redacted": bool((evidence or {}).get("token_redacted")),
        },
        "missing_items": [blocked_status] if blocked_status else [],
        "blockers": [blocked_status] if blocked_status else [],
        "required_owner_actions": ["production owner approval remains required before any live OAuth canary execution"],
        "required_config_actions": ["production OAuth config review must be complete before Phase 5S"],
        "required_callback_target_actions": ["single approved callback target and callback URL policy required for Phase 5S"],
        "required_token_policy_actions": ["token persistence remains disabled unless separately authorized"],
        "required_rollback_actions": ["rollback owner required; cleanup evidence must be captured separately"],
        "side_effect_safety": safety,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5R OAuth Identity Production Canary Readiness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {report.get('result_status')}",
        f"- ready_for_phase5s_production_canary_execution: {str(report.get('ready_for_phase5s_production_canary_execution')).lower()}",
        f"- production_live_oauth_call_executed: {str(report.get('production_live_oauth_call_executed')).lower()}",
        f"- production_callback_cutover_executed: {str(report.get('production_callback_cutover_executed')).lower()}",
        f"- production_session_write_executed: {str(report.get('production_session_write_executed')).lower()}",
        f"- production_identity_write_executed: {str(report.get('production_identity_write_executed')).lower()}",
        f"- token_persisted: {str(report.get('token_persisted')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5R OAuth identity production canary readiness.")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-live-oauth-call", action="store_true")
    parser.add_argument("--confirm-no-production-callback-cutover", action="store_true")
    parser.add_argument("--confirm-no-production-session-write", action="store_true")
    parser.add_argument("--confirm-no-production-identity-write", action="store_true")
    parser.add_argument("--confirm-no-token-persistence", action="store_true")
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
