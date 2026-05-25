#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_PHASE5L_WECOM_CONTACT_PRODUCTION_CANARY_PLANNING_APPROVED": "not_executed_missing_production_canary_planning_approval",
    "AICRM_PHASE5L_WECOM_CONTACT_PRODUCTION_CONFIG_REVIEWED": "not_executed_missing_production_config_review",
    "AICRM_PHASE5L_WECOM_CONTACT_TARGET_POLICY_REVIEWED": "not_executed_missing_target_policy",
    "AICRM_PHASE5L_WECOM_CONTACT_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
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


def _evidence_ok(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    if str(report.get("result_status", "")).startswith("not_executed_"):
        return False
    if not isinstance(report.get("side_effect_safety"), dict):
        return False
    raw = json.dumps(report, ensure_ascii=False).lower()
    return "secret" not in raw and "token_value" not in raw and "aes_key_value" not in raw and "external_userid_redacted" in report


def _blocked_status(args: argparse.Namespace, evidence: dict[str, Any] | None) -> str:
    if not evidence:
        return "not_executed_missing_staging_evidence"
    if not _evidence_ok(evidence):
        return "not_executed_invalid_staging_evidence"
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            return status
    if not args.confirm_no_production_live_callback:
        return "not_executed_missing_confirm_no_production_live_callback"
    if not args.confirm_no_production_write:
        return "not_executed_missing_confirm_no_production_write"
    if args.execute_production_canary:
        if not args.external_userid:
            return "not_executed_missing_external_userid"
        if "," in args.external_userid:
            return "not_executed_batch_target_rejected"
        if not args.event_key:
            return "not_executed_missing_event_key"
        if "," in args.event_key:
            return "not_executed_batch_event_rejected"
        if not args.idempotency_key:
            return "not_executed_missing_idempotency_key"
        if not args.confirm_production_live_callback:
            return "not_executed_missing_confirm_production_live_callback"
        if not args.confirm_single_approved_target:
            return "not_executed_missing_confirm_single_target"
        if not args.confirm_rollback_owner_approved:
            return "not_executed_missing_confirm_rollback_owner"
    return ""


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence = _load_json(args.staging_evidence_json)
    blocked_status = _blocked_status(args, evidence)
    ready = not blocked_status and not args.execute_production_canary
    executed = False
    return {
        "ok": ready,
        "mode": "production_callback_canary_readiness",
        "result_status": "ready_for_phase5m_family_acceptance_or_later_canary" if ready else (blocked_status or "not_executed_production_canary_execution_deferred"),
        "ready_for_phase5m_family_acceptance": ready,
        "production_canary_executed": executed,
        "production_live_callback_processed": False,
        "production_contact_write_executed": False,
        "production_identity_mapping_write_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "target_count": 1 if args.external_userid else 0,
        "event_count": 1 if args.event_key else 0,
        "missing_items": [blocked_status] if blocked_status else [],
        "staging_evidence_summary": {
            "present": evidence is not None,
            "acceptable": _evidence_ok(evidence),
            "result_status": (evidence or {}).get("result_status", ""),
            "live_callback_processed": bool((evidence or {}).get("live_callback_processed")),
        },
        "required_owner_actions": ["production owner approval remains required before any real callback canary"],
        "required_rollback_actions": ["rollback owner required; cleanup evidence must be separate"],
        "side_effect_safety": {
            "production_live_callback_processed": False,
            "production_contact_write_executed": False,
            "production_identity_mapping_write_executed": False,
            "outbound_send_executed": False,
            "production_compat_changed": False,
            "fallback_removed": False,
        },
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5L WeCom Contact Production Callback Canary Readiness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {report.get('result_status')}",
        f"- production_canary_executed: {str(report.get('production_canary_executed')).lower()}",
        f"- production_live_callback_processed: {str(report.get('production_live_callback_processed')).lower()}",
        f"- production_contact_write_executed: {str(report.get('production_contact_write_executed')).lower()}",
        f"- production_identity_mapping_write_executed: {str(report.get('production_identity_mapping_write_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5L production callback canary readiness/tooling evidence.")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--execute-production-canary", action="store_true")
    parser.add_argument("--external-userid")
    parser.add_argument("--event-key")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-no-production-live-callback", action="store_true")
    parser.add_argument("--confirm-no-production-write", action="store_true")
    parser.add_argument("--confirm-production-live-callback", action="store_true")
    parser.add_argument("--confirm-single-approved-target", action="store_true")
    parser.add_argument("--confirm-rollback-owner-approved", action="store_true")
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
