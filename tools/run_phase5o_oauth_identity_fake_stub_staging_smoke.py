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

from aicrm_next.integration_gateway.oauth_identity_adapter import DETERMINISTIC_OAUTH_EVENTS
from aicrm_next.integration_gateway.oauth_identity_application import build_oauth_identity_application_service, reset_oauth_identity_fake_stub_state

APPROVAL_ENV = "AICRM_PHASE5O_OAUTH_IDENTITY_STAGING_SMOKE_APPROVED"


def _safety() -> dict[str, bool]:
    return {"live_oauth_callback_cutover_allowed": False, "token_exchange_allowed": False, "network_call_allowed": False, "session_write_allowed": False, "db_write_allowed": False, "outbound_send_allowed": False}


def build_report() -> dict[str, Any]:
    approved = os.getenv(APPROVAL_ENV) == "1"
    report: dict[str, Any] = {
        "ok": approved,
        "mode": "staging_fake_stub_smoke",
        "result_status": "staging_fake_stub_evidence" if approved else "blocked_missing_staging_smoke_approval",
        "approval_env": APPROVAL_ENV,
        "approval_present": approved,
        "live_oauth_call_executed": False,
        "live_callback_processed": False,
        "code_exchange_executed": False,
        "production_session_write_executed": False,
        "production_identity_write_executed": False,
        "outbound_send_executed": False,
        "token_used": False,
        "network_call_executed": False,
        "db_write_executed": False,
        "production_behavior_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "side_effect_safety": _safety(),
    }
    if not approved:
        report["deterministic_oauth_events"] = []
        return report
    reset_oauth_identity_fake_stub_state()
    service = build_oauth_identity_application_service()
    event = DETERMINISTIC_OAUTH_EVENTS[0]
    report.update(
        {
            "deterministic_oauth_events": service._adapter.deterministic_oauth_events()["events"],  # type: ignore[attr-defined]
            "authorize_result": service.build_oauth_authorize_url_contract(slug=event["slug"], state=event["state"], redirect_uri=event["redirect_uri"]),
            "parse_result": service.parse_oauth_callback_contract(code=event["code"], state=event["state"], openid=event["openid"], unionid=event["unionid"]),
            "record_result": service.dry_run_record_oauth_identity(event=event, operator="phase5o_staging_fake_stub_runner", idempotency_key="phase5o-staging-record"),
            "session_result": service.dry_run_session_identity_evidence(event=DETERMINISTIC_OAUTH_EVENTS[1], operator="phase5o_staging_fake_stub_runner", idempotency_key="phase5o-staging-session"),
        }
    )
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(f"# Phase 5O OAuth Identity Fake/Stub Staging Smoke\n\n- ok: {str(report.get('ok')).lower()}\n- result_status: {report.get('result_status')}\n- live_oauth_call_executed: false\n- production_session_write_executed: false\n- production_identity_write_executed: false\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
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
