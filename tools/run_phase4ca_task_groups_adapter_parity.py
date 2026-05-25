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

from aicrm_next.automation_engine.repo import TASK_GROUP_TEST_DATABASE_URL_ENV, build_automation_repository


FORBIDDEN_URL_MARKERS = {"prod", "production", "primary", "master", "live"}
ALLOWED_URL_MARKERS = {"test", "local", "sqlite", "fixture", "ci", "dev", "tmp"}


def _url_safety(url: str) -> dict[str, Any]:
    normalized = url.lower()
    allowed_hits = sorted(marker for marker in ALLOWED_URL_MARKERS if marker in normalized)
    forbidden_hits = sorted(marker for marker in FORBIDDEN_URL_MARKERS if re.search(rf"(^|[^a-z]){re.escape(marker)}([^a-z]|$)", normalized))
    return {
        "ok": bool(url.strip()) and bool(allowed_hits) and not forbidden_hits,
        "allowed_hits": allowed_hits,
        "forbidden_hits": forbidden_hits,
    }


def _side_effect_safety_false(payload: dict[str, Any]) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for value in safety.values())


def run_harness() -> dict[str, Any]:
    db_url = str(os.getenv(TASK_GROUP_TEST_DATABASE_URL_ENV) or "").strip()
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
    repo = build_automation_repository(task_group_backend="sqlalchemy", task_group_engine=engine)
    rows, total = repo.list_task_groups({"program_id": 1, "limit": 20, "offset": 0})
    details.append({"name": "list_task_groups", "status": "passed", "total": total, "row_count": len(rows)})
    payload = {
        "program_id": 9,
        "group_name": "Phase 4CA adapter parity",
        "group_code": "phase4ca_adapter_parity",
        "metadata": {"source": "phase4ca_test_db"},
        "operator": "phase4ca",
    }
    created = repo.create_task_group(payload, idempotency_key="phase4ca-create", operator="phase4ca")
    replay = repo.create_task_group(payload, idempotency_key="phase4ca-create", operator="phase4ca")
    audit_events = repo.list_task_group_audit_events()
    checks = {
        "create_with_idempotency": created.get("idempotent_replay") is False,
        "idempotency_replay": replay.get("idempotent_replay") is True and replay["group"]["id"] == created["group"]["id"],
        "audit_event_emitted": bool(audit_events),
        "rollback_payload_present": created.get("rollback_payload", {}).get("delete_approved") is False,
        "side_effect_safety_false": _side_effect_safety_false(created.get("audit_event") or {}),
    }
    for name, passed in checks.items():
        details.append({"name": name, "status": "passed" if passed else "failed"})
    ok = all(item["status"] == "passed" for item in details)
    return {
        "ok": ok,
        "result_status": "passed" if ok else "failed",
        "adapter_smoke_executed": True,
        "production_data_used": False,
        "route_switch_ready": False,
        "db_url_safety": safety,
        "side_effect_safety": (created.get("audit_event") or {}).get("side_effect_safety") or {},
        "details": details,
    }


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CA Task Groups Adapter Parity Harness",
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
