#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
from typing import Any


STAGING_DB_ENV = "AICRM_WORKFLOW_NODES_STAGING_DATABASE_URL"
REPO_BACKEND_ENV = "AICRM_WORKFLOW_NODES_REPO_BACKEND"
SMOKE_APPROVAL_ENV = "AICRM_PHASE4CJ_STAGING_SMOKE_APPROVED"
WRITE_APPROVAL_ENV = "AICRM_PHASE4CJ_STAGING_WRITE_APPROVED"
ALLOWED_URL_MARKERS = {"staging", "stage", "test", "local", "sqlite", "dev"}
FORBIDDEN_URL_MARKERS = {"prod", "production", "primary", "master", "live"}
SIDE_EFFECT_SAFETY = {
    "production_data_used": False,
    "production_write_executed": False,
    "production_route_owner_changed": False,
    "fallback_removed": False,
    "real_external_call_executed": False,
    "timer_execution_executed": False,
    "workflow_execution_executed": False,
    "task_execution_executed": False,
    "outbound_send_executed": False,
}


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _redact_url(value: str) -> str:
    if not value:
        return ""
    if "://" in value and "@" in value:
        scheme, rest = value.split("://", 1)
        return f"{scheme}://<redacted>@{rest.split('@', 1)[1]}"
    return value[:16] + "<redacted>" if len(value) > 24 else "<redacted>"


def db_url_safety(db_url: str | None = None) -> dict[str, Any]:
    value = str(db_url if db_url is not None else os.getenv(STAGING_DB_ENV, "") or "").strip()
    normalized = value.lower()
    allowed_hits = sorted(marker for marker in ALLOWED_URL_MARKERS if marker in normalized)
    forbidden_hits = sorted(
        marker
        for marker in FORBIDDEN_URL_MARKERS
        if re.search(rf"(^|[^a-z]){re.escape(marker)}([^a-z]|$)", normalized)
    )
    present = bool(value)
    safe = present and bool(allowed_hits) and not forbidden_hits
    if not present:
        reason = "missing_staging_db_url"
    elif forbidden_hits:
        reason = "forbidden_marker_present"
    elif not allowed_hits:
        reason = "missing_allowed_marker"
    else:
        reason = "safe_staging_db_url"
    return {
        "present": present,
        "safe": safe,
        "reason": reason,
        "allowed_hits": allowed_hits,
        "forbidden_hits": forbidden_hits,
        "redacted_url": _redact_url(value),
    }


def _report(*, ok: bool, result_status: str, details: list[dict[str, Any]], execute_writes: bool) -> dict[str, Any]:
    return {
        "ok": ok,
        "result_status": result_status,
        "route_family": "/api/admin/automation-conversion/workflow-nodes*",
        "bundle_type": "staging_readiness_bundle",
        "staging_smoke_executed": False,
        "staging_write_executed": False,
        "db_connection_attempted": False,
        "execute_writes_requested": execute_writes,
        "write_approved": _truthy_env(WRITE_APPROVAL_ENV),
        "ready_for_staging_smoke_execution": result_status == "staging_readiness_preflight_passed_no_execution",
        "production_approval_claimed": False,
        "route_switch_ready": False,
        "delete_ready": False,
        "db_url_safety": db_url_safety(),
        "side_effect_safety": dict(SIDE_EFFECT_SAFETY),
        "details": details,
    }


def run_preflight(*, execute_writes: bool = False) -> dict[str, Any]:
    safety = db_url_safety()
    if not safety["present"]:
        return _report(
            ok=True,
            result_status="not_executed_missing_staging_db",
            execute_writes=execute_writes,
            details=[{"name": STAGING_DB_ENV, "status": "skipped", "message": "missing route-specific staging DB URL"}],
        )
    if not safety["safe"]:
        return _report(
            ok=False,
            result_status="not_executed_db_url_safety_failed",
            execute_writes=execute_writes,
            details=[{"name": STAGING_DB_ENV, "status": "failed", "message": safety["reason"]}],
        )
    backend = str(os.getenv(REPO_BACKEND_ENV, "") or "").strip().lower()
    if backend != "sqlalchemy":
        return _report(
            ok=True,
            result_status="not_executed_missing_repo_backend",
            execute_writes=execute_writes,
            details=[{"name": REPO_BACKEND_ENV, "status": "skipped", "message": "backend must be explicitly sqlalchemy"}],
        )
    if not _truthy_env(SMOKE_APPROVAL_ENV):
        return _report(
            ok=True,
            result_status="not_executed_missing_staging_approval",
            execute_writes=execute_writes,
            details=[{"name": SMOKE_APPROVAL_ENV, "status": "skipped", "message": "staging approval flag is missing"}],
        )
    if execute_writes and not _truthy_env(WRITE_APPROVAL_ENV):
        return _report(
            ok=True,
            result_status="not_executed_write_approval_missing",
            execute_writes=execute_writes,
            details=[{"name": WRITE_APPROVAL_ENV, "status": "skipped", "message": "write smoke approval flag is missing"}],
        )
    return _report(
        ok=True,
        result_status="staging_readiness_preflight_passed_no_execution",
        execute_writes=execute_writes,
        details=[
            {"name": STAGING_DB_ENV, "status": "passed", "message": "route-specific staging DB URL passed marker checks"},
            {"name": REPO_BACKEND_ENV, "status": "passed", "message": "backend explicitly set to sqlalchemy"},
            {"name": SMOKE_APPROVAL_ENV, "status": "passed", "message": "staging smoke approval flag present"},
        ],
    )


def _write_outputs(report: dict[str, Any], output_json: str | None, output_md: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if output_md:
        lines = [
            "# Phase 4CJ Workflow Nodes Staging Readiness",
            "",
            f"- ok: {str(report['ok']).lower()}",
            f"- result_status: {report['result_status']}",
            f"- staging_smoke_executed: {str(report['staging_smoke_executed']).lower()}",
            f"- staging_write_executed: {str(report['staging_write_executed']).lower()}",
            f"- db_connection_attempted: {str(report['db_connection_attempted']).lower()}",
            f"- ready_for_staging_smoke_execution: {str(report['ready_for_staging_smoke_execution']).lower()}",
        ]
        Path(output_md).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute-writes", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args()
    report = run_preflight(execute_writes=args.execute_writes)
    _write_outputs(report, args.output_json, args.output_md)
    print(json.dumps(report, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
