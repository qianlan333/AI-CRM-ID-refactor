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
APPROVAL_ENV = "AICRM_PHASE4CS_PRODUCTION_READONLY_DRY_RUN_APPROVED"
CONFIG_REVIEW_ENV = "AICRM_PHASE4CS_PRODUCTION_CONFIG_REVIEWED"
BACKEND_ENV = "AICRM_AGENT_RUNS_REPO_BACKEND"
DB_ENV = "AICRM_AGENT_RUNS_READONLY_DRY_RUN_DATABASE_URL"
ROUTE_FAMILY = "/api/admin/automation-conversion/agent-runs*"


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
        "timer_execution_triggered": False,
        "workflow_execution_triggered": False,
        "task_execution_triggered": False,
        "agent_execution_triggered": False,
        "run_due_triggered": False,
        "outbound_send_triggered": False,
        "llm_call_triggered": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
    }


def _base_report(args: argparse.Namespace) -> dict[str, Any]:
    db_url = os.environ.get(DB_ENV)
    safety = _side_effect_safety()
    return {
        "ok": True,
        "status": "phase_4cs_agent_runs_production_readonly_dry_run_readiness",
        "timestamp": datetime.now(UTC).isoformat(),
        "route_family": ROUTE_FAMILY,
        "bundle_type": "production_readonly_dry_run_readiness_bundle",
        "result_status": "",
        "production_dry_run_executed": False,
        "db_connected": False,
        "writes_attempted": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "agent_execution_triggered": False,
        "workflow_execution_triggered": False,
        "outbound_send_triggered": False,
        "llm_call_triggered": False,
        "execution": {
            "result_status": "",
            "read_only_dry_run_attempted": False,
            "production_dry_run_executed": False,
            "approval_present": os.environ.get(APPROVAL_ENV) == "1",
            "config_reviewed": os.environ.get(CONFIG_REVIEW_ENV) == "1",
            "backend_sqlalchemy": (os.environ.get(BACKEND_ENV) or "").strip().lower() == "sqlalchemy",
            "dry_run_db_present": bool(db_url),
            "read_only_flags_present": bool(args.read_only and args.confirm_no_writes),
            "not_executed_reason": "",
            "writes_attempted": False,
            "db_connected": False,
        },
        "evidence": {
            "db_url_env": DB_ENV,
            "db_url_redacted": _redact_url(db_url),
            "db_url_secret_redacted": True,
            "route_specific_readonly_db_required": True,
            "database_url_fallback_used": False,
            "test_or_staging_db_fallback_used": False,
            "fixture_local_demo_fallback_used": False,
            "shared_settings_database_url_used": False,
            "route_owner_changed": False,
            "production_compat_changed": False,
            "fallback_retained": True,
            "raw_payload_exported": False,
            "raw_pii_exported": False,
        },
        "read_only_summary": {},
        "skipped_details": [],
        "failed_details": [],
        "side_effect_safety": safety,
        "production_data_written": False,
        "production_repository_route_enabled": False,
    }


def _block(report: dict[str, Any], result_status: str, reason: str) -> dict[str, Any]:
    report["result_status"] = result_status
    report["execution"]["result_status"] = result_status
    report["execution"]["not_executed_reason"] = reason
    report["skipped_details"] = [{"name": "phase4cs_readiness_gate", "status": result_status, "reason": reason}]
    return report


