#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_PHASE5AD_PAYMENT_COMMERCE_PRODUCTION_CANARY_APPROVED": "not_executed_missing_canary_approval",
    "AICRM_PHASE5AD_PAYMENT_COMMERCE_TARGET_APPROVED": "not_executed_missing_target_approval",
    "AICRM_PHASE5AD_PAYMENT_COMMERCE_FINANCE_OWNER_APPROVED": "not_executed_missing_finance_owner",
    "AICRM_PHASE5AD_PAYMENT_COMMERCE_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5AD_PAYMENT_COMMERCE_CLEANUP_STRATEGY_APPROVED": "not_executed_missing_cleanup_strategy",
}


def _enabled(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


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


def _ready(readiness: dict[str, Any]) -> bool:
    return bool(readiness.get("ready_for_phase5ad_production_canary_tooling")) and readiness.get("production_provider_call_executed") is False and readiness.get("real_money_movement_executed") is False


def _staging_ok(evidence: dict[str, Any]) -> bool:
    return bool(evidence.get("ok")) and evidence.get("real_money_movement_executed") is False and evidence.get("production_order_state_mutation_executed") is False and evidence.get("production_payment_webhook_cutover_executed") is False


def _redact(value: str) -> str:
    text = str(value or "")
    return "" if not text else f"{text[:2]}***{text[-2:]}" if len(text) > 4 else "***"


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    readiness = _load(args.phase5ac_readiness_json)
    staging = _load(args.staging_evidence_json)
    if not readiness:
        missing.append("not_executed_missing_phase5ac_readiness")
    elif not _ready(readiness):
        missing.append("not_executed_invalid_phase5ac_readiness")
    if not staging:
        missing.append("not_executed_missing_staging_evidence")
    elif not _staging_ok(staging):
        missing.append("not_executed_invalid_staging_evidence")
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            missing.append(status)
    if not args.synthetic_target_id:
        missing.append("not_executed_missing_synthetic_target")
    if args.synthetic_target_id and "," in args.synthetic_target_id:
        missing.append("not_executed_batch_target_forbidden")
    if not args.idempotency_key:
        missing.append("not_executed_missing_idempotency_key")
    for attr, status in (
        ("confirm_production_canary_tooling", "not_executed_missing_confirm_production_canary_tooling"),
        ("confirm_single_approved_target", "not_executed_missing_confirm_single_target"),
        ("confirm_no_real_money_movement", "not_executed_missing_confirm_no_real_money_movement"),
        ("confirm_no_production_order_mutation", "not_executed_missing_confirm_no_order_mutation"),
        ("confirm_no_webhook_cutover", "not_executed_missing_confirm_no_webhook_cutover"),
        ("confirm_no_batch_target", "not_executed_missing_confirm_no_batch_target"),
    ):
        if not getattr(args, attr):
            missing.append(status)
    return {
        "ok": not missing,
        "mode": "payment_commerce_production_canary_tooling",
        "result_status": "production_canary_tooling_ready_no_money_movement" if not missing else missing[0],
        "production_provider_call_executed": False,
        "real_money_movement_executed": False,
        "real_payment_capture_executed": False,
        "real_refund_executed": False,
        "real_settlement_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "synthetic_target_id_redacted": _redact(args.synthetic_target_id or ""),
        "target_count": 1 if args.synthetic_target_id else 0,
        "idempotency_key": args.idempotency_key or "",
        "request_hash": _hash({"target_present": bool(args.synthetic_target_id), "idempotency_key": args.idempotency_key or ""}),
        "cleanup_runner": "tools/run_phase5ad_payment_commerce_production_canary_cleanup.py",
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "outbound_send_executed": False,
        "missing_items": missing,
        "side_effect_safety": {
            "production_provider_call_executed": False,
            "real_money_movement_executed": False,
            "production_order_state_mutation_executed": False,
            "production_payment_webhook_cutover_executed": False,
        },
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    fields = {key: report.get(key) for key in ("ok", "result_status", "real_money_movement_executed", "production_order_state_mutation_executed")}
    Path(path).write_text("# Phase 5AD Payment Production Canary Tooling\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase5ac-readiness-json")
    parser.add_argument("--staging-evidence-json")
    parser.add_argument("--synthetic-target-id", default="")
    parser.add_argument("--idempotency-key")
    parser.add_argument("--confirm-production-canary-tooling", action="store_true")
    parser.add_argument("--confirm-single-approved-target", action="store_true")
    parser.add_argument("--confirm-no-real-money-movement", action="store_true")
    parser.add_argument("--confirm-no-production-order-mutation", action="store_true")
    parser.add_argument("--confirm-no-webhook-cutover", action="store_true")
    parser.add_argument("--confirm-no-batch-target", action="store_true")
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
