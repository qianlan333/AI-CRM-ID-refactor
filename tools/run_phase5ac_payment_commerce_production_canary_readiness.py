#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REQUIRED_ENV = {
    "AICRM_PHASE5AC_PAYMENT_COMMERCE_PRODUCTION_CANARY_PLANNING_APPROVED": "not_executed_missing_production_canary_planning_approval",
    "AICRM_PHASE5AC_PAYMENT_COMMERCE_PROVIDER_CONFIG_REVIEWED": "not_executed_missing_payment_config_review",
    "AICRM_PHASE5AC_PAYMENT_COMMERCE_FINANCE_OWNER_APPROVED": "not_executed_missing_finance_owner_approval",
    "AICRM_PHASE5AC_PAYMENT_COMMERCE_ROLLBACK_OWNER_APPROVED": "not_executed_missing_rollback_owner",
    "AICRM_PHASE5AC_PAYMENT_COMMERCE_TARGET_POLICY_REVIEWED": "not_executed_missing_target_policy",
}


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


def _has_leak(data: dict[str, Any]) -> bool:
    text = json.dumps(data, ensure_ascii=False).lower()
    return any(token in text for token in ("sk_live", "secret=", "token=", "provider_secret\":", "raw_payment_secret"))


def _evidence_ok(evidence: dict[str, Any]) -> bool:
    return (
        bool(evidence.get("ok"))
        and evidence.get("real_money_movement_executed") is False
        and evidence.get("production_order_state_mutation_executed") is False
        and evidence.get("production_payment_webhook_cutover_executed") is False
        and evidence.get("provider_secret_redacted") is True
        and "side_effect_safety" in evidence
        and not _has_leak(evidence)
    )


def build_report(args: argparse.Namespace) -> dict[str, Any]:
    missing: list[str] = []
    evidence = _load(args.staging_evidence_json)
    if not evidence:
        missing.append("not_executed_missing_staging_evidence")
    elif not _evidence_ok(evidence):
        missing.append("not_executed_invalid_staging_evidence")
    for env, status in REQUIRED_ENV.items():
        if not _enabled(env):
            missing.append(status)
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
        "mode": "payment_commerce_production_canary_readiness",
        "result_status": "ready_for_phase5ad_production_canary_tooling" if not missing else missing[0],
        "ready_for_phase5ad_production_canary_tooling": not missing,
        "production_provider_call_executed": False,
        "real_money_movement_executed": False,
        "real_payment_capture_executed": False,
        "real_refund_executed": False,
        "real_settlement_executed": False,
        "real_charge_executed": False,
        "production_payment_webhook_cutover_executed": False,
        "production_order_state_mutation_executed": False,
        "financial_reconciliation_mutation_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "missing_items": missing,
        "blockers": missing,
        "staging_evidence_summary": {
            "result_status": evidence.get("result_status", ""),
            "synthetic_order_id_redacted": evidence.get("synthetic_order_id_redacted", ""),
        },
        "required_owner_actions": ["finance_owner_approval", "rollback_owner_approval", "target_policy_review"],
        "required_config_actions": ["payment_provider_config_review"],
        "required_target_actions": ["single_synthetic_target_policy"],
        "required_rollback_actions": ["explicit_cleanup_strategy_for_later_tooling"],
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
    fields = {key: report.get(key) for key in ("ok", "result_status", "production_provider_call_executed", "real_money_movement_executed", "production_order_state_mutation_executed")}
    Path(path).write_text("# Phase 5AC Payment Production Canary Readiness\n\n" + "\n".join(f"- {key}: {value}" for key, value in fields.items()) + "\n", encoding="utf-8")


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
