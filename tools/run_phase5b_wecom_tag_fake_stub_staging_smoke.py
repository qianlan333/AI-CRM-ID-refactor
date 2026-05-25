#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.customer_tags.application import WeComTagApplicationService
from aicrm_next.customer_tags.wecom_tag_adapter import build_fake_stub_wecom_tag_adapter


APPROVAL_ENV = "AICRM_PHASE5B_WECOM_TAG_STAGING_SMOKE_APPROVED"


def _timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _blocked(reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "status": "blocked_not_executed",
        "result_status": "blocked_not_executed",
        "reason": reason,
        "staging_fake_stub_evidence": {},
        "live_call_executed": False,
        "token_used": False,
        "network_call_executed": False,
        "timestamp": _timestamp(),
    }


def build_report() -> dict[str, Any]:
    if os.getenv(APPROVAL_ENV) != "1":
        return _blocked(f"{APPROVAL_ENV}=1 is required")
    service = WeComTagApplicationService(build_fake_stub_wecom_tag_adapter())
    listed = service.list_wecom_tags()
    marked = service.dry_run_mark_tags(
        external_userid="external_userid_phase5b_staging",
        tag_ids=["tag_contract_001", "tag_contract_002"],
        operator="phase5b_staging_smoke",
        idempotency_key="phase5b-staging-mark",
    )
    unmarked = service.dry_run_unmark_tags(
        external_userid="external_userid_phase5b_staging",
        tag_ids=["tag_contract_002"],
        operator="phase5b_staging_smoke",
        idempotency_key="phase5b-staging-unmark",
    )
    return {
        "ok": bool(listed.get("ok") and marked.get("ok") and unmarked.get("ok")),
        "status": "staging_fake_stub_evidence",
        "result_status": "staging_fake_stub_evidence",
        "staging_fake_stub_evidence": {
            "list_wecom_tags": listed,
            "dry_run_mark_tags": marked,
            "dry_run_unmark_tags": unmarked,
        },
        "live_call_executed": False,
        "token_used": False,
        "network_call_executed": False,
        "production_behavior_changed": False,
        "timestamp": _timestamp(),
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 5B WeCom Tag Fake/Stub Staging Smoke",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- status: {report.get('status')}",
        f"- live_call_executed: {str(report.get('live_call_executed')).lower()}",
        f"- token_used: {str(report.get('token_used')).lower()}",
        f"- network_call_executed: {str(report.get('network_call_executed')).lower()}",
        f"- reason: {report.get('reason') or 'none'}",
    ]
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 5B WeCom tag fake/stub staging smoke evidence.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(json.dumps({"overall": "PASS" if report.get("ok") else "FAIL", "ok": report.get("ok"), "status": report.get("status")}, ensure_ascii=False))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
