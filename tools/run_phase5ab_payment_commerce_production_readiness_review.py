#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load(path: str | None) -> dict[str, Any]:
    if not path:
        return {}
    evidence_path = Path(path)
    if not evidence_path.exists():
        return {}
    try:
        data = json.loads(evidence_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _has_leak(data: dict[str, Any]) -> bool:
    text = json.dumps(data, ensure_ascii=False).lower()
    return any(token in text for token in ("secret=", "token=", "provider_secret\":", "raw_payment_secret", "sk_live"))


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    evidence = _load(args.staging_evidence_json)
    missing: list[str] = []
    if not evidence:
        missing.append("not_executed_missing_staging_evidence")
    elif not evidence.get("ok"):
        missing.append("not_executed_invalid_staging_evidence")
    elif evidence.get("real_money_movement_executed") is not False or evidence.get("production_order_state_mutation_executed") is not False or evidence.get("production_payment_webhook_cutover_executed") is not False:
        missing.append("not_executed_invalid_staging_evidence")
    elif not evidence.get("provider_secret_redacted"):
        missing.append("not_executed_invalid_staging_evidence")
    elif _has_leak(evidence):
        missing.append("not_executed_secret_or_token_leak_risk")
    if not args.confirm_no_production_provider_call:
        missing.append("not_executed_missing_confirm_no_production_provider_call")
    if not args.confirm_no_money_movement:
        missing.append("not_executed_missing_confirm_no_money_movement")
    if not args.confirm_no_order_mutation:
        missing.append("not_executed_missing_confirm_no_order_mutation")
    if not args.confirm_no_webhook_cutover:
        missing.append("not_executed_missing_confirm_no_webhook_cutover")
    return {
        "ok": not missing,
        "mode": "payment_commerce_production_readiness_review",
        "ready_for_phase5ac_production_canary_readiness": not missing,
        "result_status": "production_readiness_review_ready" if not missing else missing[0],
        "missing_items": missing,
        "evidence_summary": {
            "result_status": evidence.get("result_status", ""),
            "synthetic_order_id_redacted": evidence.get("synthetic_order_id_redacted", ""),
        },
        "production_provider_call_executed": False,
        "real_money_movement_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "financial_reconciliation_mutation_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = {key: report.get(key) for key in ("ok", "result_status", "production_provider_call_executed", "real_money_movement_executed", "production_order_state_mutation_executed")}
    Path(path).write_text("# Phase 5AB Payment Production Readiness Review\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--confirm-no-production-provider-call", action="store_true")
    parser.add_argument("--confirm-no-money-movement", action="store_true")
    parser.add_argument("--confirm-no-order-mutation", action="store_true")
    parser.add_argument("--confirm-no-webhook-cutover", action="store_true")
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
