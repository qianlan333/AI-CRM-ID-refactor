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
APPROVAL_ENV = "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"
CONFIG_REVIEW_ENV = "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"
PRODUCTION_DB_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"
BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
OPERATOR_ENV = "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_OPERATOR"
READ_CASES = ("catalog_read", "list_read", "options_read", "detail_read")


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
        "external_calls_executed": False,
        "automation_execution_executed": False,
        "outbound_send_executed": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "writes_attempted": False,
    }


def _base_report(*, args: argparse.Namespace) -> dict[str, Any]:
    database_url = os.environ.get(PRODUCTION_DB_ENV)
    approval = os.environ.get(APPROVAL_ENV) == "1"
    config_reviewed = os.environ.get(CONFIG_REVIEW_ENV) == "1"
    return {
        "ok": False,
        "execution_status": "",
        "read_only": True,
        "writes_attempted": False,
        "production_data_access_requested": False,
        "approval_flags": {
            APPROVAL_ENV: approval,
            CONFIG_REVIEW_ENV: config_reviewed,
        },
        "config_reviewed": config_reviewed,
        "db_url_redacted": _redact_url(database_url),
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_retained": True,
        "read_parity_summary": {name: {"status": "blocked", "notes": "runner did not start"} for name in READ_CASES},
        "failed": [],
        "skipped": [],
        "side_effect_safety": _side_effect_safety(),
        "operator": os.environ.get(OPERATOR_ENV) or "",
        "timestamp": datetime.now(UTC).isoformat(),
        "blocked_reason": "",
        "requested_args": {
            "read_only": bool(args.read_only),
            "confirm_no_writes": bool(args.confirm_no_writes),
        },
        "raw_payload_exported": False,
        "pii_exported": False,
    }


def _block(report: dict[str, Any], status: str, reason: str) -> dict[str, Any]:
    report["execution_status"] = status
    report["blocked_reason"] = reason
    report["failed"].append({"name": "safety_gate", "status": status, "reason": reason})
    report["read_parity_summary"] = {
        name: {"status": "blocked", "notes": reason}
        for name in READ_CASES
    }
    return report


def _summarize_template(template: dict[str, Any] | None) -> dict[str, Any]:
    if not template:
        return {"present": False}
    rules = template.get("rules") or {}
    categories = rules.get("categories") if isinstance(rules, dict) else []
    return {
        "present": True,
        "id": template.get("id"),
        "keys": sorted(str(key) for key in template.keys()),
        "category_count": len(categories or []),
        "status": template.get("status"),
        "warning_count": len(template.get("warnings") or []),
    }


def _run_read_only(database_url: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine

    from aicrm_next.automation_engine.profile_segment_repository import (
        SqlAlchemyProfileSegmentTemplateRepository,
    )

    engine = create_engine(database_url, future=True)
    repo = SqlAlchemyProfileSegmentTemplateRepository(engine)
    summary: dict[str, Any] = {}
    catalog = repo.profile_segment_template_catalog()
    summary["catalog_read"] = {
        "status": "passed",
        "total": int(catalog.get("total") or 0),
        "item_count": len(catalog.get("items") or []),
        "source_status": catalog.get("source_status"),
        "notes": "redacted count and shape summary only",
    }
    items, total = repo.list_profile_segment_templates(limit=50, offset=0)
    summary["list_read"] = {
        "status": "passed",
        "total": int(total or 0),
        "item_count": len(items),
        "shape_keys": sorted(items[0].keys()) if items else [],
        "notes": "raw rows not exported",
    }
    enabled_items, enabled_total = repo.list_profile_segment_templates(enabled_only=True, limit=50, offset=0)
    summary["options_read"] = {
        "status": "passed",
        "enabled_total": int(enabled_total or 0),
        "sample_category_count": len(((enabled_items[0].get("rules") or {}).get("categories") or [])) if enabled_items else 0,
        "notes": "options projection summarized from enabled template categories",
    }
    if items:
        detail = repo.get_profile_segment_template(int(items[0]["id"]))
        summary["detail_read"] = {
            "status": "passed",
            "template": _summarize_template(detail),
            "notes": "detail payload shape summarized without raw payload export",
        }
    else:
        summary["detail_read"] = {
            "status": "skipped",
            "notes": "no template row available for detail read",
        }
    return summary


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = _base_report(args=args)
    database_url = os.environ.get(PRODUCTION_DB_ENV)

    if os.environ.get(APPROVAL_ENV) != "1":
        return _block(report, "not_executed_missing_approval", f"{APPROVAL_ENV}=1 is required")
    if os.environ.get(CONFIG_REVIEW_ENV) != "1":
        return _block(report, "not_executed_config_not_reviewed", f"{CONFIG_REVIEW_ENV}=1 is required")
    if not database_url:
        return _block(report, "not_executed_missing_production_db", f"{PRODUCTION_DB_ENV} is required")
    if not args.read_only or not args.confirm_no_writes:
        return _block(report, "not_executed_read_only_flags_missing", "--read-only and --confirm-no-writes are required")
    if (os.environ.get(BACKEND_ENV) or "").strip().lower() != "sqlalchemy":
        return _block(report, "not_executed_safety_failed", f"{BACKEND_ENV}=sqlalchemy is required")

    try:
        report["production_data_access_requested"] = True
        report["read_parity_summary"] = _run_read_only(database_url)
        failed = [
            {"name": name, **detail}
            for name, detail in report["read_parity_summary"].items()
            if detail.get("status") == "failed"
        ]
        skipped = [
            {"name": name, **detail}
            for name, detail in report["read_parity_summary"].items()
            if detail.get("status") == "skipped"
        ]
        report["failed"] = failed
        report["skipped"] = skipped
        report["execution_status"] = "read_only_dry_run_executed"
        report["ok"] = not failed
        return report
    except Exception as exc:  # noqa: BLE001 - runner reports controlled evidence.
        report["execution_status"] = "not_executed_safety_failed"
        report["failed"].append({"name": "read_only_runner", "status": "failed", "reason": str(exc), "type": type(exc).__name__})
        return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4R Profile Segment Template Production Read-Only Dry-Run",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- execution_status: {report.get('execution_status')}",
        f"- read_only: {str(report.get('read_only')).lower()}",
        f"- writes_attempted: {str(report.get('writes_attempted')).lower()}",
        f"- production_data_access_requested: {str(report.get('production_data_access_requested')).lower()}",
        f"- db_url_redacted: {report.get('db_url_redacted') or 'none'}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        f"- fallback_retained: {str(report.get('fallback_retained')).lower()}",
        "",
        "## Read Parity Summary",
    ]
    for name, detail in (report.get("read_parity_summary") or {}).items():
        lines.append(f"- {name}: {detail.get('status')} - {detail.get('notes', '')}")
    lines.extend(["", "## Blocked Reason", f"- {report.get('blocked_reason') or 'none'}", ""])
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4R profile segment template production read-only dry-run evidence.")
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
    print(f"overall: {'PASS' if report.get('ok') else 'BLOCKED'}")
    print(f"execution_status: {report.get('execution_status')}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
