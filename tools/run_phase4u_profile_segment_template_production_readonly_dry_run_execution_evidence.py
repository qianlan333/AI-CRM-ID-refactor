#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
PHASE4S_TOOL = ROOT / "tools/run_phase4s_profile_segment_template_production_readonly_dry_run_evidence.py"
APPROVAL_ENV = "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"
CONFIG_REVIEW_ENV = "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"
BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
PRODUCTION_DB_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"
OPERATOR_ENV = "AICRM_PHASE4U_PRODUCTION_READONLY_DRY_RUN_OPERATOR"
RESULT_STATUSES = {
    "not_executed_missing_approval",
    "not_executed_config_not_reviewed",
    "not_executed_missing_production_db",
    "not_executed_read_only_flags_missing",
    "not_executed_safety_failed",
    "read_only_dry_run_executed",
}


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
        "create_update_delete_executed": False,
    }


def _base_report(args: argparse.Namespace) -> dict[str, Any]:
    production_db_url = os.environ.get(PRODUCTION_DB_ENV)
    approval_present = os.environ.get(APPROVAL_ENV) == "1"
    config_reviewed = os.environ.get(CONFIG_REVIEW_ENV) == "1"
    read_only_flags_present = bool(args.read_only and args.confirm_no_writes)
    return {
        "ok": True,
        "status": "phase_4u_production_readonly_dry_run_execution_evidence_no_route_switch",
        "timestamp": datetime.now(UTC).isoformat(),
        "command": "tools/run_phase4u_profile_segment_template_production_readonly_dry_run_execution_evidence.py",
        "execution": {
            "result_status": "",
            "attempted": False,
            "lower_runner_called": False,
            "read_only_dry_run_executed": False,
            "approval_present": approval_present,
            "config_reviewed": config_reviewed,
            "production_db_present": bool(production_db_url),
            "read_only_flags_present": read_only_flags_present,
            "not_executed_reason": "",
            "writes_attempted": False,
        },
        "evidence": {
            "command_attempted_or_not_attempted_reason": "",
            "approval_flags_summary": {
                APPROVAL_ENV: approval_present,
                CONFIG_REVIEW_ENV: config_reviewed,
                BACKEND_ENV: (os.environ.get(BACKEND_ENV) or "").strip().lower() == "sqlalchemy",
            },
            "production_config_reviewed_summary": config_reviewed,
            "db_url_secret_redacted": True,
            "db_url_redacted": _redact_url(production_db_url),
            "route_owner_changed": False,
            "production_compat_changed": False,
            "fallback_retained": True,
            "read_parity_summary_present": False,
            "skipped_details_present": False,
            "side_effect_safety_present": True,
            "raw_payload_exported": False,
            "raw_pii_exported": False,
        },
        "read_parity_summary": {},
        "skipped_details": [],
        "failed_details": [],
        "side_effect_safety": _side_effect_safety(),
        "readiness": {
            "route_switch_ready": False,
            "reason": "",
        },
        "operator": os.environ.get(OPERATOR_ENV) or "phase4u_evidence_gate",
        "phase4s_lower_runner": {
            "path": str(PHASE4S_TOOL.relative_to(ROOT)),
            "returncode": None,
            "report": None,
        },
        "production_data_written": False,
        "production_repository_route_enabled": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
        "fallback_retained": True,
    }


def _block(report: dict[str, Any], result_status: str, reason: str) -> dict[str, Any]:
    if result_status not in RESULT_STATUSES:
        result_status = "not_executed_safety_failed"
    report["execution"]["result_status"] = result_status
    report["execution"]["not_executed_reason"] = reason
    report["evidence"]["command_attempted_or_not_attempted_reason"] = reason
    report["skipped_details"] = [{"name": "phase4u_evidence_gate", "status": result_status, "reason": reason}]
    report["evidence"]["skipped_details_present"] = True
    report["readiness"]["reason"] = reason
    return report


def _safe_phase4s_report(report: dict[str, Any]) -> dict[str, Any]:
    execution = report.get("execution") or {}
    evidence = report.get("evidence") or {}
    return {
        "ok": report.get("ok"),
        "status": report.get("status"),
        "execution": {
            "result_status": execution.get("result_status"),
            "read_only_dry_run_executed": execution.get("read_only_dry_run_executed"),
            "writes_attempted": execution.get("writes_attempted"),
            "not_executed_reason": execution.get("not_executed_reason"),
        },
        "evidence": {
            "db_url_secret_redacted": evidence.get("db_url_secret_redacted"),
            "route_owner_changed": evidence.get("route_owner_changed"),
            "production_compat_changed": evidence.get("production_compat_changed"),
            "fallback_retained": evidence.get("fallback_retained"),
            "read_parity_summary_present": evidence.get("read_parity_summary_present"),
            "skipped_details_present": evidence.get("skipped_details_present"),
            "side_effect_safety_present": evidence.get("side_effect_safety_present"),
            "raw_payload_exported": evidence.get("raw_payload_exported"),
            "raw_pii_exported": evidence.get("raw_pii_exported"),
        },
        "read_parity_summary": report.get("read_parity_summary") or {},
        "skipped_details": report.get("skipped_details") or [],
        "failed_details": report.get("failed_details") or [],
        "side_effect_safety": report.get("side_effect_safety") or {},
    }


