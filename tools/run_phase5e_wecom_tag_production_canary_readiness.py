#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CANARY_PLANNING_APPROVED": "not_executed_missing_production_canary_planning_approval",
    "AICRM_PHASE5E_WECOM_TAG_PRODUCTION_CONFIG_REVIEWED": "not_executed_missing_production_config_review",
    "AICRM_PHASE5E_WECOM_TAG_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5E_WECOM_TAG_TARGET_POLICY_REVIEWED": "not_executed_missing_target_policy",
}
BLOCKED_PREFIXES = ("not_executed", "blocked")
ACCEPTABLE_STAGING_STATUSES = {
    "staging_canary_live_evidence_completed",
    "ready_for_phase5e_production_canary_planning",
}
SECRET_OR_TOKEN_KEYS = {
    "secret",
    "corp_secret",
    "agent_secret",
    "access_token",
    "refresh_token",
    "token",
}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _side_effect_safety() -> dict[str, bool]:
    return {
        "production_live_call_executed": False,
        "production_tag_write_executed": False,
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


def _read_json(path: str | None) -> tuple[dict[str, Any], str | None]:
    if not path:
        return {}, "not_executed_missing_staging_evidence"
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {}, "not_executed_missing_staging_evidence"
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, "not_executed_invalid_staging_evidence"
    if not isinstance(data, dict):
        return {}, "not_executed_invalid_staging_evidence"
    return data, None


def _contains_secret_or_token(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            lowered_key = str(key).lower()
            if lowered_key in SECRET_OR_TOKEN_KEYS:
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


def _staging_evidence_blockers(evidence: dict[str, Any], read_error: str | None) -> list[str]:
    if read_error:
        return [read_error]
    blockers: list[str] = []
    result_status = str(evidence.get("result_status") or "")
    if not result_status or result_status.startswith(BLOCKED_PREFIXES) or "blocked" in result_status:
        blockers.append("not_executed_invalid_staging_evidence")
    elif result_status not in ACCEPTABLE_STAGING_STATUSES:
        blockers.append("not_executed_invalid_staging_evidence")
    if evidence.get("mode") != "phase5d_staging_live_canary":
        blockers.append("not_executed_invalid_staging_evidence")
    if evidence.get("production_live_call_executed") is not False:
        blockers.append("not_executed_invalid_staging_evidence")
    if "side_effect_safety" not in evidence or not isinstance(evidence.get("side_effect_safety"), dict):
        blockers.append("not_executed_invalid_staging_evidence")
    if not evidence.get("external_userid_redacted"):
        blockers.append("not_executed_invalid_staging_evidence")
    if _contains_secret_or_token(evidence):
        blockers.append("not_executed_invalid_staging_evidence")
    return blockers


def _gate_blockers(args: argparse.Namespace, evidence: dict[str, Any], read_error: str | None) -> list[str]:
    blockers = _staging_evidence_blockers(evidence, read_error)
    if blockers:
        return blockers
    for name, status in REQUIRED_ENV.items():
        if not _enabled(name):
            return [status]
    if not args.confirm_no_production_live_call:
        return ["not_executed_missing_confirm_no_production_live_call"]
    if not args.confirm_no_production_tag_write:
        return ["not_executed_missing_confirm_no_production_tag_write"]
    return []


def _summary(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "present": bool(evidence),
        "mode": evidence.get("mode") or "",
        "result_status": evidence.get("result_status") or "",
        "live_call_executed": bool(evidence.get("live_call_executed")),
        "production_live_call_executed": bool(evidence.get("production_live_call_executed")),
        "production_tag_write_executed": bool(evidence.get("production_tag_write_executed")),
        "external_userid_redacted": evidence.get("external_userid_redacted") or "",
        "has_side_effect_safety": isinstance(evidence.get("side_effect_safety"), dict),
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence, read_error = _read_json(args.staging_evidence_json)
    blockers = _gate_blockers(args, evidence, read_error)
    ready = not blockers
    safety = _side_effect_safety()
    missing_items = list(blockers)
    return {
        "ok": True,
        "mode": "production_canary_readiness",
        "result_status": "ready_for_phase5f_production_canary_execution" if ready else blockers[0],
        "ready_for_phase5f_production_canary_execution": ready,
        "production_live_call_executed": False,
        "production_tag_write_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "staging_evidence_summary": _summary(evidence),
        "missing_items": missing_items,
        "blockers": blockers,
        "required_owner_actions": [] if ready else ["approve Phase 5F execution separately", "assign rollback owner"],
        "required_config_actions": [] if ready else ["review production WeCom tag config before Phase 5F"],
        "required_target_actions": [] if ready else ["approve exactly one production external_userid and one tag_id before Phase 5F"],
        "required_rollback_actions": [] if ready else ["prepare explicit same-target same-tag cleanup approval"],
        "side_effect_safety": safety,
        **safety,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5E WeCom Tag Production Canary Readiness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- ready_for_phase5f_production_canary_execution: {str(report.get('ready_for_phase5f_production_canary_execution')).lower()}",
        f"- production_live_call_executed: {str(report.get('production_live_call_executed')).lower()}",
        f"- production_tag_write_executed: {str(report.get('production_tag_write_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- missing_items: {', '.join(report.get('missing_items') or []) or 'none'}",
        f"- blockers: {', '.join(report.get('blockers') or []) or 'none'}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review Phase 5E WeCom tag production canary readiness without production live execution.")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-live-call", action="store_true")
    parser.add_argument("--confirm-no-production-tag-write", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS", "ok": True, "status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
