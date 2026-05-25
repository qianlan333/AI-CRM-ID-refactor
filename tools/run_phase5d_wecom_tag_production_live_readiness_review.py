#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_staging_evidence(path: str | None) -> tuple[dict[str, Any], list[str]]:
    if not path:
        return {}, ["staging_evidence_json_required"]
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {}, ["staging_evidence_json_missing"]
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}, ["staging_evidence_json_invalid"]
    return data if isinstance(data, dict) else {}, []


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence, missing_items = _read_staging_evidence(args.staging_evidence_json)
    if not args.confirm_no_production_live_call:
        missing_items.append("confirm_no_production_live_call_required")
    if evidence:
        if not evidence.get("live_call_executed"):
            missing_items.append("staging_live_call_evidence_missing")
        if evidence.get("production_behavior_changed") or evidence.get("production_compat_changed") or evidence.get("fallback_removed"):
            missing_items.append("staging_evidence_contains_forbidden_production_change")
    ready = not missing_items
    return {
        "ok": True,
        "mode": "phase5d_production_live_readiness_review",
        "result_status": "ready_for_phase5e_production_canary_planning" if ready else "blocked_missing_staging_canary_evidence",
        "ready_for_phase5e_production_canary_planning": ready,
        "missing_items": missing_items,
        "evidence_summary": {
            "present": bool(evidence),
            "mode": evidence.get("mode") or "",
            "result_status": evidence.get("result_status") or "",
            "live_call_executed": bool(evidence.get("live_call_executed")),
            "external_userid_redacted": evidence.get("external_userid_redacted") or "",
        },
        "production_live_call_executed": False,
        "production_tag_write_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    missing = report.get("missing_items") or []
    lines = [
        "# Phase 5D WeCom Tag Production Live Readiness Review",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {report.get('result_status')}",
        f"- ready_for_phase5e_production_canary_planning: {str(report.get('ready_for_phase5e_production_canary_planning')).lower()}",
        f"- production_live_call_executed: {str(report.get('production_live_call_executed')).lower()}",
        f"- production_tag_write_executed: {str(report.get('production_tag_write_executed')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- missing_items: {', '.join(missing) if missing else 'none'}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Review Phase 5D production live readiness without any production live call.")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-live-call", action="store_true")
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
