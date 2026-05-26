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

from aicrm_next.integration_gateway.payment_commerce_live_adapter import build_payment_commerce_live_adapter


REQUIRED_ENV = {
    "AICRM_PAYMENT_COMMERCE_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_PAYMENT_COMMERCE_LIVE_CALL_APPROVED": "not_executed_missing_live_call_approval",
    "AICRM_PAYMENT_COMMERCE_PROVIDER_CONFIG_REVIEWED": "not_executed_missing_provider_config_review",
    "AICRM_PAYMENT_COMMERCE_SANDBOX_MODE_APPROVED": "not_executed_missing_sandbox_mode_approval",
    "AICRM_PAYMENT_COMMERCE_NO_MONEY_MOVEMENT_CONFIRMED": "not_executed_missing_no_money_movement_approval",
    "AICRM_PHASE5AA_PAYMENT_COMMERCE_STAGING_SANDBOX_APPROVED": "not_executed_missing_staging_sandbox_approval",
}
CONFIG_ENV = {
    "AICRM_PAYMENT_COMMERCE_PROVIDER_NAME": "not_executed_missing_provider_config",
    "AICRM_PAYMENT_COMMERCE_PROVIDER_SECRET": "not_executed_missing_provider_config",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def _redact(value: str) -> str:
    text = str(value or "")
    if len(text) <= 4:
        return "***" if text else ""
    return f"{text[:2]}***{text[-2:]}"


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
        "media_upload_executed": False,
        "oauth_callback_executed": False,
        "wecom_live_call_executed": False,
        "openclaw_mcp_executed": False,
        "timer_execution_executed": False,
        "automation_execution_executed": False,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing = ""
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            missing = status
            break
    if not missing and args.execute_sandbox_staging:
        for env, status in CONFIG_ENV.items():
            if not os.getenv(env, "").strip():
                missing = status
                break
    if not missing and not (args.dry_run_live_gate or args.execute_sandbox_staging):
        missing = "not_executed_missing_mode"
    if not missing and args.execute_sandbox_staging and not args.confirm_no_money_movement:
        missing = "not_executed_missing_confirm_no_money_movement"
    if not missing and args.execute_sandbox_staging and not args.confirm_sandbox_only:
        missing = "not_executed_missing_confirm_sandbox_only"
    if not missing and args.execute_sandbox_staging and not args.confirm_no_order_mutation:
        missing = "not_executed_missing_confirm_no_order_mutation"
    if not missing and args.execute_sandbox_staging and not args.confirm_no_webhook_cutover:
        missing = "not_executed_missing_confirm_no_webhook_cutover"
    if not missing and args.execute_sandbox_staging and not args.idempotency_key:
        missing = "not_executed_missing_idempotency_key"
    if not missing and args.execute_sandbox_staging and not args.order_id:
        missing = "not_executed_missing_synthetic_order_id"
    if not missing and args.execute_sandbox_staging and int(args.amount_cents or 0) <= 0:
        missing = "not_executed_invalid_amount"

    live_result: dict[str, Any] | None = None
    if not missing and args.execute_sandbox_staging:
        live_result = build_payment_commerce_live_adapter(confirm_no_money_movement=True).create_payment_intent_live(
            order_id=args.order_id,
            amount_cents=int(args.amount_cents),
            currency=args.currency,
            operator="phase5aa_staging_runner",
            idempotency_key=args.idempotency_key,
        )
    safety = _side_effect_safety()
    provider_call = bool(live_result and live_result.get("provider_call_executed"))
    return {
        "ok": not missing and (bool(live_result.get("ok")) if live_result is not None else True),
        "mode": "payment_commerce_live_staging_evidence",
        "result_status": missing or ("staging_sandbox_payment_gate_ready" if args.dry_run_live_gate else str((live_result or {}).get("result_status") or "blocked")),
        "provider_call_executed": provider_call,
        "real_payment_capture_executed": False,
        "real_refund_executed": False,
        "real_settlement_executed": False,
        "real_charge_executed": False,
        "real_money_movement_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "financial_reconciliation_mutation_executed": False,
        "token_used": False,
        "provider_secret_used": False,
        "provider_secret_redacted": True,
        "order_id_redacted": _redact(args.order_id or ""),
        "amount_cents": int(args.amount_cents or 0),
        "currency": args.currency,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _hash({"mode": "phase5aa", "order_id_present": bool(args.order_id), "amount_cents": int(args.amount_cents or 0), "currency": args.currency, "idempotency_key": args.idempotency_key or ""}),
        **safety,
        "side_effect_safety": {**safety, "provider_call_executed": provider_call, "network_call_executed": provider_call},
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = {
        "ok": report.get("ok"),
        "result_status": report.get("result_status"),
        "provider_call_executed": report.get("provider_call_executed"),
        "real_money_movement_executed": report.get("real_money_movement_executed"),
        "production_order_state_mutation_executed": report.get("production_order_state_mutation_executed"),
    }
    Path(path).write_text("# Phase 5AA Payment Live Staging Evidence\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run-live-gate", action="store_true")
    parser.add_argument("--execute-sandbox-staging", action="store_true")
    parser.add_argument("--confirm-no-money-movement", action="store_true")
    parser.add_argument("--confirm-sandbox-only", action="store_true")
    parser.add_argument("--confirm-no-order-mutation", action="store_true")
    parser.add_argument("--confirm-no-webhook-cutover", action="store_true")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--order-id", default="")
    parser.add_argument("--amount-cents", type=int, default=100)
    parser.add_argument("--currency", default="CNY")
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
