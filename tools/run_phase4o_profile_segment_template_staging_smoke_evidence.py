#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlunparse


ROOT = Path(__file__).resolve().parents[1]
PHASE4M_RUNNER = ROOT / "tools/run_phase4m_profile_segment_template_staging_smoke.py"
STAGING_DB_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL"
BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
WRITE_APPROVAL_ENV = "AICRM_PHASE4O_STAGING_WRITE_APPROVED"
OPERATOR_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_OPERATOR"
ALLOWED_DB_MARKERS = ("staging", "stage", "test", "local", "dev")
FORBIDDEN_DB_MARKERS = ("prod", "production", "primary", "master")
READ_CASES = ("catalog", "list", "options", "detail")
WRITE_CASES = (
    "create_with_idempotency",
    "create_replay",
    "create_conflict",
    "duplicate_template_rejected",
    "update_existing",
    "update_missing",
    "invalid_payload_rejected",
    "dangerous_field_rejected",
    "audit_log_created",
    "rollback_payload_present",
    "side_effect_safety_false",
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
    if parsed.username or parsed.password:
        netloc = f"<redacted>@{host}"
    else:
        netloc = host
    return urlunparse((parsed.scheme, netloc, parsed.path, "", "", ""))


def _db_url_safety(raw_url: str | None) -> dict[str, Any]:
    if not raw_url:
        return {
            "checked": True,
            "safe": False,
            "reason": f"{STAGING_DB_ENV} is required",
            "redacted_url": None,
            "allowed_marker_present": False,
            "forbidden_marker_present": False,
            "matched_allowed_markers": [],
            "matched_forbidden_markers": [],
            "secret_redacted": True,
            "production_data_used": False,
        }
    parsed = urlparse(raw_url)
    database_name = Path(parsed.path or "").name.lower()
    full_url = raw_url.lower()
    allowed = [marker for marker in ALLOWED_DB_MARKERS if marker in database_name or marker in full_url]
    forbidden = [marker for marker in FORBIDDEN_DB_MARKERS if marker in database_name or marker in full_url]
    safe = bool(allowed) and not forbidden
    if forbidden:
        reason = "database URL contains forbidden production marker"
    elif not allowed:
        reason = "database URL must include staging, stage, test, local, or dev"
    else:
        reason = "safe staging/test marker present"
    return {
        "checked": True,
        "safe": safe,
        "reason": reason,
        "redacted_url": _redact_url(raw_url),
        "database_name": database_name,
        "allowed_marker_present": bool(allowed),
        "forbidden_marker_present": bool(forbidden),
        "matched_allowed_markers": allowed,
        "matched_forbidden_markers": forbidden,
        "secret_redacted": True,
        "production_data_used": False,
    }


def _empty_matrix(status: str, notes: str) -> dict[str, list[dict[str, str]]]:
    return {
        "read": [{"name": name, "status": status, "notes": notes} for name in READ_CASES],
        "write": [{"name": name, "status": status, "notes": notes} for name in WRITE_CASES],
    }


def _matrix_from_runner(runner_report: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    details = {str(item.get("name")): item for item in runner_report.get("details") or [] if isinstance(item, dict)}
    matrix = _empty_matrix("skipped", "not reported by Phase 4M runner")
    for bucket, cases in (("read", READ_CASES), ("write", WRITE_CASES)):
        matrix[bucket] = []
        for name in cases:
            detail = details.get(name)
            if not detail:
                matrix[bucket].append({"name": name, "status": "skipped", "notes": "not reported by Phase 4M runner"})
            elif detail.get("skipped"):
                matrix[bucket].append({"name": name, "status": "skipped", "notes": str(detail.get("reason") or "skipped")})
            elif detail.get("ok"):
                matrix[bucket].append({"name": name, "status": "passed", "notes": "Phase 4M runner passed"})
            else:
                matrix[bucket].append({"name": name, "status": "failed", "notes": str(detail.get("error") or "Phase 4M runner failed")})
    return matrix


def _base_report(*, execute_writes: bool, db_safety: dict[str, Any]) -> dict[str, Any]:
    return {
        "ok": False,
        "timestamp": datetime.now(UTC).isoformat(),
        "command": "tools/run_phase4o_profile_segment_template_staging_smoke_evidence.py",
        "execute_writes_requested": execute_writes,
        "execution": {
            "result_status": "",
            "dry_run_attempted": False,
            "dry_run_passed": False,
            "write_smoke_attempted": False,
            "write_smoke_passed": False,
            "write_smoke_owner_approved": os.environ.get(WRITE_APPROVAL_ENV) == "1",
            "not_executed_reason": "",
        },
        "db_url_safety": db_safety,
        "smoke_matrix_result": _empty_matrix("blocked", "execution did not start"),
        "failed_skipped_details": [],
        "dry_run_result": None,
        "write_smoke_result": None,
        "side_effect_safety": {
            "external_calls_executed": False,
            "automation_execution_executed": False,
            "outbound_send_executed": False,
            "route_owner_changed": False,
            "production_compat_changed": False,
        },
        "rollback_cleanup": {
            "required": False,
            "completed": True,
            "strategy": "no staging writes executed; no cleanup required",
            "notes": "Safe namespace rollback is required if owner-approved writes execute later.",
        },
        "operator": os.environ.get(OPERATOR_ENV) or "",
        "owner_approval": {
            "automation_engine_owner": "pending",
            "integration_gateway_owner": "pending",
            "db_config_owner": "pending",
            "business_owner": "pending",
            "rollback_owner": "pending",
            "smoke_operator": "approved" if os.environ.get(WRITE_APPROVAL_ENV) == "1" else "pending",
        },
        "production_data_used": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
    }


def _run_phase4m(*, execute_writes: bool) -> tuple[int, dict[str, Any], str]:
    args = ["python3", str(PHASE4M_RUNNER.relative_to(ROOT))]
    if execute_writes:
        args.append("--execute-writes")
    else:
        args.append("--dry-run")
    output_json = Path(os.environ.get("TMPDIR", "/tmp")) / f"phase4o_phase4m_{'write' if execute_writes else 'dry_run'}_{os.getpid()}.json"
    args.extend(["--output-json", str(output_json)])
    proc = subprocess.run(
        args,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    report: dict[str, Any] = {}
    if output_json.exists():
        try:
            report = json.loads(output_json.read_text(encoding="utf-8"))
        finally:
            output_json.unlink(missing_ok=True)
    return proc.returncode, report, proc.stdout


def run_evidence(*, execute_writes: bool) -> dict[str, Any]:
    database_url = os.environ.get(STAGING_DB_ENV)
    db_safety = _db_url_safety(database_url)
    report = _base_report(execute_writes=execute_writes, db_safety=db_safety)

    if not database_url:
        report["execution"]["result_status"] = "not_executed_missing_staging_db"
        report["execution"]["not_executed_reason"] = f"{STAGING_DB_ENV} is required"
        report["failed_skipped_details"].append({"name": "staging_db_url", "status": "blocked", "reason": report["execution"]["not_executed_reason"]})
        return report
    if not db_safety.get("safe"):
        report["execution"]["result_status"] = "not_executed_db_url_safety_failed"
        report["execution"]["not_executed_reason"] = str(db_safety.get("reason") or "DB URL safety failed")
        report["failed_skipped_details"].append({"name": "db_url_safety", "status": "blocked", "reason": report["execution"]["not_executed_reason"]})
        return report
    if os.environ.get(BACKEND_ENV) != "sqlalchemy":
        report["execution"]["result_status"] = "not_executed_missing_approval"
        report["execution"]["not_executed_reason"] = f"{BACKEND_ENV}=sqlalchemy is required"
        report["failed_skipped_details"].append({"name": "backend_config", "status": "blocked", "reason": report["execution"]["not_executed_reason"]})
        return report
    if execute_writes and os.environ.get(WRITE_APPROVAL_ENV) != "1":
        report["execution"]["result_status"] = "not_executed_missing_approval"
        report["execution"]["not_executed_reason"] = f"{WRITE_APPROVAL_ENV}=1 is required for write smoke"
        report["failed_skipped_details"].append({"name": "write_owner_approval", "status": "blocked", "reason": report["execution"]["not_executed_reason"]})
        return report

    report["execution"]["dry_run_attempted"] = True
    dry_code, dry_report, dry_stdout = _run_phase4m(execute_writes=False)
    report["dry_run_result"] = {"returncode": dry_code, "report": dry_report, "stdout": dry_stdout}
    report["execution"]["dry_run_passed"] = dry_code == 0 and dry_report.get("ok") is True
    report["smoke_matrix_result"] = _matrix_from_runner(dry_report)
    report["failed_skipped_details"].extend(item for item in dry_report.get("details") or [] if item.get("skipped") or item.get("ok") is False)
    if not report["execution"]["dry_run_passed"]:
        report["execution"]["result_status"] = "not_executed_missing_approval" if execute_writes else "dry_run_executed"
        report["execution"]["not_executed_reason"] = "dry-run did not pass"
        return report

    if not execute_writes:
        report["execution"]["result_status"] = "dry_run_executed"
        report["ok"] = True
        return report

    report["execution"]["write_smoke_attempted"] = True
    report["rollback_cleanup"]["required"] = True
    report["rollback_cleanup"]["completed"] = False
    report["rollback_cleanup"]["strategy"] = "use Phase 4M safe namespace rollback / cleanup plan"
    write_code, write_report, write_stdout = _run_phase4m(execute_writes=True)
    report["write_smoke_result"] = {"returncode": write_code, "report": write_report, "stdout": write_stdout}
    report["execution"]["write_smoke_passed"] = write_code == 0 and write_report.get("ok") is True
    report["smoke_matrix_result"] = _matrix_from_runner(write_report)
    report["failed_skipped_details"].extend(item for item in write_report.get("details") or [] if item.get("skipped") or item.get("ok") is False)
    report["execution"]["result_status"] = "write_smoke_executed_owner_approved"
    report["ok"] = report["execution"]["write_smoke_passed"]
    report["rollback_cleanup"]["completed"] = report["execution"]["write_smoke_passed"]
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4O Profile Segment Template Staging Smoke Evidence",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- result_status: {report.get('execution', {}).get('result_status')}",
        f"- dry_run_attempted: {str(report.get('execution', {}).get('dry_run_attempted')).lower()}",
        f"- dry_run_passed: {str(report.get('execution', {}).get('dry_run_passed')).lower()}",
        f"- write_smoke_attempted: {str(report.get('execution', {}).get('write_smoke_attempted')).lower()}",
        f"- write_smoke_passed: {str(report.get('execution', {}).get('write_smoke_passed')).lower()}",
        f"- production_data_used: {str(report.get('production_data_used')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        "",
        "## DB URL Safety",
        "",
        f"- checked: {str(report.get('db_url_safety', {}).get('checked')).lower()}",
        f"- safe: {str(report.get('db_url_safety', {}).get('safe')).lower()}",
        f"- redacted_url: {report.get('db_url_safety', {}).get('redacted_url')}",
        f"- reason: {report.get('db_url_safety', {}).get('reason')}",
        "",
        "## Details",
    ]
    details = report.get("failed_skipped_details") or []
    lines.extend(f"- {item.get('name')}: {item.get('status') or item.get('reason') or item.get('error') or 'recorded'}" for item in details) if details else lines.append("- none")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4O staging smoke evidence gate.")
    parser.add_argument("--execute-writes", action="store_true", help="Run owner-approved staging write smoke after dry-run passes.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = run_evidence(execute_writes=bool(args.execute_writes))
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"ok: {str(report.get('ok')).lower()}")
    print(f"result_status: {report.get('execution', {}).get('result_status')}")
    print(f"dry_run_attempted: {str(report.get('execution', {}).get('dry_run_attempted')).lower()}")
    print(f"write_smoke_attempted: {str(report.get('execution', {}).get('write_smoke_attempted')).lower()}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
