#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parents[1]
TEST_DB_ENV = "AICRM_NEXT_TEST_DATABASE_URL"
SAFE_DB_MARKERS = ("test", "local", "tmp", "dev")
OPERATOR = "phase4k_local_parity_operator"
IDEMPOTENCY_PREFIX = "phase4k_local_parity_"
TEMPLATE_CODE_PREFIX = "phase4k_local_parity_"


def _json_default(value: Any) -> str:
    return str(value)


def _safe_db_url(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {
            "ok": False,
            "connected": False,
            "reason": f"{TEST_DB_ENV} is required",
            "safe_markers": list(SAFE_DB_MARKERS),
        }
    parsed = urlparse(database_url)
    database_name = Path(parsed.path or "").name.lower()
    full_url = database_url.lower()
    matched = [marker for marker in SAFE_DB_MARKERS if marker in database_name or marker in full_url]
    return {
        "ok": bool(matched),
        "connected": False,
        "reason": "safe test/local/tmp/dev marker present" if matched else "database URL must include test, local, tmp, or dev",
        "database_name": database_name,
        "matched_markers": matched,
        "safe_markers": list(SAFE_DB_MARKERS),
    }


def _base_report() -> dict[str, Any]:
    return {
        "ok": False,
        "db_url_safety": {},
        "tests_run": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
        "side_effect_safety": {
            "external_calls_allowed": False,
            "automation_execution_allowed": False,
            "outbound_delivery_allowed": False,
            "route_owner_change_allowed": False,
            "real_external_call_executed": False,
            "real_automation_runtime_executed": False,
        },
        "production_data_used": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
    }


def _payload(name: str, code: str, *, status: str = "active") -> dict[str, Any]:
    return {
        "name": name,
        "code": code,
        "description": "Phase 4K local test DB parity harness metadata only",
        "status": status,
        "rules": {
            "categories": [
                {
                    "category_key": f"{code}_category",
                    "category_name": f"{name} Category",
                    "sort_order": 1,
                    "option_mappings": [{"question_id": 4101, "option_id": 4201}],
                }
            ]
        },
        "conditions": {},
    }


def _setup_sqlite_schema(engine: Any) -> None:
    from sqlalchemy import text

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_profile_segment_template (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    program_id INTEGER,
                    template_code TEXT NOT NULL UNIQUE,
                    template_name TEXT NOT NULL DEFAULT '',
                    questionnaire_id INTEGER,
                    segmentation_question_id INTEGER,
                    description TEXT NOT NULL DEFAULT '',
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    version INTEGER NOT NULL DEFAULT 1,
                    created_by TEXT NOT NULL DEFAULT '',
                    updated_by TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_profile_segment_category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    category_key TEXT NOT NULL DEFAULT '',
                    category_name TEXT NOT NULL DEFAULT '',
                    description TEXT NOT NULL DEFAULT '',
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    enabled BOOLEAN NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_profile_segment_option_mapping (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    template_id INTEGER NOT NULL,
                    category_id INTEGER NOT NULL,
                    question_id INTEGER NOT NULL,
                    option_id INTEGER NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_profile_segment_template_idempotency (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    request_hash TEXT NOT NULL,
                    response_snapshot TEXT NOT NULL DEFAULT '{}',
                    resource_type TEXT NOT NULL DEFAULT 'profile_segment_template',
                    resource_id INTEGER,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE (route_family, operation, operator, idempotency_key)
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS automation_profile_segment_template_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    route_family TEXT NOT NULL,
                    operation TEXT NOT NULL,
                    operator TEXT NOT NULL,
                    resource_type TEXT NOT NULL DEFAULT 'profile_segment_template',
                    resource_id INTEGER,
                    before_snapshot TEXT NOT NULL DEFAULT '{}',
                    after_snapshot TEXT NOT NULL DEFAULT '{}',
                    request_payload TEXT NOT NULL DEFAULT '{}',
                    validation_result TEXT NOT NULL DEFAULT '{}',
                    rollback_payload TEXT NOT NULL DEFAULT '{}',
                    side_effect_safety TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )


def _assert_required_tables(engine: Any) -> None:
    from sqlalchemy import inspect

    required = {
        "automation_profile_segment_template",
        "automation_profile_segment_category",
        "automation_profile_segment_option_mapping",
        "automation_profile_segment_template_idempotency",
        "automation_profile_segment_template_audit_log",
    }
    existing = set(inspect(engine).get_table_names())
    missing = sorted(required - existing)
    if missing:
        raise RuntimeError(f"local test database is missing required tables: {missing}")


def _init_engine(database_url: str) -> Any:
    from sqlalchemy import create_engine

    engine = create_engine(database_url, future=True)
    if database_url.startswith("sqlite"):
        _setup_sqlite_schema(engine)
    else:
        _assert_required_tables(engine)
    return engine


def _record(report: dict[str, Any], name: str, fn: Callable[[], dict[str, Any] | None]) -> Any:
    report["tests_run"] += 1
    try:
        detail = fn() or {}
    except Exception as exc:  # noqa: BLE001 - harness reports every parity failure.
        report["failed"] += 1
        report["details"].append({"name": name, "ok": False, "error": str(exc), "type": type(exc).__name__})
        return None
    report["passed"] += 1
    report["details"].append({"name": name, "ok": True, **detail})
    return detail


def _run_parity(database_url: str) -> dict[str, Any]:
    sys.path.insert(0, str(ROOT))
    from aicrm_next.automation_engine.profile_segment_repository import (
        ProfileSegmentTemplateIdempotencyConflict,
        SqlAlchemyProfileSegmentTemplateRepository,
    )
    from aicrm_next.shared.errors import ContractError, NotFoundError

    report = _base_report()
    report["db_url_safety"] = _safe_db_url(database_url)
    if not report["db_url_safety"].get("ok"):
        report["details"].append({"name": "db_url_safety", "ok": False, "error": report["db_url_safety"].get("reason")})
        return report

    engine = _init_engine(database_url)
    report["db_url_safety"]["connected"] = True
    repo = SqlAlchemyProfileSegmentTemplateRepository(engine)
    run_token = os.environ.get("PHASE4K_LOCAL_PARITY_RUN_ID") or uuid.uuid4().hex[:8]
    code_prefix = f"{TEMPLATE_CODE_PREFIX}{run_token}_"
    idem_prefix = f"{IDEMPOTENCY_PREFIX}{run_token}_"

    created_ref: dict[str, Any] = {}

    def create_seed() -> dict[str, Any]:
        payload = _payload(f"Phase 4K Local Seed {run_token}", f"{code_prefix}seed")
        result = repo.create_profile_segment_template(
            payload,
            idempotency_key=f"{idem_prefix}seed",
            operator=OPERATOR,
        )
        created_ref["template_id"] = result["template"]["id"]
        return {"template_id": created_ref["template_id"], "source_status": result.get("source_status")}

    _record(report, "seed_template", create_seed)

    _record(report, "catalog", lambda: {"total": repo.profile_segment_template_catalog()["total"]})
    _record(report, "list", lambda: {"total": repo.list_profile_segment_templates()[1]})
    _record(report, "options", lambda: {"enabled_total": repo.list_profile_segment_templates(enabled_only=True)[1]})
    _record(
        report,
        "detail",
        lambda: {"template_id": repo.get_profile_segment_template(int(created_ref["template_id"]))["id"]},
    )

    def create_replay() -> dict[str, Any]:
        payload = _payload(f"Phase 4K Local Replay {run_token}", f"{code_prefix}replay")
        first = repo.create_profile_segment_template(payload, idempotency_key=f"{idem_prefix}replay", operator=OPERATOR)
        replay = repo.create_profile_segment_template(payload, idempotency_key=f"{idem_prefix}replay", operator=OPERATOR)
        if first["template"]["id"] != replay["template"]["id"] or replay.get("idempotent_replay") is not True:
            raise AssertionError("idempotency replay did not return the same template")
        return {"template_id": first["template"]["id"], "idempotent_replay": True}

    _record(report, "create_idempotency_replay", create_replay)

    def create_conflict() -> dict[str, Any]:
        payload = _payload(f"Phase 4K Local Conflict {run_token}", f"{code_prefix}conflict")
        repo.create_profile_segment_template(payload, idempotency_key=f"{idem_prefix}conflict", operator=OPERATOR)
        try:
            repo.create_profile_segment_template(
                _payload(f"Phase 4K Local Conflict Other {run_token}", f"{code_prefix}conflict_other"),
                idempotency_key=f"{idem_prefix}conflict",
                operator=OPERATOR,
            )
        except ProfileSegmentTemplateIdempotencyConflict:
            return {"conflict_rejected": True}
        raise AssertionError("idempotency conflict was not rejected")

    _record(report, "create_idempotency_conflict", create_conflict)

    def duplicate_template() -> dict[str, Any]:
        try:
            repo.create_profile_segment_template(
                _payload(f"Phase 4K Local Seed {run_token}", f"{code_prefix}seed"),
                idempotency_key=f"{idem_prefix}duplicate",
                operator=OPERATOR,
            )
        except ContractError:
            return {"duplicate_rejected": True}
        raise AssertionError("duplicate template name/code was not rejected")

    _record(report, "duplicate_template", duplicate_template)

    def update_existing() -> dict[str, Any]:
        result = repo.update_profile_segment_template(
            int(created_ref["template_id"]),
            {
                "name": f"Phase 4K Local Seed Updated {run_token}",
                "status": "inactive",
                "rules": {"categories": [{"category_key": "phase4k_updated", "category_name": "Updated", "sort_order": 2}]},
            },
            operator=OPERATOR,
        )
        if not result.get("rollback", {}).get("before") or not result.get("rollback", {}).get("after"):
            raise AssertionError("update rollback before/after snapshots missing")
        return {"template_id": created_ref["template_id"], "audit_operation": result.get("audit_event", {}).get("operation")}

    _record(report, "update_existing", update_existing)

    def update_missing() -> dict[str, Any]:
        try:
            repo.update_profile_segment_template(999999999, {"name": "missing"}, operator=OPERATOR)
        except NotFoundError:
            return {"not_found": True}
        raise AssertionError("missing update did not return not-found")

    _record(report, "update_missing", update_missing)

    def invalid_payload() -> dict[str, Any]:
        try:
            repo.create_profile_segment_template(
                {"name": "", "code": f"{code_prefix}invalid", "status": "active", "rules": {}, "conditions": {}},
                idempotency_key=f"{idem_prefix}invalid",
                operator=OPERATOR,
            )
        except ContractError:
            return {"invalid_rejected": True}
        raise AssertionError("invalid payload was accepted")

    _record(report, "invalid_payload", invalid_payload)

    def dangerous_field_rejection() -> dict[str, Any]:
        try:
            repo.create_profile_segment_template(
                _payload(f"Phase 4K Dangerous {run_token}", f"{code_prefix}danger") | {"rules": {"categories": [], "timer": True}},
                idempotency_key=f"{idem_prefix}danger",
                operator=OPERATOR,
            )
        except ContractError:
            return {"dangerous_rejected": True}
        raise AssertionError("dangerous side-effect field was accepted")

    _record(report, "dangerous_field_rejection", dangerous_field_rejection)

    def audit_and_rollback() -> dict[str, Any]:
        events = repo.list_profile_segment_template_audit_events()
        if not events:
            raise AssertionError("audit events missing")
        latest = events[0]
        if "rollback_payload" not in latest or "side_effect_safety" not in latest:
            raise AssertionError("audit rollback or safety evidence missing")
        if any(bool(value) for value in latest["side_effect_safety"].values()):
            raise AssertionError("side-effect safety flag was true")
        return {"audit_events": len(events), "latest_operation": latest.get("operation")}

    _record(report, "audit_log_shape", audit_and_rollback)
    _record(report, "rollback_payload_shape", audit_and_rollback)

    report["ok"] = report["failed"] == 0
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4K Profile Segment Template Local Parity Harness",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- tests_run: {report.get('tests_run', 0)}",
        f"- passed: {report.get('passed', 0)}",
        f"- failed: {report.get('failed', 0)}",
        f"- skipped: {report.get('skipped', 0)}",
        f"- production_data_used: {str(report.get('production_data_used')).lower()}",
        f"- route_owner_changed: {str(report.get('route_owner_changed')).lower()}",
        f"- production_compat_changed: {str(report.get('production_compat_changed')).lower()}",
        "",
        "## Details",
    ]
    for detail in report.get("details") or []:
        status = "PASS" if detail.get("ok") else "FAIL"
        lines.append(f"- {detail.get('name')}: {status}")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4K profile segment template local test DB parity harness.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    database_url = os.environ.get(TEST_DB_ENV)
    safety = _safe_db_url(database_url)
    if not safety.get("ok"):
        report = _base_report()
        report["db_url_safety"] = safety
        report["details"].append({"name": "db_url_safety", "ok": False, "error": safety.get("reason")})
    else:
        report = _run_parity(str(database_url))

    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"ok: {str(report.get('ok')).lower()}")
    print(f"tests_run: {report.get('tests_run', 0)}")
    print(f"failed: {report.get('failed', 0)}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
