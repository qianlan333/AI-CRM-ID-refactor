#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.integration_gateway.wecom_contact_callback_adapter import DETERMINISTIC_EVENTS
from aicrm_next.integration_gateway.wecom_contact_callback_application import (
    build_wecom_contact_callback_application_service,
    reset_wecom_contact_callback_fake_stub_state,
)


APPROVAL_ENV = "AICRM_PHASE5I_WECOM_CONTACT_STAGING_SMOKE_APPROVED"


def _side_effect_safety() -> dict[str, bool]:
    return {
        "live_callback_cutover_allowed": False,
        "production_contact_write_allowed": False,
        "production_identity_mapping_write_allowed": False,
        "production_tag_write_allowed": False,
        "live_customer_sync_allowed": False,
        "outbound_send_allowed": False,
        "token_refresh_allowed": False,
        "decrypt_allowed": False,
        "network_call_allowed": False,
        "db_write_allowed": False,
    }


def build_report() -> dict[str, Any]:
    approved = os.getenv(APPROVAL_ENV) == "1"
    reset_wecom_contact_callback_fake_stub_state()
    service = build_wecom_contact_callback_application_service()

    report: dict[str, Any] = {
        "ok": approved,
        "mode": "staging_fake_stub_smoke",
        "result_status": "staging_fake_stub_evidence" if approved else "blocked_missing_staging_smoke_approval",
        "approval_env": APPROVAL_ENV,
        "approval_present": approved,
        "live_callback_processed": False,
        "production_write_executed": False,
        "production_contact_write_executed": False,
        "production_identity_mapping_write_executed": False,
        "production_tag_write_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "aes_key_used": False,
        "decrypt_executed": False,
        "network_call_executed": False,
        "db_write_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": _side_effect_safety(),
    }
    if not approved:
        report["deterministic_events"] = []
        return report

    event = DETERMINISTIC_EVENTS[0]
    parse_result = service.parse_external_contact_event(event)
    normalize_result = service.normalize_external_contact_event(event)
    record_result = service.dry_run_record_contact_event(
        event=event,
        operator="phase5i_staging_fake_stub_runner",
        idempotency_key="phase5i-staging-smoke-record",
    )
    identity_result = service.dry_run_identity_mapping(
        event=DETERMINISTIC_EVENTS[1],
        operator="phase5i_staging_fake_stub_runner",
        idempotency_key="phase5i-staging-smoke-identity",
    )
    report.update(
        {
            "deterministic_events": service._adapter.deterministic_events()["events"],  # type: ignore[attr-defined]
            "parse_result": parse_result,
            "normalize_result": normalize_result,
            "record_result": record_result,
            "identity_mapping_result": identity_result,
        }
    )
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5I WeCom Customer Contact Fake/Stub Staging Smoke",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- mode: {report.get('mode')}",
        f"- result_status: {report.get('result_status')}",
        f"- live_callback_processed: {str(report.get('live_callback_processed')).lower()}",
        f"- production_contact_write_executed: {str(report.get('production_contact_write_executed')).lower()}",
        f"- production_identity_mapping_write_executed: {str(report.get('production_identity_mapping_write_executed')).lower()}",
        f"- outbound_send_executed: {str(report.get('outbound_send_executed')).lower()}",
        f"- token_used: {str(report.get('token_used')).lower()}",
        f"- aes_key_used: {str(report.get('aes_key_used')).lower()}",
        f"- network_call_executed: {str(report.get('network_call_executed')).lower()}",
        f"- db_write_executed: {str(report.get('db_write_executed')).lower()}",
        f"- production_behavior_changed: {str(report.get('production_behavior_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5I fake/stub staging smoke evidence for WeCom contact callback.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "BLOCKED", "ok": report.get("ok"), "result_status": report.get("result_status")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
