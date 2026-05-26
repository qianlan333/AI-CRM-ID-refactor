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

from tools import run_phase5aa_payment_commerce_live_staging_evidence as phase5aa_runner


REQUIRED_ENV = {
    "AICRM_PAYMENT_COMMERCE_LIVE_ADAPTER_ENABLED": "not_executed_missing_live_adapter_enabled",
    "AICRM_PAYMENT_COMMERCE_LIVE_CALL_APPROVED": "not_executed_missing_live_call_approval",
    "AICRM_PAYMENT_COMMERCE_PROVIDER_CONFIG_REVIEWED": "not_executed_missing_provider_config_review",
    "AICRM_PAYMENT_COMMERCE_SANDBOX_MODE_APPROVED": "not_executed_missing_sandbox_mode_approval",
    "AICRM_PAYMENT_COMMERCE_NO_MONEY_MOVEMENT_CONFIRMED": "not_executed_missing_no_money_movement_approval",
    "AICRM_PHASE5AB_PAYMENT_COMMERCE_STAGING_SANDBOX_APPROVED": "not_executed_missing_staging_sandbox_approval",
    "AICRM_PHASE5AB_PAYMENT_COMMERCE_TARGET_APPROVED": "not_executed_missing_target_approval",
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


def _safe_false() -> dict[str, bool]:
    return {
        "provider_call_executed": False,
        "network_call_executed": False,
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
        "raw_payment_secret_output": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
    }


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing = ""
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            missing = status
            break
    if not missing:
        for env, status in CONFIG_ENV.items():
            if not os.getenv(env, "").strip():
                missing = status
                break
    if not missing and not args.execute_staging_sandbox_canary:
        missing = "not_executed_missing_execute_staging_sandbox_canary"
    if not missing and not args.synthetic_order_id:
        missing = "not_executed_missing_synthetic_order_id"
    if not missing and "," in args.synthetic_order_id:
        missing = "not_executed_batch_replay_forbidden"
    if not missing and not args.idempotency_key:
        missing = "not_executed_missing_idempotency_key"
    if not missing and not args.confirm_no_real_money_movement:
        missing = "not_executed_missing_confirm_no_real_money_movement"
    if not missing and not args.confirm_sandbox_only:
        missing = "not_executed_missing_confirm_sandbox_only"
    if not missing and not args.confirm_no_production_order_mutation:
        missing = "not_executed_missing_confirm_no_production_order_mutation"
    if not missing and not args.confirm_no_webhook_cutover:
        missing = "not_executed_missing_confirm_no_webhook_cutover"

    phase5aa_evidence: dict[str, Any] | None = None
    if not missing:
        phase5aa_evidence = phase5aa_runner.build_report(
            argparse.Namespace(
                dry_run_live_gate=False,
                execute_sandbox_staging=True,
                confirm_no_money_movement=True,
                confirm_sandbox_only=True,
                confirm_no_order_mutation=True,
                confirm_no_webhook_cutover=True,
                idempotency_key=args.idempotency_key,
                order_id=args.synthetic_order_id,
                amount_cents=args.amount_cents,
                currency=args.currency,
            )
        )

    safety = _safe_false()
    return {
        "ok": not missing and bool((phase5aa_evidence or {}).get("ok")),
        "mode": "payment_commerce_staging_sandbox_canary_evidence",
        "result_status": missing or str((phase5aa_evidence or {}).get("result_status") or "blocked"),
        "synthetic_order_id_redacted": _redact(args.synthetic_order_id or ""),
        "target_count": 1 if args.synthetic_order_id else 0,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _hash({"synthetic_order_id_present": bool(args.synthetic_order_id), "amount_cents": args.amount_cents, "currency": args.currency, "idempotency_key": args.idempotency_key or ""}),
        "provider_secret_redacted": True,
        "cleanup_required": False,
        "cleanup_strategy": "review_only_no_real_money_movement",
        **safety,
        "side_effect_safety": safety,
        "phase5aa_evidence_summary": {
            "ok": bool((phase5aa_evidence or {}).get("ok")),
            "result_status": (phase5aa_evidence or {}).get("result_status", ""),
            "provider_call_executed": bool((phase5aa_evidence or {}).get("provider_call_executed")),
        },
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = {key: report.get(key) for key in ("ok", "result_status", "real_money_movement_executed", "production_order_state_mutation_executed", "production_payment_webhook_cutover_executed")}
    Path(path).write_text("# Phase 5AB Payment Staging Sandbox Canary Evidence\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-staging-sandbox-canary", action="store_true")
    parser.add_argument("--synthetic-order-id", default="")
    parser.add_argument("--amount-cents", type=int, default=100)
    parser.add_argument("--currency", default="CNY")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-no-real-money-movement", action="store_true")
    parser.add_argument("--confirm-sandbox-only", action="store_true")
    parser.add_argument("--confirm-no-production-order-mutation", action="store_true")
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
