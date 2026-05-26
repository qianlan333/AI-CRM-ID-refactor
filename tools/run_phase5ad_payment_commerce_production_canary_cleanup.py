#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        return {}
    try:
        data = json.loads(candidate.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    evidence = _load(args.canary_evidence_json)
    if not evidence:
        missing.append("not_executed_missing_canary_evidence")
    if not _enabled("AICRM_PHASE5AD_PAYMENT_COMMERCE_CLEANUP_APPROVED"):
        missing.append("not_executed_missing_cleanup_approval")
    if not _enabled("AICRM_PHASE5AD_PAYMENT_COMMERCE_ROLLBACK_OWNER_APPROVED"):
        missing.append("not_executed_missing_rollback_owner")
    for attr, status in (
        ("confirm_cleanup_reviewed", "not_executed_missing_confirm_cleanup_reviewed"),
        ("confirm_no_provider_refund", "not_executed_missing_confirm_no_provider_refund"),
        ("confirm_no_production_order_cleanup", "not_executed_missing_confirm_no_order_cleanup"),
        ("confirm_no_batch_cleanup", "not_executed_missing_confirm_no_batch_cleanup"),
    ):
        if not getattr(args, attr):
            missing.append(status)
    return {
        "ok": not missing,
        "mode": "payment_commerce_production_canary_cleanup",
        "result_status": "cleanup_review_ready" if not missing else missing[0],
        "cleanup_executed": False,
        "provider_refund_executed": False,
        "real_payment_capture_executed": False,
        "real_settlement_executed": False,
        "production_order_cleanup_executed": False,
        "batch_cleanup_executed": False,
        "automatic_cleanup_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "cleanup_executed": False,
            "provider_refund_executed": False,
            "production_order_cleanup_executed": False,
            "batch_cleanup_executed": False,
        },
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = {key: report.get(key) for key in ("ok", "result_status", "cleanup_executed", "provider_refund_executed", "production_order_cleanup_executed")}
    Path(path).write_text("# Phase 5AD Payment Production Canary Cleanup\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--canary-evidence-json")
    parser.add_argument("--confirm-cleanup-reviewed", action="store_true")
    parser.add_argument("--confirm-no-provider-refund", action="store_true")
    parser.add_argument("--confirm-no-production-order-cleanup", action="store_true")
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
