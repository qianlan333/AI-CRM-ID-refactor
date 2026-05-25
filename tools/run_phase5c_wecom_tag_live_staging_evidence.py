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


LIVE_ENV = {
    "AICRM_WECOM_TAG_LIVE_ADAPTER_ENABLED",
    "AICRM_WECOM_TAG_LIVE_CALL_APPROVED",
    "AICRM_WECOM_TAG_CONFIG_REVIEWED",
    "AICRM_WECOM_TAG_CORP_ID",
    "AICRM_WECOM_TAG_AGENT_SECRET",
}
STAGING_APPROVAL_ENV = "AICRM_PHASE5C_WECOM_TAG_STAGING_LIVE_APPROVED"


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _present(name: str) -> bool:
    return bool(str(os.getenv(name, "") or "").strip())


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety(*, live_call_executed: bool = False, token_used: bool = False, network_call_executed: bool = False) -> dict[str, bool]:
    return {
        "live_call_executed": live_call_executed,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
        "outbound_send_executed": False,
        "token_used": token_used,
        "network_call_executed": network_call_executed,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _base(*, mode: str, result_status: str, reason: str = "", live_call_executed: bool = False, token_used: bool = False, network_call_executed: bool = False) -> dict[str, Any]:
    payload = {"mode": mode, "runner": "phase5c_staging_live_evidence"}
    safety = _side_effect_safety(
        live_call_executed=live_call_executed,
        token_used=token_used,
        network_call_executed=network_call_executed,
    )
    return {
        "ok": True,
        "mode": mode,
        "result_status": result_status,
        "reason": reason,
        **safety,
        "config_reviewed": _enabled("AICRM_WECOM_TAG_CONFIG_REVIEWED"),
        "approval_present": _enabled("AICRM_WECOM_TAG_LIVE_CALL_APPROVED") and _enabled(STAGING_APPROVAL_ENV),
        "idempotency_key": "phase5c-staging-live-list",
        "request_hash": _request_hash(payload),
        "side_effect_safety": safety,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _gate_blockers(args: argparse.Namespace) -> list[str]:
    blockers: list[str] = []
    for name in sorted(LIVE_ENV):
        if name in {"AICRM_WECOM_TAG_CORP_ID", "AICRM_WECOM_TAG_AGENT_SECRET"}:
            if not _present(name):
                blockers.append(f"{name} is required")
        elif not _enabled(name):
            blockers.append(f"{name}=1 is required")
    if not _enabled(STAGING_APPROVAL_ENV):
        blockers.append(f"{STAGING_APPROVAL_ENV}=1 is required")
    if args.execute_live_staging and not args.confirm_live_wecom_call:
        blockers.append("--confirm-live-wecom-call is required")
    return blockers


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    if not args.dry_run_live_gate and not args.execute_live_staging:
        return _base(mode="blocked", result_status="blocked_not_executed", reason="select --dry-run-live-gate or --execute-live-staging")

    blockers = _gate_blockers(args)
    if blockers:
        return _base(mode="dry_run_live_gate" if args.dry_run_live_gate else "execute_live_staging", result_status="blocked_not_executed", reason="; ".join(blockers))

    if args.dry_run_live_gate:
        return _base(mode="dry_run_live_gate", result_status="ready_no_live_call")

    adapter = build_live_wecom_tag_adapter(confirm_live_wecom_call=args.confirm_live_wecom_call)
    result = adapter.list_wecom_tags_live()
    report = _base(
        mode="execute_live_staging",
        result_status=str(result.get("result_status") or "live_evidence_completed"),
        reason=str(result.get("error_message") or ""),
        live_call_executed=bool(result.get("live_call_executed")),
        token_used=bool(result.get("token_used")),
        network_call_executed=bool(result.get("network_call_executed")),
    )
    report["ok"] = bool(result.get("ok"))
    report["live_result_summary"] = {
        "ok": bool(result.get("ok")),
        "error_code": result.get("error_code") or "",
        "result_status": result.get("result_status") or "",
    }
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5C WeCom Tag Live Staging Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- live_call_executed: {str(report.get('live_call_executed')).lower()}",
        f"- mark_tag_executed: {str(report.get('mark_tag_executed')).lower()}",
        f"- unmark_tag_executed: {str(report.get('unmark_tag_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- reason: {report.get('reason') or 'none'}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5C WeCom tag live staging evidence.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run-live-gate", action="store_true")
    mode.add_argument("--execute-live-staging", action="store_true")
    parser.add_argument("--confirm-live-wecom-call", action="store_true")
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
