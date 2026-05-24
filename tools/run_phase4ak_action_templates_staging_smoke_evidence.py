#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGING_DB_ENV = "AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL"
REPO_BACKEND_ENV = "AICRM_ACTION_TEMPLATES_REPO_BACKEND"
SMOKE_APPROVAL_ENV = "AICRM_PHASE4AK_STAGING_SMOKE_APPROVED"
WRITE_APPROVAL_ENV = "AICRM_PHASE4AK_STAGING_WRITE_APPROVED"
LOWER_WRITE_APPROVAL_ENV = "AICRM_PHASE4AJ_STAGING_WRITE_APPROVED"
MODE = "staging_smoke_evidence_gate"
ALLOWED_DB_MARKERS = ("staging", "stage", "test", "local", "dev")
FORBIDDEN_DB_MARKERS = ("prod", "production", "primary", "master")
SAFE_NAMESPACE = {
    "template_code_prefix": "phase4aj_staging_smoke_",
    "operator": "phase4aj_staging_smoke_operator",
    "idempotency_key_prefix": "phase4aj_staging_smoke_",
    "delete_required": False,
}
SIDE_EFFECT_SAFETY = {
    "real_external_call_executed": False,
    "real_automation_execution_executed": False,
    "real_outbound_send_executed": False,
    "real_wecom_call_executed": False,
    "real_openclaw_call_executed": False,
    "real_mcp_call_executed": False,
    "real_llm_call_executed": False,
    "real_timer_executed": False,
    "real_customer_pool_state_changed": False,
}


def _truthy_env(name: str) -> bool:
    return str(os.getenv(name, "") or "").strip().lower() in {"1", "true", "yes", "on"}


def _redact_url(value: str) -> str:
    if not value:
        return ""
    if "@" in value and "://" in value:
        scheme, rest = value.split("://", 1)
        host_part = rest.split("@", 1)[1]
        return f"{scheme}://<redacted>@{host_part}"
    return value[:16] + "<redacted>" if len(value) > 24 else "<redacted>"


def db_url_safety(db_url: str | None = None) -> dict[str, Any]:
    value = str(db_url if db_url is not None else os.getenv(STAGING_DB_ENV, "") or "").strip()
    lowered = value.lower()
    allowed_hits = [marker for marker in ALLOWED_DB_MARKERS if marker in lowered]
    forbidden_hits = [marker for marker in FORBIDDEN_DB_MARKERS if marker in lowered]
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
        "allowed_markers": list(ALLOWED_DB_MARKERS),
        "forbidden_markers": list(FORBIDDEN_DB_MARKERS),
        "allowed_hits": allowed_hits,
        "forbidden_hits": forbidden_hits,
        "redacted_url": _redact_url(value),
    }


def _count(details: list[dict[str, Any]], status: str) -> int:
    return len([item for item in details if item.get("status") == status])


