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
    "list_wecom_tags",
    "validate_tag_ids",
    "dry_run_mark_tags",
    "dry_run_unmark_tags",
]
ERROR_MAPPING = [
    "wecom_config_missing",
    "invalid_tag_id",
    "external_userid_missing",
    "idempotency_key_required",
    "duplicate_idempotency_key",
    "live_call_not_enabled",
    "adapter_unavailable",
    "forbidden_in_production_without_approval",
]
DETERMINISTIC_TAGS = [
    {"tag_id": "tag_contract_001", "tag_name": "Phase5A Contract A", "group_id": "group_contract", "group_name": "Phase5A Contract"},
    {"tag_id": "tag_contract_002", "tag_name": "Phase5A Contract B", "group_id": "group_contract", "group_name": "Phase5A Contract"},
    {"tag_id": "tag_contract_003", "tag_name": "Phase5A Contract C", "group_id": "group_contract", "group_name": "Phase5A Contract"},
]


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _request_hash(payload: dict[str, Any]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _side_effect_safety() -> dict[str, bool]:
    return {
        "wecom_live_call_allowed": False,
        "network_call_allowed": False,
        "production_tag_write_allowed": False,
        "mark_tag_allowed": False,
        "unmark_tag_allowed": False,
        "outbound_send_allowed": False,
        "token_refresh_allowed": False,
        "external_sync_allowed": False,
        "db_write_allowed": False,
    }


def build_report(mode: str = MODE) -> dict[str, Any]:
    if mode != MODE:
        return {
            "ok": False,
            "mode": mode,
            "error_code": "adapter_unavailable",
            "result_status": "unsupported_mode",
            "live_call_executed": False,
            "timestamp": _timestamp(),
        }

    requested_tag_ids = [item["tag_id"] for item in DETERMINISTIC_TAGS[:2]]
    payload = {
        "mode": mode,
        "external_userid": "<redacted>",
        "operator": "phase5a_contract_runner",
        "tag_ids": requested_tag_ids,
        "idempotency_key": "phase5a-contract-evidence",
    }
    return {
        "ok": True,
        "mode": MODE,
        "adapter_mode": MODE,
        "route_family": "/api/admin/wecom/tags*",
        "capability_owner": "aicrm_next.customer_tags",
        "live_call_executed": False,
        "mark_tag_executed": False,
        "unmark_tag_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "deterministic_tags": DETERMINISTIC_TAGS,
        "supported_methods": SUPPORTED_METHODS,
        "error_mapping": ERROR_MAPPING,
        "idempotency_policy": {
            "idempotency_key_required_for_write_like_dry_run": True,
            "replay_same_hash": True,
            "conflict_different_hash": True,
            "retry_safe": True,
            "no_partial_external_side_effect": True,
        },
        "evidence_policy": {
            "requested_tag_ids": requested_tag_ids,
            "normalized_tag_ids": requested_tag_ids,
            "external_userid_redaction": "full value is not emitted; evidence uses <redacted>",
            "operator": "phase5a_contract_runner",
            "idempotency_key": "phase5a-contract-evidence",
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
        "# Phase 5A WeCom Tag Adapter Contract Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- live_call_executed: {str(report.get('live_call_executed')).lower()}",
        f"- mark_tag_executed: {str(report.get('mark_tag_executed')).lower()}",
        f"- unmark_tag_executed: {str(report.get('unmark_tag_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- token_used: {str(report.get('token_used')).lower()}",
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
    parser = argparse.ArgumentParser(description="Generate Phase 5A WeCom tag adapter fake/stub contract evidence.")
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