def _run_phase4s() -> tuple[int, dict[str, Any]]:
    with tempfile.TemporaryDirectory(prefix="phase4u_readonly_") as tmpdir:
        output_json = Path(tmpdir) / "phase4s.json"
        command = [
            sys.executable,
            str(PHASE4S_TOOL.relative_to(ROOT)),
            "--read-only",
            "--confirm-no-writes",
            "--output-json",
            str(output_json),
        ]
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        report: dict[str, Any] = {}
        if output_json.exists():
            report = json.loads(output_json.read_text(encoding="utf-8"))
        return proc.returncode, report


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = _base_report(args)
    production_db_url = os.environ.get(PRODUCTION_DB_ENV)
    if os.environ.get(APPROVAL_ENV) != "1":
        return _block(report, "not_executed_missing_approval", f"{APPROVAL_ENV}=1 is required")
    if os.environ.get(CONFIG_REVIEW_ENV) != "1":
        return _block(report, "not_executed_config_not_reviewed", f"{CONFIG_REVIEW_ENV}=1 is required")
    if not production_db_url:
        return _block(report, "not_executed_missing_production_db", f"{PRODUCTION_DB_ENV} is required")
    if not args.read_only or not args.confirm_no_writes:
        return _block(report, "not_executed_read_only_flags_missing", "--read-only and --confirm-no-writes are required")
    if (os.environ.get(BACKEND_ENV) or "").strip().lower() != "sqlalchemy":
        return _block(report, "not_executed_safety_failed", f"{BACKEND_ENV}=sqlalchemy is required")

    report["execution"]["attempted"] = True
    report["execution"]["lower_runner_called"] = True
    code, phase4s_report = _run_phase4s()
    safe_report = _safe_phase4s_report(phase4s_report)
    report["phase4s_lower_runner"] = {
        "path": str(PHASE4S_TOOL.relative_to(ROOT)),
        "returncode": code,
        "report": safe_report,
    }
    lower_execution = safe_report.get("execution") or {}
    result_status = str(lower_execution.get("result_status") or "not_executed_safety_failed")
    report["execution"]["result_status"] = result_status if result_status in RESULT_STATUSES else "not_executed_safety_failed"
    report["execution"]["read_only_dry_run_executed"] = result_status == "read_only_dry_run_executed"
    report["execution"]["writes_attempted"] = bool(lower_execution.get("writes_attempted"))
    report["execution"]["not_executed_reason"] = str(lower_execution.get("not_executed_reason") or "")
    report["read_parity_summary"] = safe_report.get("read_parity_summary") or {}
    report["skipped_details"] = safe_report.get("skipped_details") or []
    report["failed_details"] = safe_report.get("failed_details") or []
    report["side_effect_safety"] = safe_report.get("side_effect_safety") or _side_effect_safety()
    report["evidence"]["command_attempted_or_not_attempted_reason"] = "Phase 4S evidence tool called with read-only/no-write flags"
    report["evidence"]["read_parity_summary_present"] = bool(report["read_parity_summary"])
    report["evidence"]["skipped_details_present"] = bool(report["skipped_details"])
    report["evidence"]["side_effect_safety_present"] = True
    report["route_owner_changed"] = bool((safe_report.get("evidence") or {}).get("route_owner_changed"))
    report["production_compat_changed"] = bool((safe_report.get("evidence") or {}).get("production_compat_changed"))
    report["fallback_retained"] = (safe_report.get("evidence") or {}).get("fallback_retained") is True
    report["evidence"]["route_owner_changed"] = report["route_owner_changed"]
    report["evidence"]["production_compat_changed"] = report["production_compat_changed"]
    report["evidence"]["fallback_retained"] = report["fallback_retained"]
    if report["execution"]["writes_attempted"] or report["route_owner_changed"] or report["production_compat_changed"] or not report["fallback_retained"]:
        report["ok"] = False
        report["execution"]["result_status"] = "not_executed_safety_failed"
        report["execution"]["not_executed_reason"] = "Phase 4S lower runner reported write or ownership safety drift"
    report["readiness"]["reason"] = (
        "read parity summary present"
        if report["execution"]["read_only_dry_run_executed"]
        else report["execution"]["not_executed_reason"]
    )
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    execution = report.get("execution") or {}
    evidence = report.get("evidence") or {}
    lines = [
        "# Phase 4U Profile Segment Template Production Read-Only Dry-Run Execution Evidence Attempt",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {execution.get('result_status')}",
        f"- attempted: {str(execution.get('attempted')).lower()}",
        f"- lower_runner_called: {str(execution.get('lower_runner_called')).lower()}",
        f"- read_only_dry_run_executed: {str(execution.get('read_only_dry_run_executed')).lower()}",
        f"- writes_attempted: {str(execution.get('writes_attempted')).lower()}",
        f"- approval_present: {str(execution.get('approval_present')).lower()}",
        f"- config_reviewed: {str(execution.get('config_reviewed')).lower()}",
        f"- production_db_present: {str(execution.get('production_db_present')).lower()}",
        f"- read_only_flags_present: {str(execution.get('read_only_flags_present')).lower()}",
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
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 4U profile segment template production read-only dry-run execution evidence attempt.")
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
