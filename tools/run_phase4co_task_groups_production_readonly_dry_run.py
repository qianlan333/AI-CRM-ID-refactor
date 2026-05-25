#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
APPROVAL_ENV = "AICRM_PHASE4CO_PRODUCTION_READONLY_DRY_RUN_APPROVED"
CONFIG_REVIEW_ENV = "AICRM_PHASE4CO_PRODUCTION_CONFIG_REVIEWED"
DB_ENV = "AICRM_TASK_GROUPS_READONLY_DRY_RUN_DATABASE_URL"
BACKEND_ENV = "AICRM_TASK_GROUPS_REPO_BACKEND"
OPERATOR_ENV = "AICRM_PHASE4CO_PRODUCTION_READONLY_DRY_RUN_OPERATOR"
ROUTE_FAMILY = "/api/admin/automation-conversion/task-groups*"


def _redact_url(raw_url: str | None) -> str | None:
    if not raw_url:
        return None
    parsed = urlparse(raw_url)
    if not parsed.netloc:
        return "<redacted>"
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    netloc = f"<redacted>@{host}" if parsed.username or parsed.password else host
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def _side_effect_safety() -> dict[str, bool]:
    return {
        "production_write_attempted": False,
        "create_update_delete_executed": False,
        "external_calls_executed": False,
        "timer_execution_executed": False,
        "workflow_execution_executed": False,
        "task_execution_executed": False,
        "outbound_send_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _base_report(args: argparse.Namespace) -> dict[str, Any]:
    db_url = os.environ.get(DB_ENV)
    return {
        "ok": True,
        "status": "phase_4co_task_groups_production_readonly_dry_run_readiness",
        "timestamp": datetime.now(UTC).isoformat(),
        "route_family": ROUTE_FAMILY,
        "bundle_type": "production_read_only_dry_run_readiness_bundle",
        "execution": {
            "result_status": "",
            "read_only_dry_run_attempted": False,
            "read_only_dry_run_executed": False,
            "approval_present": os.environ.get(APPROVAL_ENV) == "1",
            "config_reviewed": os.environ.get(CONFIG_REVIEW_ENV) == "1",
            "dry_run_db_present": bool(db_url),
            "read_only_flags_present": bool(args.read_only and args.confirm_no_writes),
            "not_executed_reason": "",
            "writes_attempted": False,
            "db_connection_attempted": False,
        },
        "evidence": {
            "db_url_env": DB_ENV,
            "db_url_redacted": _redact_url(db_url),
            "db_url_secret_redacted": True,
            "database_url_fallback_used": False,
            "test_or_staging_db_fallback_used": False,
            "route_owner_changed": False,
            "production_compat_changed": False,
            "fallback_retained": True,
            "raw_payload_exported": False,
            "raw_pii_exported": False,
        },
        "read_parity_summary": {},
        "skipped_details": [],
        "failed_details": [],
        "side_effect_safety": _side_effect_safety(),
        "operator": os.environ.get(OPERATOR_ENV) or "",
        "production_data_written": False,
        "production_repository_route_enabled": False,
    }


def _block(report: dict[str, Any], result_status: str, reason: str) -> dict[str, Any]:
    report["execution"]["result_status"] = result_status
    report["execution"]["not_executed_reason"] = reason
    report["skipped_details"] = [{"name": "phase4co_readiness_gate", "status": result_status, "reason": reason}]
    return report


def _read_only_summary(db_url: str) -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path[:0] = [str(ROOT)]
    from sqlalchemy import create_engine

    from aicrm_next.automation_engine.task_group_sqlalchemy_repository import (
        SqlAlchemyTaskGroupRepository,
    )

    engine = create_engine(db_url, future=True)
    repo = SqlAlchemyTaskGroupRepository(engine)
    rows, total = repo.list_task_groups({"limit": 50, "offset": 0, "include_archived": False})
    return {
        "task_groups_list_read": {
            "status": "passed",
            "total": int(total or 0),
            "item_count": len(rows),
            "shape_keys": sorted(rows[0].keys()) if rows else [],
            "notes": "redacted count and shape summary only; raw rows not exported",
        }
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = _base_report(args)
    db_url = os.environ.get(DB_ENV)
    if os.environ.get(APPROVAL_ENV) != "1":
        return _block(report, "not_executed_missing_approval", f"{APPROVAL_ENV}=1 is required")
    if os.environ.get(CONFIG_REVIEW_ENV) != "1":
        return _block(report, "not_executed_config_not_reviewed", f"{CONFIG_REVIEW_ENV}=1 is required")
    if not db_url:
        return _block(report, "not_executed_missing_dry_run_db", f"{DB_ENV} is required")
    if not args.read_only or not args.confirm_no_writes:
        return _block(report, "not_executed_read_only_flags_missing", "--read-only and --confirm-no-writes are required")
    if (os.environ.get(BACKEND_ENV) or "").strip().lower() != "sqlalchemy":
        return _block(report, "not_executed_backend_not_enabled", f"{BACKEND_ENV}=sqlalchemy is required")

    try:
        report["execution"]["read_only_dry_run_attempted"] = True
        report["execution"]["db_connection_attempted"] = True
        report["read_parity_summary"] = _read_only_summary(db_url)
        report["execution"]["result_status"] = "read_only_dry_run_executed"
        report["execution"]["read_only_dry_run_executed"] = True
        return report
    except Exception as exc:  # noqa: BLE001 - runner emits controlled evidence.
        report["ok"] = False
        report["execution"]["result_status"] = "not_executed_safety_failed"
        report["failed_details"].append({"name": "read_only_runner", "status": "failed", "reason": str(exc), "type": type(exc).__name__})
        return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    execution = report.get("execution") or {}
    evidence = report.get("evidence") or {}
    lines = [
        "# Phase 4CO Task Groups Production Read-Only Dry-Run Readiness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {execution.get('result_status')}",
        f"- read_only_dry_run_attempted: {str(execution.get('read_only_dry_run_attempted')).lower()}",
        f"- read_only_dry_run_executed: {str(execution.get('read_only_dry_run_executed')).lower()}",
        f"- writes_attempted: {str(execution.get('writes_attempted')).lower()}",
        f"- db_connection_attempted: {str(execution.get('db_connection_attempted')).lower()}",
        f"- db_url_redacted: {evidence.get('db_url_redacted') or 'none'}",
        f"- route_owner_changed: {str(evidence.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(evidence.get('production_compat_changed')).lower()}",
        f"- fallback_retained: {str(evidence.get('fallback_retained')).lower()}",
        "",
        "## Not Executed Reason",
        f"- {execution.get('not_executed_reason') or 'none'}",
        "",
        "## Read Parity Summary",
    ]
    summary = report.get("read_parity_summary") or {}
    if summary:
        for name, detail in summary.items():
            lines.append(f"- {name}: {detail.get('status')} - {detail.get('notes', '')}")
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 4CO task-groups production read-only dry-run readiness evidence.")
    parser.add_argument("--read-only", action="store_true")
    parser.add_argument("--confirm-no-writes", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = run(args)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"overall: {'PASS' if report.get('ok') else 'FAIL'}")
    print(f"result_status: {report.get('execution', {}).get('result_status')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
