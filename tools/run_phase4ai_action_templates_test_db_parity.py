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

TEST_DB_ENV = "AICRM_ACTION_TEMPLATES_TEST_DATABASE_URL"
MODE = "local_test_db_adapter_parity"
ALLOWED_DB_MARKERS = ("test", "local", "dev", "tmp")
FORBIDDEN_DB_MARKERS = ("prod", "production", "primary", "master")
REQUIRED_TABLES = (
    "automation_operation_templates",
    "automation_operation_template_idempotency",
    "automation_operation_template_audit_log",
)
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


class Harness:
    def __init__(self) -> None:
        self.details: list[dict[str, Any]] = []

    def pass_(self, name: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        self.details.append({"name": name, "status": "passed", "ok": True, "message": message, "evidence": evidence or {}})

    def fail(self, name: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        self.details.append({"name": name, "status": "failed", "ok": False, "message": message, "evidence": evidence or {}})

    def skip(self, name: str, message: str, evidence: dict[str, Any] | None = None) -> None:
        self.details.append({"name": name, "status": "skipped", "ok": True, "message": message, "evidence": evidence or {}})


def db_url_safety(db_url: str | None = None) -> dict[str, Any]:
    value = str(db_url if db_url is not None else os.getenv(TEST_DB_ENV, "") or "").strip()
    lowered = value.lower()
    allowed_hits = [marker for marker in ALLOWED_DB_MARKERS if marker in lowered]
    forbidden_hits = [marker for marker in FORBIDDEN_DB_MARKERS if marker in lowered]
    present = bool(value)
    safe = present and bool(allowed_hits) and not forbidden_hits
    if not present:
        reason = "missing_test_db_url"
    elif forbidden_hits:
        reason = "forbidden_marker_present"
    elif not allowed_hits:
        reason = "missing_allowed_marker"
    else:
        reason = "safe_local_test_db_url"
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


def _blocked_report(status: str, safety: dict[str, Any]) -> dict[str, Any]:
    details = [
        {
            "name": "test_db_url_guard",
            "status": "skipped" if status == "not_executed_missing_test_db" else "failed",
            "ok": status == "not_executed_missing_test_db",
            "message": "local/test DB adapter smoke was not executed",
            "evidence": safety,
        }
    ]
    failed = _count(details, "failed")
    skipped = _count(details, "skipped")
    return {
        "ok": failed == 0,
        "result_status": status,
        "mode": MODE,
        "db_url_safety": safety,
        "adapter_smoke_executed": False,
        "tests_run": 0,
        "passed": 0,
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


def _check_schema(engine: Any, harness: Harness) -> bool:
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    ok = True
    for table in REQUIRED_TABLES:
        name = {
            "automation_operation_templates": "main_table_available",
            "automation_operation_template_idempotency": "idempotency_table_available",
            "automation_operation_template_audit_log": "audit_table_available",
        }[table]
        if table in tables:
            harness.pass_(name, f"{table} is available")
        else:
            harness.fail(name, f"{table} is missing", {"available_tables": sorted(tables)})
            ok = False
    return ok


def _run_adapter_smoke(db_url: str, safety: dict[str, Any]) -> dict[str, Any]:
    from aicrm_next.automation_engine.action_template_repository import ActionTemplateIdempotencyConflict
    from aicrm_next.automation_engine.action_template_sqlalchemy_repository import SqlAlchemyActionTemplateRepository
    from aicrm_next.shared.errors import ContractError

    harness = Harness()
    engine = create_engine(db_url, future=True)
    if not _check_schema(engine, harness):
        return _ran_report(harness.details, safety, result_status="failed_schema_unavailable")

    repo = SqlAlchemyActionTemplateRepository(engine)
    try:
        rows, total = repo.list_action_templates({"limit": 5})
        harness.pass_("list_action_templates", "adapter list query returned", {"count": len(rows), "total": total})
    except Exception as exc:  # pragma: no cover - defensive evidence path
        harness.fail("list_action_templates", f"adapter list query failed: {exc}")

    code = f"phase4ai_{os.getpid()}"
    payload = {
        "template_name": "Phase 4AI Test DB Smoke",
        "template_code": code,
        "operator": "phase4ai",
        "default_config": {"mode": "local_test_db"},
    }
    created: dict[str, Any] = {}
    try:
        created = repo.create_action_template(payload, idempotency_key=f"{code}-idem", operator="phase4ai")
        harness.pass_("create_with_idempotency", "adapter create returned created template", {"template_code": code})
    except Exception as exc:  # pragma: no cover - defensive evidence path
        harness.fail("create_with_idempotency", f"adapter create failed: {exc}")

    if created:
        try:
            replay = repo.create_action_template(payload, idempotency_key=f"{code}-idem", operator="phase4ai")
            if replay.get("idempotent_replay") is True:
                harness.pass_("idempotency_replay", "same key and same payload replayed")
            else:
                harness.fail("idempotency_replay", "replay did not report idempotent_replay=true", {"body": replay})
        except Exception as exc:  # pragma: no cover
            harness.fail("idempotency_replay", f"replay failed: {exc}")
        try:
            repo.create_action_template({**payload, "template_name": "Phase 4AI Conflict"}, idempotency_key=f"{code}-idem", operator="phase4ai")
            harness.fail("idempotency_conflict", "different payload with same idempotency key did not conflict")
        except ActionTemplateIdempotencyConflict:
            harness.pass_("idempotency_conflict", "different payload with same idempotency key conflicts")
        except Exception as exc:  # pragma: no cover
            harness.fail("idempotency_conflict", f"unexpected conflict error: {exc}")
        try:
            repo.create_action_template({**payload, "template_name": "Phase 4AI Duplicate"}, idempotency_key=f"{code}-dup", operator="phase4ai")
            harness.fail("duplicate_template_code_rejected", "duplicate template_code was not rejected")
        except ContractError:
            harness.pass_("duplicate_template_code_rejected", "duplicate template_code is rejected")
        except Exception as exc:  # pragma: no cover
            harness.fail("duplicate_template_code_rejected", f"unexpected duplicate error: {exc}")
        events = repo.list_action_template_audit_events({"resource_id": created.get("template", {}).get("id")})
        if events:
            harness.pass_("audit_event_emitted", "audit row exists for created template", {"count": len(events)})
        else:
            harness.fail("audit_event_emitted", "audit row missing")
        if created.get("rollback_payload", {}).get("created_template_id") == created.get("template", {}).get("id"):
            harness.pass_("rollback_payload_present", "rollback payload references created template")
        else:
            harness.fail("rollback_payload_present", "rollback payload missing", {"body": created})
        if _all_real_safety_false(created.get("audit_event") or {}):
            harness.pass_("side_effect_safety_false", "side_effect_safety is all false")
        else:
            harness.fail("side_effect_safety_false", "side_effect_safety missing or not all false", {"body": created})

    for name, candidate in (
        ("missing_name_rejected", {"template_code": f"{code}_missing"}),
        ("invalid_status_rejected", {"template_name": "Bad Status", "template_code": f"{code}_bad_status", "status": "enabled"}),
        ("dangerous_fields_rejected", {"template_name": "Danger", "template_code": f"{code}_danger", "default_config": {"workflow_activation": True}}),
    ):
        try:
            repo.create_action_template(candidate, idempotency_key=f"{code}-{name}", operator="phase4ai")
            harness.fail(name, f"{name} did not reject invalid payload")
        except ContractError:
            harness.pass_(name, f"{name} rejected invalid payload")
        except Exception as exc:  # pragma: no cover
            harness.fail(name, f"unexpected validation error: {exc}")

    failed = _count(harness.details, "failed")
    return _ran_report(harness.details, safety, result_status="passed" if failed == 0 else "failed")


def _ran_report(details: list[dict[str, Any]], safety: dict[str, Any], *, result_status: str) -> dict[str, Any]:
    passed = _count(details, "passed")
    failed = _count(details, "failed")
    skipped = _count(details, "skipped")
    return {
        "ok": failed == 0,
        "result_status": result_status,
        "mode": MODE,
        "db_url_safety": safety,
        "adapter_smoke_executed": True,
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


def run_harness() -> dict[str, Any]:
    db_url = str(os.getenv(TEST_DB_ENV, "") or "").strip()
    safety = db_url_safety(db_url)
    if not safety["present"]:
        return _blocked_report("not_executed_missing_test_db", safety)
    if not safety["safe"]:
        return _blocked_report("blocked_unsafe_test_db_url", safety)
    return _run_adapter_smoke(db_url, safety)


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4AI Action Templates Test DB Parity",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- result_status: {report['result_status']}",
        f"- adapter_smoke_executed: {str(report['adapter_smoke_executed']).lower()}",
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
    parser = argparse.ArgumentParser(description="Run Phase 4AI action templates local/test DB adapter parity harness.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = run_harness()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"result_status: {report['result_status']}")
    print(f"ok: {str(report['ok']).lower()}")
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