def _read_only_summary(db_url: str) -> dict[str, Any]:
    if str(ROOT) not in sys.path:
        sys.path[:0] = [str(ROOT)]
    from sqlalchemy import create_engine

    from aicrm_next.automation_engine.agent_run_sqlalchemy_repository import SqlAlchemyAgentRunRepository

    engine = create_engine(db_url, future=True)
    repo = SqlAlchemyAgentRunRepository(engine)
    rows, total, filters = repo.list_agent_runs({"page_size": 50, "offset": 0, "visibility": "internal"})
    keys = sorted(rows[0].keys()) if rows else []
    return {
        "agent_runs_list_read": {
            "status": "passed",
            "total": int(total or 0),
            "item_count": len(rows),
            "shape_keys": keys,
            "redacted_field_presence_summary": keys,
            "normalized_filter_keys": sorted(filters.keys()),
            "notes": "count and redacted field presence only; raw rows and PII are not exported",
        }
    }


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = _base_report(args)
    db_url = os.environ.get(DB_ENV)
    if os.environ.get(APPROVAL_ENV) != "1":
        return _block(report, "not_executed_missing_approval", f"{APPROVAL_ENV}=1 is required")
    if os.environ.get(CONFIG_REVIEW_ENV) != "1":
        return _block(report, "not_executed_config_not_reviewed", f"{CONFIG_REVIEW_ENV}=1 is required")
    if (os.environ.get(BACKEND_ENV) or "").strip().lower() != "sqlalchemy":
        return _block(report, "not_executed_backend_not_enabled", f"{BACKEND_ENV}=sqlalchemy is required")
    if not db_url:
        return _block(report, "not_executed_missing_database_url", f"{DB_ENV} is required")
    if not args.read_only or not args.confirm_no_writes:
        return _block(report, "not_executed_read_only_flags_missing", "--read-only and --confirm-no-writes are required")

    try:
        report["execution"]["read_only_dry_run_attempted"] = True
        report["read_only_summary"] = _read_only_summary(db_url)
        report["result_status"] = "read_only_dry_run_executed"
        report["execution"]["result_status"] = "read_only_dry_run_executed"
        report["execution"]["production_dry_run_executed"] = True
        report["execution"]["db_connected"] = True
        report["production_dry_run_executed"] = True
        report["db_connected"] = True
        return report
    except Exception as exc:  # noqa: BLE001 - runner emits controlled evidence.
        report["ok"] = False
        report["result_status"] = "not_executed_safety_failed"
        report["execution"]["result_status"] = "not_executed_safety_failed"
        report["failed_details"].append({"name": "read_only_runner", "status": "failed", "reason": str(exc), "type": type(exc).__name__})
        return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    execution = report.get("execution") or {}
    evidence = report.get("evidence") or {}
    lines = [
        "# Phase 4CS Agent Runs Production Read-Only Dry-Run Readiness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {report.get('result_status')}",
        f"- production_dry_run_executed: {str(report.get('production_dry_run_executed')).lower()}",
        f"- db_connected: {str(report.get('db_connected')).lower()}",
        f"- writes_attempted: {str(report.get('writes_attempted')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_removed: {str(report.get('fallback_removed')).lower()}",
        f"- agent_execution_triggered: {str(report.get('agent_execution_triggered')).lower()}",
        f"- workflow_execution_triggered: {str(report.get('workflow_execution_triggered')).lower()}",
        f"- outbound_send_triggered: {str(report.get('outbound_send_triggered')).lower()}",
        f"- llm_call_triggered: {str(report.get('llm_call_triggered')).lower()}",
        f"- db_url_redacted: {evidence.get('db_url_redacted') or 'none'}",
        "",
        "## Gate Status",
        f"- approval_present: {str(execution.get('approval_present')).lower()}",
        f"- config_reviewed: {str(execution.get('config_reviewed')).lower()}",
        f"- backend_sqlalchemy: {str(execution.get('backend_sqlalchemy')).lower()}",
        f"- dry_run_db_present: {str(execution.get('dry_run_db_present')).lower()}",
        f"- read_only_flags_present: {str(execution.get('read_only_flags_present')).lower()}",
        "",
        "## Not Executed Reason",
        f"- {execution.get('not_executed_reason') or 'none'}",
        "",
        "## Read-Only Summary",
    ]
    summary = report.get("read_only_summary") or {}
    if summary:
        for name, detail in summary.items():
            lines.append(f"- {name}: {detail.get('status')} - total={detail.get('total')} item_count={detail.get('item_count')}")
    else:
        lines.append("- none")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 4CS agent-runs production read-only dry-run readiness evidence.")
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
    print(f"result_status: {report.get('result_status')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
