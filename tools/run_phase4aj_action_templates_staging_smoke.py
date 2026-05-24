#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import create_engine, inspect


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

STAGING_DB_ENV = "AICRM_ACTION_TEMPLATES_STAGING_DATABASE_URL"
WRITE_APPROVAL_ENV = "AICRM_PHASE4AJ_STAGING_WRITE_APPROVED"
MODE = "staging_smoke_package"
ALLOWED_DB_MARKERS = ("staging", "stage", "test", "local", "dev")
FORBIDDEN_DB_MARKERS = ("prod", "production", "primary", "master")
REQUIRED_TABLES = (
    "automation_operation_templates",
    "automation_operation_template_idempotency",
    "automation_operation_template_audit_log",
)
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


class Runner:
    def __init__(self) -> None:
        self.details: list[dict[str, Any]] = []

    def pass_(self, name: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        self.details.append({"name": name, "status": "passed", "ok": True, "message": message, "evidence": evidence or {}})

    def fail(self, name: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        self.details.append({"name": name, "status": "failed", "ok": False, "message": message, "evidence": evidence or {}})

    def skip(self, name: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        self.details.append({"name": name, "status": "skipped", "ok": True, "message": message, "evidence": evidence or {}})


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


def _redact_url(value: str) -> str:
    if not value:
        return ""
    if "@" in value and "://" in value:
        scheme, rest = value.split("://", 1)
        host_part = rest.split("@", 1)[1]
        return f"{scheme}://<redacted>@{host_part}"
    return value[:16] + "<redacted>" if len(value) > 24 else "<redacted>"


def _all_real_safety_false(payload: dict[str, Any]) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def _count(details: list[dict[str, Any]], status: str) -> int:
    return len([item for item in details if item["status"] == status])


def _write_approved(execute_writes: bool) -> bool:
    value = str(os.getenv(WRITE_APPROVAL_ENV, "") or "").strip().lower()
    return execute_writes and value in {"1", "true", "yes", "on"}


def _base_report(
    *,
    ok: bool,
    result_status: str,
    safety: dict[str, Any],
    dry_run: bool,
    execute_writes: bool,
    staging_smoke_executed: bool,
    details: list[dict[str, Any]],
) -> dict[str, Any]:
    passed = _count(details, "passed")
    failed = _count(details, "failed")
    skipped = _count(details, "skipped")
    return {
        "ok": ok,
        "result_status": result_status,
        "mode": MODE,
        "dry_run": dry_run,
        "execute_writes": execute_writes,
        "db_url_safety": safety,
        "staging_smoke_executed": staging_smoke_executed,
        "tests_run": passed + failed,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "details": details,
        "safe_namespace": dict(SAFE_NAMESPACE),
        "side_effect_safety": dict(SIDE_EFFECT_SAFETY),
        "production_data_used": False,
        "production_route_owner_changed": False,
        "production_compat_changed": False,
        "route_switch_ready": False,
        "production_approval_claimed": False,
    }


def _blocked_report(status: str, safety: dict[str, Any], *, execute_writes: bool) -> dict[str, Any]:
    ok = status == "not_executed_missing_staging_db"
    details = [
        {
            "name": "staging_db_url_guard",
            "status": "skipped" if ok else "failed",
            "ok": ok,
            "message": "staging smoke package was not executed",
            "evidence": safety,
        }
    ]
    return _base_report(
        ok=ok,
        result_status=status,
        safety=safety,
        dry_run=not execute_writes,
        execute_writes=execute_writes,
        staging_smoke_executed=False,
        details=details,
    )


def _check_schema(engine: Any, runner: Runner) -> bool:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    ok = True
    for table in REQUIRED_TABLES:
        if table in tables:
            runner.pass_("schema_available", f"{table} is available", {"table": table})
        else:
            runner.fail("schema_available", f"{table} is missing", {"available_tables": sorted(tables), "table": table})
            ok = False
    return ok


def _run_read_preflight(db_url: str, safety: dict[str, Any], *, execute_writes: bool) -> tuple[Runner, Any | None]:
    from aicrm_next.automation_engine.action_template_sqlalchemy_repository import SqlAlchemyActionTemplateRepository

    runner = Runner()
    engine = create_engine(db_url, future=True)
    if not _check_schema(engine, runner):
        return runner, None
    repo = SqlAlchemyActionTemplateRepository(engine)
    try:
        rows, total = repo.list_action_templates({"limit": 5})
        runner.pass_("list_action_templates", "adapter list query returned", {"count": len(rows), "total": total})
    except Exception as exc:  # pragma: no cover - defensive evidence path
        runner.fail("list_action_templates", f"adapter list query failed: {exc}")
    if not _write_approved(execute_writes):
        runner.skip(
            "write_smoke_not_executed",
            "write smoke requires --execute-writes and AICRM_PHASE4AJ_STAGING_WRITE_APPROVED=1",
        )
    return runner, repo


def _run_write_smoke(runner: Runner, repo: Any) -> None:
    from aicrm_next.automation_engine.action_template_repository import ActionTemplateIdempotencyConflict
    from aicrm_next.shared.errors import ContractError

    suffix = str(os.getpid())
    code = f"{SAFE_NAMESPACE['template_code_prefix']}{suffix}"
    idempotency_key = f"{SAFE_NAMESPACE['idempotency_key_prefix']}{suffix}"
    operator = str(SAFE_NAMESPACE["operator"])
    payload = {
        "template_name": "Phase 4AJ Staging Smoke",
        "template_code": code,
        "operator": operator,
        "default_config": {"mode": "staging_smoke"},
    }
    created: dict[str, Any] = {}
    try:
        created = repo.create_action_template(payload, idempotency_key=idempotency_key, operator=operator)
        runner.pass_("create_with_idempotency", "safe namespace create returned", {"template_code": code})
    except Exception as exc:  # pragma: no cover
        runner.fail("create_with_idempotency", f"safe namespace create failed: {exc}")
    if created:
        try:
            replay = repo.create_action_template(payload, idempotency_key=idempotency_key, operator=operator)
            if replay.get("idempotent_replay") is True:
                runner.pass_("idempotency_replay", "same key and same payload replayed")
            else:
                runner.fail("idempotency_replay", "replay did not report idempotent_replay=true", {"body": replay})
        except Exception as exc:  # pragma: no cover
            runner.fail("idempotency_replay", f"replay failed: {exc}")
        try:
            repo.create_action_template({**payload, "template_name": "Phase 4AJ Conflict"}, idempotency_key=idempotency_key, operator=operator)
            runner.fail("idempotency_conflict", "different payload with same idempotency key did not conflict")
        except ActionTemplateIdempotencyConflict:
            runner.pass_("idempotency_conflict", "different payload with same idempotency key conflicts")
        except Exception as exc:  # pragma: no cover
            runner.fail("idempotency_conflict", f"unexpected conflict error: {exc}")
        try:
            repo.create_action_template({**payload, "template_name": "Phase 4AJ Duplicate"}, idempotency_key=f"{idempotency_key}_dup", operator=operator)
            runner.fail("duplicate_template_code_rejected", "duplicate template_code was not rejected")
        except ContractError:
            runner.pass_("duplicate_template_code_rejected", "duplicate template_code is rejected")
        except Exception as exc:  # pragma: no cover
            runner.fail("duplicate_template_code_rejected", f"unexpected duplicate error: {exc}")
        events = repo.list_action_template_audit_events({"resource_id": created.get("template", {}).get("id")})
        if events:
            runner.pass_("audit_event_emitted", "audit row exists for created template", {"count": len(events)})
        else:
            runner.fail("audit_event_emitted", "audit row missing")
        if created.get("rollback_payload", {}).get("created_template_id") == created.get("template", {}).get("id"):
            runner.pass_("rollback_payload_present", "rollback payload references created template")
        else:
            runner.fail("rollback_payload_present", "rollback payload missing", {"body": created})
        if _all_real_safety_false(created.get("audit_event") or {}):
            runner.pass_("side_effect_safety_false", "side_effect_safety is all false")
        else:
            runner.fail("side_effect_safety_false", "side_effect_safety missing or not all false", {"body": created})

    for name, candidate in (
        ("missing_name_rejected", {"template_code": f"{code}_missing"}),
        ("invalid_status_rejected", {"template_name": "Bad Status", "template_code": f"{code}_bad_status", "status": "enabled"}),
        ("dangerous_fields_rejected", {"template_name": "Danger", "template_code": f"{code}_danger", "default_config": {"workflow_activation": True}}),
    ):
        try:
            repo.create_action_template(candidate, idempotency_key=f"{idempotency_key}_{name}", operator=operator)
            runner.fail(name, f"{name} did not reject invalid payload")
        except ContractError:
            runner.pass_(name, f"{name} rejected invalid payload")
        except Exception as exc:  # pragma: no cover
            runner.fail(name, f"unexpected validation error: {exc}")


def run_runner(*, execute_writes: bool = False) -> dict[str, Any]:
    db_url = str(os.getenv(STAGING_DB_ENV, "") or "").strip()
    safety = db_url_safety(db_url)
    if not safety["present"]:
        return _blocked_report("not_executed_missing_staging_db", safety, execute_writes=execute_writes)
    if not safety["safe"]:
        return _blocked_report("blocked_unsafe_staging_db_url", safety, execute_writes=execute_writes)
    runner, repo = _run_read_preflight(db_url, safety, execute_writes=execute_writes)
    if repo is None:
        return _base_report(
            ok=False,
            result_status="failed_schema_unavailable",
            safety=safety,
            dry_run=not execute_writes,
            execute_writes=execute_writes,
            staging_smoke_executed=False,
            details=runner.details,
        )
    if _write_approved(execute_writes):
        _run_write_smoke(runner, repo)
        executed = True
        result_status = "passed" if _count(runner.details, "failed") == 0 else "failed"
    else:
        executed = False
        result_status = "ready_for_owner_approved_staging_write_smoke" if _count(runner.details, "failed") == 0 else "failed"
    return _base_report(
        ok=_count(runner.details, "failed") == 0,
        result_status=result_status,
        safety=safety,
        dry_run=not execute_writes,
        execute_writes=execute_writes,
        staging_smoke_executed=executed,
        details=runner.details,
    )


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4AJ Action Templates Staging Smoke Package",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- result_status: {report['result_status']}",
        f"- dry_run: {str(report['dry_run']).lower()}",
        f"- execute_writes: {str(report['execute_writes']).lower()}",
        f"- staging_smoke_executed: {str(report['staging_smoke_executed']).lower()}",
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
    parser = argparse.ArgumentParser(description="Run Phase 4AJ action templates staging smoke package.")
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
