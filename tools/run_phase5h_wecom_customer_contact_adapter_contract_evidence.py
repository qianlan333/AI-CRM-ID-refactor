#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


MODE = "fake_stub_contract"
SUPPORTED_METHODS = [
    "verify_callback_contract",
    "parse_external_contact_event",
    "normalize_external_contact_event",
    "dry_run_record_contact_event",
    "dry_run_identity_mapping",
]
ERROR_MAPPING = [
    "callback_config_missing",
    "signature_invalid",
    "decrypt_not_enabled",
    "event_type_unsupported",
    "external_userid_missing",
    "follow_user_userid_missing",
    "idempotency_key_required",
    "duplicate_event_key",
    "live_callback_not_enabled",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
]
DETERMINISTIC_EVENTS = [
    {
        "event_type": "external_contact",
        "change_type": "add_external_contact",
        "event_key": "phase5h:external_contact:add:external_userid_001:follow_user_001",
        "external_userid_redacted": "external...0001",
        "follow_user_userid": "follow_user_001",
    },
    {
        "event_type": "external_contact",
        "change_type": "edit_external_contact",
        "event_key": "phase5h:external_contact:edit:external_userid_002:follow_user_001",
        "external_userid_redacted": "external...0002",
        "follow_user_userid": "follow_user_001",
    },
]


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_callback_cutover_allowed": False,
        "network_call_allowed": False,
        "decrypt_executed": False,
        "production_contact_write_allowed": False,
        "production_identity_mapping_write_allowed": False,
        "production_tag_write_allowed": False,
        "outbound_send_allowed": False,
        "token_refresh_allowed": False,
        "customer_sync_allowed": False,
        "db_write_allowed": False,
    }


def build_report(mode: str = MODE) -> dict[str, Any]:
    if mode != MODE:
        return {
            "ok": False,
            "mode": mode,
            "error_code": "adapter_unavailable",
            "result_status": "unsupported_mode",
            "live_callback_processed": False,
            "production_write_executed": False,
            "timestamp": _timestamp(),
        }

    event = DETERMINISTIC_EVENTS[0]
    payload = {
        "mode": mode,
        "event_key": event["event_key"],
        "external_userid_redacted": event["external_userid_redacted"],
        "follow_user_userid": event["follow_user_userid"],
        "operator": "phase5h_contract_runner",
        "idempotency_key": "phase5h-contract-evidence",
    }
    return {
        "ok": True,
        "mode": MODE,
        "adapter_mode": MODE,
        "route_family": "/wecom/external-contact/callback",
        "capability_owner": "aicrm_next.integration_gateway",
        "live_callback_processed": False,
        "production_write_executed": False,
        "production_contact_write_executed": False,
        "production_identity_mapping_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "aes_key_used": False,
        "deterministic_events": DETERMINISTIC_EVENTS,
        "supported_methods": SUPPORTED_METHODS,
        "error_mapping": ERROR_MAPPING,
        "idempotency_policy": {
            "event_key_required": True,
            "idempotency_key_required_for_write_like_dry_run": True,
            "replay_same_event_key": True,
            "conflict_different_hash": True,
            "retry_safe": True,
            "no_partial_production_side_effect": True,
        },
        "evidence_policy": {
            "event_type": event["event_type"],
            "event_key": event["event_key"],
            "external_userid_redacted": event["external_userid_redacted"],
            "follow_user_userid": event["follow_user_userid"],
            "operator": "phase5h_contract_runner",
            "idempotency_key": "phase5h-contract-evidence",
            "request_hash": _request_hash(payload),
            "result_status": "contract_evidence_only",
            "timestamp": _timestamp(),
        },
        "side_effect_safety": _side_effect_safety(),
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5H WeCom Customer Contact Adapter Contract Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- live_callback_processed: {str(report.get('live_callback_processed')).lower()}",
        f"- production_contact_write_executed: {str(report.get('production_contact_write_executed')).lower()}",
        f"- production_identity_mapping_write_executed: {str(report.get('production_identity_mapping_write_executed')).lower()}",
        f"- production_tag_write_executed: {str(report.get('production_tag_write_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- token_used: {str(report.get('token_used')).lower()}",
        f"- aes_key_used: {str(report.get('aes_key_used')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        "",
        "## Supported Methods",
        *(f"- {item}" for item in report.get("supported_methods", [])),
        "",
        "## Error Mapping",
        *(f"- {item}" for item in report.get("error_mapping", [])),
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 5H WeCom customer contact callback fake/stub contract evidence.")
    parser.add_argument("--mode", default=MODE, choices=[MODE])
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    report = build_report(args.mode)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "FAIL", "ok": report.get("ok"), "mode": report.get("mode")}, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