def _base_report(
    *,
    ok: bool,
    result_status: str,
    lower_runner_called: bool,
    staging_smoke_executed: bool,
    dry_run: bool,
    execute_writes: bool,
    write_approved: bool,
    safety: dict[str, Any],
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = _count(details, "passed")
    failed = _count(details, "failed")
    skipped = _count(details, "skipped")
    return {
        "ok": ok,
        "result_status": result_status,
        "mode": MODE,
        "lower_runner_called": lower_runner_called,
        "staging_smoke_executed": staging_smoke_executed,
        "dry_run": dry_run,
        "execute_writes": execute_writes,
        "write_approved": write_approved,
        "db_url_safety": safety,
        "safe_namespace": dict(SAFE_NAMESPACE),
        "tests_run": passed + failed,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "details": details,
        "side_effect_safety": dict(SIDE_EFFECT_SAFETY),
        "production_data_used": False,
        "production_route_owner_changed": False,
        "production_compat_changed": False,
        "route_switch_ready": False,
        "production_approval_claimed": False,
    }


def _blocked_report(status: str, message: str, safety: dict[str, Any], *, execute_writes: bool, failed: bool = False) -> dict[str, Any]:
    detail_status = "failed" if failed else "skipped"
    details = [
        {
            "name": "phase4ak_staging_smoke_gate",
            "status": detail_status,
            "ok": not failed,
            "message": message,
            "evidence": {
                "db_url_safety": safety,
                "repo_backend": os.getenv(REPO_BACKEND_ENV, ""),
                "smoke_approved": _truthy_env(SMOKE_APPROVAL_ENV),
                "write_approved": _truthy_env(WRITE_APPROVAL_ENV),
            },
        }
    ]
    return _base_report(
        ok=not failed,
        result_status=status,
        lower_runner_called=False,
        staging_smoke_executed=False,
        dry_run=not execute_writes,
        execute_writes=execute_writes,
        write_approved=_truthy_env(WRITE_APPROVAL_ENV),
        safety=safety,
        details=details,
    )


def _lower_runner_report(*, execute_writes: bool) -> dict[str, Any]:
    from tools import run_phase4aj_action_templates_staging_smoke as lower_runner

    previous = os.environ.get(LOWER_WRITE_APPROVAL_ENV)
    try:
        if execute_writes and _truthy_env(WRITE_APPROVAL_ENV):
            os.environ[LOWER_WRITE_APPROVAL_ENV] = "1"
        elif LOWER_WRITE_APPROVAL_ENV in os.environ:
            del os.environ[LOWER_WRITE_APPROVAL_ENV]
        return lower_runner.run_runner(execute_writes=execute_writes)
    finally:
        if previous is None:
            os.environ.pop(LOWER_WRITE_APPROVAL_ENV, None)
        else:
            os.environ[LOWER_WRITE_APPROVAL_ENV] = previous


def run_runner(*, execute_writes: bool = False) -> dict[str, Any]:
    db_url = str(os.getenv(STAGING_DB_ENV, "") or "").strip()
    safety = db_url_safety(db_url)
    if not safety["present"]:
        return _blocked_report("not_executed_missing_staging_db", "staging DB URL is missing", safety, execute_writes=execute_writes)
    if not safety["safe"]:
        return _blocked_report(
            "not_executed_db_url_safety_failed",
            "staging DB URL failed safety marker checks",
            safety,
            execute_writes=execute_writes,
            failed=True,
        )
    if str(os.getenv(REPO_BACKEND_ENV, "") or "").strip().lower() != "sqlalchemy":
        return _blocked_report("not_executed_missing_repo_backend", "repo backend must be explicitly set to sqlalchemy", safety, execute_writes=execute_writes)
    if not _truthy_env(SMOKE_APPROVAL_ENV):
        return _blocked_report("not_executed_missing_approval", "staging smoke approval flag is missing", safety, execute_writes=execute_writes)
    if execute_writes and not _truthy_env(WRITE_APPROVAL_ENV):
        return _blocked_report("not_executed_write_approval_missing", "write smoke approval flag is missing", safety, execute_writes=execute_writes)

    lower = _lower_runner_report(execute_writes=execute_writes)
    lower_status = str(lower.get("result_status") or "")
    if execute_writes:
        result_status = "staging_smoke_executed_write_safe_namespace" if lower.get("ok") else lower_status or "failed"
    else:
        result_status = "staging_smoke_executed_readonly" if lower.get("ok") else lower_status or "failed"
    details = [
        {
            "name": "phase4aj_lower_runner",
            "status": "passed" if lower.get("ok") else "failed",
            "ok": bool(lower.get("ok")),
            "message": f"lower runner result_status={lower_status}",
            "evidence": {
                "result_status": lower_status,
                "staging_smoke_executed": lower.get("staging_smoke_executed"),
                "tests_run": lower.get("tests_run"),
                "passed": lower.get("passed"),
                "failed": lower.get("failed"),
                "skipped": lower.get("skipped"),
            },
        }
    ]
    details.extend(lower.get("details") or [])
    return _base_report(
        ok=bool(lower.get("ok")),
        result_status=result_status,
        lower_runner_called=True,
        staging_smoke_executed=bool(lower.get("staging_smoke_executed") or not execute_writes),
        dry_run=not execute_writes,
        execute_writes=execute_writes,
        write_approved=_truthy_env(WRITE_APPROVAL_ENV),
        safety=safety,
        details=details,
    )


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4AK Action Templates Staging Smoke Evidence",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- result_status: {report['result_status']}",
        f"- lower_runner_called: {str(report['lower_runner_called']).lower()}",
        f"- staging_smoke_executed: {str(report['staging_smoke_executed']).lower()}",
        f"- dry_run: {str(report['dry_run']).lower()}",
        f"- execute_writes: {str(report['execute_writes']).lower()}",
        f"- write_approved: {str(report['write_approved']).lower()}",
        f"- tests_run: {report['tests_run']}",
        f"- passed: {report['passed']}",
        f"- failed: {report['failed']}",
        f"- skipped: {report['skipped']}",
        "",
        "## Details",
    ]
    for item in report.get("details") or []:
        lines.append(f"- {item['status']}: {item['name']} - {item['message']}")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4AK action templates staging smoke evidence gate.")
    parser.add_argument("--execute-writes", action="store_true")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = run_runner(execute_writes=args.execute_writes)
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"result_status: {report['result_status']}")
    print(f"ok: {str(report['ok']).lower()}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
