#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
PHASE4R_RUNNER = ROOT / "tools/run_phase4r_profile_segment_template_production_readonly_dry_run.py"
APPROVAL_ENV = "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_APPROVED"
CONFIG_REVIEW_ENV = "AICRM_PHASE4R_PRODUCTION_CONFIG_REVIEWED"
BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
PRODUCTION_DB_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_PRODUCTION_DATABASE_URL"
OPERATOR_ENV = "AICRM_PHASE4R_PRODUCTION_READONLY_DRY_RUN_OPERATOR"
REQUIRED_BEFORE_ROUTE_SWITCH_READY = (
    "actual_production_readonly_dry_run_executed",
    "read_parity_passed",
    "no_writes_attempted",
    "side_effect_safety_false",
    "fallback_validation_passed",
    "production_compat_unchanged",
    "owner_approval_completed",
    "rollback_owner_assigned",
    "production_config_review_completed",
)


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


def _blocker_template() -> dict[str, Any]:
    return {
        "missing_approval": False,
        "missing_config_review": False,
        "missing_production_db": False,
        "missing_read_only_flags": False,
        "safety_failed": False,
        "unblock_actions": [],
    }


def _base_report(args: argparse.Namespace) -> dict[str, Any]:
    approval_present = os.environ.get(APPROVAL_ENV) == "1"
    config_reviewed = os.environ.get(CONFIG_REVIEW_ENV) == "1"
    production_db_url = os.environ.get(PRODUCTION_DB_ENV)
    read_only_flags_present = bool(args.read_only and args.confirm_no_writes)
    return {
        "ok": True,
        "status": "phase_4v_production_readonly_execution_blocker_and_readiness_no_route_switch",
        "timestamp": datetime.now(UTC).isoformat(),
        "command": "tools/run_phase4v_profile_segment_template_production_readonly_execution_blocker_and_readiness.py",
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
        "blockers": _blocker_template(),
        "evidence": {
            "command_attempted_or_not_attempted_reason": "",
            "approval_flags_summary": {
                APPROVAL_ENV: approval_present,
                CONFIG_REVIEW_ENV: config_reviewed,
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
        "side_effect_safety": _side_effect_safety(),
        "read_parity_summary": {},
        "skipped_details": [],
        "failed_details": [],
        "operator": os.environ.get(OPERATOR_ENV) or "",
        "phase4r_runner": {
            "path": str(PHASE4R_RUNNER.relative_to(ROOT)),
            "returncode": None,
            "stdout": "",
            "report": None,
        },
        "readiness": {
            "route_switch_ready": False,
            "production_repository_route_enablement_ready": False,
            "fallback_removal_ready": False,
            "production_write_ready": False,
            "reason": "",
            "blockers": [],
            "required_before_route_switch_ready": list(REQUIRED_BEFORE_ROUTE_SWITCH_READY),
        },
    }


def _unblock_actions(report: dict[str, Any]) -> list[dict[str, str]]:
    blockers = report["blockers"]
    actions: list[dict[str, str]] = []
    if blockers["missing_approval"]:
        actions.append({"item": "Obtain explicit owner approval for production read-only dry-run only."})
    if blockers["missing_config_review"]:
        actions.append({"item": "Complete production config review and record approval."})
    if blockers["missing_production_db"]:
        actions.append({"item": f"Provide {PRODUCTION_DB_ENV} without using DATABASE_URL fallback."})
    if blockers["missing_read_only_flags"]:
        actions.append({"item": "Execute only with --read-only and --confirm-no-writes."})
    if blockers["safety_failed"]:
        actions.append({"item": f"Set {BACKEND_ENV}=sqlalchemy and keep legacy production_compat fallback owner unchanged."})
    return actions


def _set_blocked(report: dict[str, Any], status: str, reason: str, blocker_field: str) -> dict[str, Any]:
    report["execution"]["result_status"] = status
    report["execution"]["not_executed_reason"] = reason
    report["evidence"]["command_attempted_or_not_attempted_reason"] = reason
    report["evidence"]["skipped_details_present"] = True
    report["blockers"][blocker_field] = True
    report["blockers"]["missing_approval"] = report["blockers"]["missing_approval"] or not report["execution"]["approval_present"]
    report["blockers"]["missing_config_review"] = report["blockers"]["missing_config_review"] or not report["execution"]["config_reviewed"]
    report["blockers"]["missing_production_db"] = report["blockers"]["missing_production_db"] or not report["execution"]["production_db_present"]
    report["blockers"]["missing_read_only_flags"] = report["blockers"]["missing_read_only_flags"] or not report["execution"]["read_only_flags_present"]
    report["blockers"]["safety_failed"] = report["blockers"]["safety_failed"] or (os.environ.get(BACKEND_ENV) or "").strip().lower() != "sqlalchemy"
    report["blockers"]["unblock_actions"] = _unblock_actions(report)
    report["skipped_details"] = [{"name": "phase4v_evidence_gate", "status": status, "reason": reason}]
    report["readiness"]["reason"] = "blocked evidence only; route-owner switch readiness remains not ready"
    report["readiness"]["blockers"] = [
        {"item": reason},
        {"item": "Production read-only dry-run has not executed."},
        {"item": "Read parity summary is not present because execution did not start."},
    ]
    return report


def _run_phase4r() -> tuple[int, dict[str, Any], str]:
    with tempfile.TemporaryDirectory(prefix="phase4v_readonly_") as tmpdir:
        output_json = Path(tmpdir) / "phase4r.json"
        command = [
            "python3",
            str(PHASE4R_RUNNER.relative_to(ROOT)),
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
        return proc.returncode, report, proc.stdout


def _read_parity_passed(summary: dict[str, Any], failed_details: list[Any]) -> bool:
    if failed_details or not summary:
        return False
    statuses = {str(item.get("status")) for item in summary.values() if isinstance(item, dict)}
    return bool(statuses) and "failed" not in statuses and "blocked" not in statuses


def _apply_readiness(report: dict[str, Any]) -> None:
    executed = bool(report["execution"]["read_only_dry_run_executed"])
    no_writes = report["execution"]["writes_attempted"] is False
    parity_passed = _read_parity_passed(report["read_parity_summary"], report["failed_details"])
    safe = all(value is False for value in report["side_effect_safety"].values())
    unchanged = (
        report["evidence"]["route_owner_changed"] is False
        and report["evidence"]["production_compat_changed"] is False
        and report["evidence"]["fallback_retained"] is True
    )
    ready = executed and no_writes and parity_passed and safe and unchanged
    report["readiness"]["route_switch_ready"] = ready
    report["readiness"]["production_repository_route_enablement_ready"] = ready
    report["readiness"]["fallback_removal_ready"] = False
    report["readiness"]["production_write_ready"] = False
    if ready:
        report["readiness"]["reason"] = "read-only evidence passed; next phase may prepare route-owner switch readiness package only"
        report["readiness"]["blockers"] = []
        return
    blockers: list[dict[str, str]] = []
    if not executed:
        blockers.append({"item": "Production read-only dry-run has not executed."})
    if not parity_passed:
        blockers.append({"item": "Read parity has not passed or summary is incomplete."})
    if not no_writes:
        blockers.append({"item": "A write attempt was reported."})
    if not safe:
        blockers.append({"item": "Side-effect safety is not fully false."})
    if not unchanged:
        blockers.append({"item": "Route owner, production_compat, or fallback evidence is unsafe."})
    report["readiness"]["reason"] = "route-owner switch readiness remains not ready"
    report["readiness"]["blockers"] = blockers


def run(args: argparse.Namespace) -> dict[str, Any]:
    report = _base_report(args)
    if os.environ.get(APPROVAL_ENV) != "1":
        return _set_blocked(report, "not_executed_missing_approval", f"{APPROVAL_ENV}=1 is required", "missing_approval")
    if os.environ.get(CONFIG_REVIEW_ENV) != "1":
        return _set_blocked(report, "not_executed_config_not_reviewed", f"{CONFIG_REVIEW_ENV}=1 is required", "missing_config_review")
    if not os.environ.get(PRODUCTION_DB_ENV):
        return _set_blocked(report, "not_executed_missing_production_db", f"{PRODUCTION_DB_ENV} is required", "missing_production_db")
    if not args.read_only or not args.confirm_no_writes:
        return _set_blocked(report, "not_executed_read_only_flags_missing", "--read-only and --confirm-no-writes are required", "missing_read_only_flags")
    if (os.environ.get(BACKEND_ENV) or "").strip().lower() != "sqlalchemy":
        return _set_blocked(report, "not_executed_safety_failed", f"{BACKEND_ENV}=sqlalchemy is required", "safety_failed")

    report["execution"]["attempted"] = True
    report["execution"]["lower_runner_called"] = True
    code, runner_report, stdout = _run_phase4r()
    report["phase4r_runner"] = {
        "path": str(PHASE4R_RUNNER.relative_to(ROOT)),
        "returncode": code,
        "stdout": stdout,
        "report": runner_report,
    }
    result_status = str(runner_report.get("execution_status") or "not_executed_safety_failed")
    report["execution"]["result_status"] = result_status
    report["execution"]["read_only_dry_run_executed"] = result_status == "read_only_dry_run_executed"
    report["execution"]["writes_attempted"] = bool(runner_report.get("writes_attempted"))
    report["read_parity_summary"] = runner_report.get("read_parity_summary") or {}
    report["skipped_details"] = runner_report.get("skipped") or []
    report["failed_details"] = runner_report.get("failed") or []
    report["evidence"]["command_attempted_or_not_attempted_reason"] = "Phase 4R runner called with read-only/no-write flags"
    report["evidence"]["read_parity_summary_present"] = bool(report["read_parity_summary"])
    report["evidence"]["skipped_details_present"] = bool(report["skipped_details"])
    report["evidence"]["route_owner_changed"] = bool(runner_report.get("route_owner_changed"))
    report["evidence"]["production_compat_changed"] = bool(runner_report.get("production_compat_changed"))
    report["evidence"]["fallback_retained"] = bool(runner_report.get("fallback_retained", True))
    if report["execution"]["writes_attempted"]:
        report["side_effect_safety"]["create_update_delete_executed"] = True
    _apply_readiness(report)
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    execution = report.get("execution") or {}
    blockers = report.get("blockers") or {}
    readiness = report.get("readiness") or {}
    lines = [
        "# Phase 4V Profile Segment Template Production Read-Only Execution Blocker And Readiness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {execution.get('result_status')}",
        f"- attempted: {str(execution.get('attempted')).lower()}",
        f"- lower_runner_called: {str(execution.get('lower_runner_called')).lower()}",
        f"- read_only_dry_run_executed: {str(execution.get('read_only_dry_run_executed')).lower()}",
        f"- writes_attempted: {str(execution.get('writes_attempted')).lower()}",
        f"- route_switch_ready: {str(readiness.get('route_switch_ready')).lower()}",
        f"- production_repository_route_enablement_ready: {str(readiness.get('production_repository_route_enablement_ready')).lower()}",
        f"- fallback_removal_ready: {str(readiness.get('fallback_removal_ready')).lower()}",
        f"- production_write_ready: {str(readiness.get('production_write_ready')).lower()}",
        "",
        "## Blocker Package",
        f"- missing_approval: {str(blockers.get('missing_approval')).lower()}",
        f"- missing_config_review: {str(blockers.get('missing_config_review')).lower()}",
        f"- missing_production_db: {str(blockers.get('missing_production_db')).lower()}",
        f"- missing_read_only_flags: {str(blockers.get('missing_read_only_flags')).lower()}",
        f"- safety_failed: {str(blockers.get('safety_failed')).lower()}",
        "",
        "## Unblock Actions",
    ]
    actions = blockers.get("unblock_actions") or []
    lines.extend(f"- {item.get('item')}" for item in actions) if actions else lines.append("- none")
    lines.extend(["", "## Readiness Reason", f"- {readiness.get('reason') or 'none'}", "", "## Readiness Blockers"])
    readiness_blockers = readiness.get("blockers") or []
    lines.extend(f"- {item.get('item')}" for item in readiness_blockers) if readiness_blockers else lines.append("- none")
    lines.extend(["", "## Read Parity Summary"])
    summary = report.get("read_parity_summary") or {}
    if summary:
        for name, detail in summary.items():
            lines.append(f"- {name}: {detail.get('status')} - {detail.get('notes', '')}")
    else:
        lines.append("- none")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 4V profile segment template read-only execution blocker and readiness evidence.")
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
