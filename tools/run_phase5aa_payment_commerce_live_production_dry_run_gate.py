#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _side_effect_safety() -> dict[str, bool]:
    return {
        "provider_call_executed": False,
        "network_call_executed": False,
        "real_payment_capture_executed": False,
        "real_refund_executed": False,
        "real_settlement_executed": False,
        "real_charge_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "financial_reconciliation_mutation_executed": False,
        "token_used": False,
        "provider_secret_used": False,
        "raw_payment_secret_output": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing = ""
    if not args.dry_run:
        missing = "not_executed_missing_dry_run"
    elif not args.confirm_no_production_provider_call:
        missing = "not_executed_missing_confirm_no_production_provider_call"
    elif not args.confirm_no_money_movement:
        missing = "not_executed_missing_confirm_no_money_movement"
    elif not args.confirm_no_order_mutation:
        missing = "not_executed_missing_confirm_no_order_mutation"
    elif not args.confirm_no_webhook_cutover:
        missing = "not_executed_missing_confirm_no_webhook_cutover"
    safety = _side_effect_safety()
    return {
        "ok": not missing,
        "mode": "payment_commerce_live_production_dry_run_gate",
        "result_status": missing or "production_dry_run_gate_ready",
        "provider_call_executed": False,
        "production_provider_call_executed": False,
        "real_money_movement_executed": False,
        "real_payment_capture_executed": False,
        "real_refund_executed": False,
        "real_settlement_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "financial_reconciliation_mutation_executed": False,
        "provider_secret_redacted": True,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": safety,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = {
        "ok": report.get("ok"),
        "result_status": report.get("result_status"),
        "production_provider_call_executed": report.get("production_provider_call_executed"),
        "real_money_movement_executed": report.get("real_money_movement_executed"),
        "production_order_state_mutation_executed": report.get("production_order_state_mutation_executed"),
    }
    Path(path).write_text("# Phase 5AA Payment Production Dry-Run Gate\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
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
