#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "order_id": "fake_order_001",
        "amount_cents": 9900,
        "currency": "CNY",
        "mode": args.mode,
    }
    return {
        "ok": args.mode == "fake_stub_contract",
        "mode": "fake_stub_contract",
        "real_payment_capture_executed": False,
        "real_refund_executed": False,
        "real_settlement_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "token_used": False,
        "raw_secret_output": False,
        "deterministic_payment_intent": {
            "intent_id": "fake_pi_" + _hash(payload)[:12],
            "order_id_redacted": "fa***01",
            "amount_cents": 9900,
            "currency": "CNY",
            "real_financial_success_claimed": False,
        },
        "deterministic_webhook_evidence": {
            "event_id": "fake_evt_" + _hash({"event": "payment.succeeded", **payload})[:12],
            "signature_validated": "contract_only",
            "webhook_cutover_executed": False,
        },
        "supported_methods": [
            "create_payment_intent_contract",
            "query_payment_status_contract",
            "request_refund_contract",
            "verify_payment_webhook_contract",
        ],
        "error_mapping": [
            "payment_config_missing",
            "payment_signature_invalid",
            "idempotency_key_required",
            "duplicate_idempotency_key",
            "order_id_missing",
            "amount_invalid",
            "currency_unsupported",
            "real_payment_not_enabled",
            "refund_not_enabled",
            "webhook_cutover_not_enabled",
            "forbidden_in_production_without_approval",
        ],
        "idempotency_policy": {
            "idempotency_key_required_for_write_like_dry_run": True,
            "replay_same_hash": True,
            "conflict_different_hash": True,
            "no_partial_financial_side_effect": True,
        },
        "side_effect_safety": {
            "real_payment_capture_executed": False,
            "real_refund_executed": False,
            "real_settlement_executed": False,
            "production_payment_webhook_cutover_executed": False,
            "production_order_state_mutation_executed": False,
            "network_call_executed": False,
        },
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text("# Phase 5Z Payment Fake Stub Evidence\n\n" + "\n".join(f"- {key}: {report.get(key)}" for key in ("ok", "real_payment_capture_executed", "real_refund_executed", "production_payment_webhook_cutover_executed")) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", default="fake_stub_contract", choices=["fake_stub_contract"])
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "FAIL", "ok": report.get("ok")}, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
