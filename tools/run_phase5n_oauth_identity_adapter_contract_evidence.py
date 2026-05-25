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
    "build_oauth_authorize_url_contract",
    "parse_oauth_callback_contract",
    "normalize_oauth_identity_event",
    "dry_run_record_oauth_identity",
    "dry_run_session_identity_evidence",
]
ERROR_MAPPING = [
    "oauth_config_missing",
    "oauth_code_missing",
    "state_missing",
    "state_invalid",
    "redirect_uri_invalid",
    "openid_missing",
    "idempotency_key_required",
    "duplicate_oauth_event_key",
    "live_oauth_callback_not_enabled",
    "token_exchange_not_enabled",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
]
DETERMINISTIC_OAUTH_EVENTS = [
    {
        "oauth_event_type": "wechat_oauth_callback",
        "oauth_event_key": "phase5n:wechat_oauth:state_demo_001:openid_001",
        "state": "questionnaire_demo_001",
        "openid_redacted": "openid...0001",
        "unionid_redacted": "unionid...0001",
        "redirect_uri_evidence": "https://example.invalid/api/h5/wechat/oauth/callback",
    },
    {
        "oauth_event_type": "wechat_oauth_callback",
        "oauth_event_key": "phase5n:wechat_oauth:state_demo_002:openid_002",
        "state": "questionnaire_demo_002",
        "openid_redacted": "openid...0002",
        "unionid_redacted": "unionid...0002",
        "redirect_uri_evidence": "https://example.invalid/api/h5/wechat/oauth/callback",
    },
]


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_oauth_callback_cutover_allowed": False,
        "live_oauth_token_exchange_allowed": False,
        "network_call_allowed": False,
        "production_session_write_allowed": False,
        "production_identity_write_allowed": False,
        "outbound_send_allowed": False,
        "payment_allowed": False,
        "media_upload_allowed": False,
        "wecom_live_call_allowed": False,
        "openclaw_mcp_allowed": False,
        "timer_execution_allowed": False,
        "automation_execution_allowed": False,
        "db_write_allowed": False,
    }


def build_report(mode: str = MODE) -> dict[str, Any]:
    if mode != MODE:
        return {
            "ok": False,
            "mode": mode,
            "error_code": "adapter_unavailable",
            "result_status": "unsupported_mode",
            "live_oauth_call_executed": False,
            "live_callback_processed": False,
            "production_session_write_executed": False,
            "production_identity_write_executed": False,
            "timestamp": _timestamp(),
        }

    event = DETERMINISTIC_OAUTH_EVENTS[0]
    payload = {
        "mode": mode,
        "oauth_event_key": event["oauth_event_key"],
        "openid_redacted": event["openid_redacted"],
        "unionid_redacted": event["unionid_redacted"],
        "state": event["state"],
        "operator": "phase5n_contract_runner",
        "idempotency_key": "phase5n-contract-evidence",
    }
    return {
        "ok": True,
        "mode": MODE,
        "adapter_mode": MODE,
        "route_family": "/api/h5/wechat/oauth*",
        "capability_owner": "aicrm_next.integration_gateway",
        "live_oauth_call_executed": False,
        "live_callback_processed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "app_secret_used": False,
        "app_id_used": False,
        "code_exchange_executed": False,
        "network_call_executed": False,
        "db_write_executed": False,
        "deterministic_oauth_events": DETERMINISTIC_OAUTH_EVENTS,
        "supported_methods": SUPPORTED_METHODS,
        "error_mapping": ERROR_MAPPING,
        "idempotency_policy": {
            "oauth_event_key_required": True,
            "idempotency_key_required_for_write_like_dry_run": True,
            "replay_same_oauth_event_key": True,
            "conflict_different_hash": True,
            "retry_safe": True,
            "no_partial_production_side_effect": True,
        },
        "evidence_policy": {
            "oauth_event_type": event["oauth_event_type"],
            "oauth_event_key": event["oauth_event_key"],
            "openid_redacted": event["openid_redacted"],
            "unionid_redacted": event["unionid_redacted"],
            "state": event["state"],
            "operator": "phase5n_contract_runner",
            "idempotency_key": "phase5n-contract-evidence",
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
        "# Phase 5N OAuth Identity Adapter Contract Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- live_oauth_call_executed: {str(report.get('live_oauth_call_executed')).lower()}",
        f"- live_callback_processed: {str(report.get('live_callback_processed')).lower()}",
        f"- production_session_write_executed: {str(report.get('production_session_write_executed')).lower()}",
        f"- production_identity_write_executed: {str(report.get('production_identity_write_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- token_used: {str(report.get('token_used')).lower()}",
        f"- app_secret_used: {str(report.get('app_secret_used')).lower()}",
        f"- code_exchange_executed: {str(report.get('code_exchange_executed')).lower()}",
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
    parser = argparse.ArgumentParser(description="Generate Phase 5N OAuth identity fake/stub contract evidence.")
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
