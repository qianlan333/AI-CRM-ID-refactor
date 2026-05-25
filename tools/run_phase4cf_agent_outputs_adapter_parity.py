#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.automation_engine.repo import AGENT_OUTPUT_TEST_DATABASE_URL_ENV, build_automation_repository


FORBIDDEN_URL_MARKERS = {"prod", "production", "primary", "master", "live"}
ALLOWED_URL_MARKERS = {"test", "local", "sqlite", "fixture", "ci", "dev", "tmp"}


def _url_safety(url: str) -> dict[str, Any]:
    normalized = url.lower()
    allowed_hits = sorted(marker for marker in ALLOWED_URL_MARKERS if marker in normalized)
    forbidden_hits = sorted(
        marker
        for marker in FORBIDDEN_URL_MARKERS
        if re.search(rf"(^|[^a-z]){re.escape(marker)}([^a-z]|$)", normalized)
    )
    return {
        "ok": bool(url.strip()) and bool(allowed_hits) and not forbidden_hits,
        "allowed_hits": allowed_hits,
        "forbidden_hits": forbidden_hits,
    }


def run_harness() -> dict[str, Any]:
    db_url = str(os.getenv(AGENT_OUTPUT_TEST_DATABASE_URL_ENV) or "").strip()
    if not db_url:
        return {
            "ok": True,
            "result_status": "not_executed_missing_test_db",
            "adapter_smoke_executed": False,
            "production_data_used": False,
            "route_switch_ready": False,
            "db_url_safety": {"ok": False, "allowed_hits": [], "forbidden_hits": []},
            "details": [],
        }
    safety = _url_safety(db_url)
    if not safety["ok"]:
        return {
            "ok": False,
            "result_status": "blocked_unsafe_test_db_url",
            "adapter_smoke_executed": False,
            "production_data_used": False,
            "route_switch_ready": False,
            "db_url_safety": safety,
            "details": [],
        }

    details: list[dict[str, Any]] = []
    engine = create_engine(db_url, future=True)
    repo = build_automation_repository(agent_output_backend="sqlalchemy", agent_output_engine=engine)
    rows, total, filters = repo.list_agent_outputs(
        {"agent_code": "phase4bg_review_agent", "output_type": "reply_draft", "visibility": "console"}
    )
    details.append(
        {
            "name": "list_agent_outputs",
            "status": "passed" if total == 1 and len(rows) == 1 and filters["visibility"] == "console" else "failed",
            "total": total,
            "row_count": len(rows),
        }
    )
    detail = repo.get_agent_output("phase4cf_output_reply_draft", {"visibility": "console"})
    details.append(
        {
            "name": "get_agent_output_detail",
            "status": "passed" if detail and detail["output_id"] == "phase4cf_output_reply_draft" else "failed",
        }
    )
    missing = repo.get_agent_output("missing-output", {"visibility": "console"})
    details.append({"name": "missing_detail_returns_none", "status": "passed" if missing is None else "failed"})
    ok = all(item["status"] == "passed" for item in details)
    return {
        "ok": ok,
        "result_status": "passed" if ok else "failed",
        "adapter_smoke_executed": True,
        "production_data_used": False,
        "route_switch_ready": False,
        "db_url_safety": safety,
        "runtime_behavior_enabled": {
            "export_job_creation_enabled": False,
            "file_download_enabled": False,
            "agent_output_generation_enabled": False,
            "external_call_enabled": False,
        },
        "details": details,
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CF Agent Outputs Adapter Parity Harness",
            "",
            f"- ok: {str(report['ok']).lower()}",
            f"- result_status: {report['result_status']}",
            f"- adapter_smoke_executed: {str(report['adapter_smoke_executed']).lower()}",
            f"- production_data_used: {str(report['production_data_used']).lower()}",
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = run_harness()
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
