#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


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


def _looks_acceptable(report: dict[str, Any] | None) -> bool:
    if not report:
        return False
    if str(report.get("result_status", "")).startswith("not_executed_"):
        return False
    if "redacted_state" not in report or "redacted_code" not in report:
        return False
    if not isinstance(report.get("side_effect_safety"), dict):
        return False
    raw = json.dumps(report, ensure_ascii=False).lower()
    leak_terms = ("access_token", "refresh_token", "app_secret_value", "raw_code", "raw_state")
    return not any(term in raw for term in leak_terms)


def build_report(
    *,
    staging_evidence_json: str | None,
    confirm_no_production_live_oauth_call: bool,
    confirm_no_production_callback_cutover: bool,
    confirm_no_production_session_write: bool,
) -> dict[str, Any]:
    staging = _load_json(staging_evidence_json)
    missing_items: list[str] = []
    if not staging:
        missing_items.append("staging_evidence_json")
    elif not _looks_acceptable(staging):
        missing_items.append("acceptable_staging_evidence")
    if not confirm_no_production_live_oauth_call:
        missing_items.append("confirm_no_production_live_oauth_call")
    if not confirm_no_production_callback_cutover:
        missing_items.append("confirm_no_production_callback_cutover")
    if not confirm_no_production_session_write:
        missing_items.append("confirm_no_production_session_write")
    ready = not missing_items
    return {
        "ok": ready,
        "mode": "oauth_identity_production_live_readiness_review",
        "ready_for_phase5r_production_canary_readiness": ready,
        "missing_items": missing_items,
        "evidence_summary": {
            "present": staging is not None,
            "result_status": (staging or {}).get("result_status", ""),
            "live_oauth_call_executed": bool((staging or {}).get("live_oauth_call_executed")),
            "redacted_state_present": bool((staging or {}).get("redacted_state")),
            "redacted_code_present": bool((staging or {}).get("redacted_code")),
        },
        "production_live_oauth_call_executed": False,
        "production_callback_cutover_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5Q OAuth Identity Production Live Readiness Review",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- ready_for_phase5r_production_canary_readiness: {str(report.get('ready_for_phase5r_production_canary_readiness')).lower()}",
        f"- missing_items: {', '.join(report.get('missing_items', [])) or 'none'}",
        f"- production_live_oauth_call_executed: {str(report.get('production_live_oauth_call_executed')).lower()}",
        f"- production_callback_cutover_executed: {str(report.get('production_callback_cutover_executed')).lower()}",
        f"- production_session_write_executed: {str(report.get('production_session_write_executed')).lower()}",
        f"- production_identity_write_executed: {str(report.get('production_identity_write_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review Phase 5Q staging OAuth evidence before production readiness.")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-live-oauth-call", action="store_true")
    parser.add_argument("--confirm-no-production-callback-cutover", action="store_true")
    parser.add_argument("--confirm-no-production-session-write", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(
        staging_evidence_json=args.staging_evidence_json,
        confirm_no_production_live_oauth_call=args.confirm_no_production_live_oauth_call,
        confirm_no_production_callback_cutover=args.confirm_no_production_callback_cutover,
        confirm_no_production_session_write=args.confirm_no_production_session_write,
    )
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "missing_items": report.get("missing_items")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
