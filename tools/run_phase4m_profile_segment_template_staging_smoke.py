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
STAGING_DB_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_DATABASE_URL"
BACKEND_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_REPO_BACKEND"
OPERATOR_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_OPERATOR"
NAMESPACE_ENV = "AICRM_PROFILE_SEGMENT_TEMPLATE_STAGING_NAMESPACE"
ALLOWED_DB_MARKERS = ("staging", "stage", "test", "local", "dev")
FORBIDDEN_DB_MARKERS = ("prod", "production", "primary", "master")
DEFAULT_OPERATOR = "phase4m_staging_smoke_operator"
DEFAULT_NAMESPACE = "phase4m_staging_smoke"


def _json_default(value: Any) -> str:
    return str(value)


def _db_url_safety(database_url: str | None) -> dict[str, Any]:
    if not database_url:
        return {
            "ok": False,
            "connected": False,
            "reason": f"{STAGING_DB_ENV} is required",
            "allowed_markers": list(ALLOWED_DB_MARKERS),
            "forbidden_markers": list(FORBIDDEN_DB_MARKERS),
        }
    parsed = urlparse(database_url)
    database_name = Path(parsed.path or "").name.lower()
    full_url = database_url.lower()
    allowed = [marker for marker in ALLOWED_DB_MARKERS if marker in database_name or marker in full_url]
    forbidden = [marker for marker in FORBIDDEN_DB_MARKERS if marker in database_name or marker in full_url]
    ok = bool(allowed) and not forbidden
    if not allowed:
        reason = "database URL must include staging, stage, test, local, or dev"
    elif forbidden:
        reason = "database URL contains forbidden production marker"
    else:
        reason = "safe staging/test marker present"
    return {
        "ok": ok,
        "connected": False,
        "reason": reason,
        "database_name": database_name,
        "matched_allowed_markers": allowed,
        "matched_forbidden_markers": forbidden,
        "allowed_markers": list(ALLOWED_DB_MARKERS),
        "forbidden_markers": list(FORBIDDEN_DB_MARKERS),
    }


def _namespace() -> dict[str, str]:
    raw_namespace = (os.environ.get(NAMESPACE_ENV) or DEFAULT_NAMESPACE).strip() or DEFAULT_NAMESPACE
    normalized = "".join(char if char.isalnum() or char == "_" else "_" for char in raw_namespace).strip("_")
    normalized = normalized or DEFAULT_NAMESPACE
    prefix = f"{normalized}_"
    return {
        "template_code_prefix": prefix,
        "operator": (os.environ.get(OPERATOR_ENV) or DEFAULT_OPERATOR).strip() or DEFAULT_OPERATOR,
        "idempotency_key_prefix": prefix,
    }


def _base_report(*, dry_run: bool, execute_writes: bool) -> dict[str, Any]:
    return {
        "ok": False,
        "dry_run": dry_run,
        "execute_writes": execute_writes,
        "db_url_safety": {},
        "namespace": _namespace(),
        "tests_run": 0,
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "details": [],
        "side_effect_safety": {
            "external_calls_executed": False,
            "automation_execution_executed": False,
            "outbound_send_executed": False,
            "route_owner_changed": False,
            "production_compat_changed": False,
        },
        "production_data_used": False,
        "route_owner_changed": False,
        "production_compat_changed": False,
    }


def _payload(name: str, code: str, *, status: str = "active") -> dict[str, Any]:
    return {
        "name": name,
        "code": code,
        "description": "Phase 4M staging smoke metadata only",
        "status": status,
        "rules": {
            "categories": [
                {
                    "category_key": f"{code}_category",
                    "category_name": f"{name} Category",
                    "sort_order": 1,
                    "option_mappings": [{"question_id": 4301, "option_id": 4401}],
                }
            ]
        },
        "conditions": {},
    }


def _record(report: dict[str, Any], name: str, fn: Callable[[], dict[str, Any] | None]) -> Any:
    report["tests_run"] += 1
    try:
        detail = fn() or {}
    except Exception as exc:  # noqa: BLE001 - staging package reports each failure.
        report["failed"] += 1
        report["details"].append({"name": name, "ok": False, "error": str(exc), "type": type(exc).__name__})
        return None
    report["passed"] += 1
    report["details"].append({"name": name, "ok": True, **detail})
    return detail


def _skip(report: dict[str, Any], name: str, reason: str) -> None:
    report["skipped"] += 1
    report["details"].append({"name": name, "ok": None, "skipped": True, "reason": reason})


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
        raise RuntimeError(f"staging database is missing required tables: {missing}")


def _init_engine(database_url: str) -> Any:
    from sqlalchemy import create_engine

    engine = create_engine(database_url, future=True)
    _assert_required_tables(engine)
    return engine


def _validate_backend(report: dict[str, Any]) -> bool:
    backend = (os.environ.get(BACKEND_ENV) or "").strip().lower()
    if backend != "sqlalchemy":
        report["details"].append(
            {
                "name": "backend_config",
                "ok": False,
                "error": f"{BACKEND_ENV}=sqlalchemy is required",
            }
        )
        report["failed"] += 1
        return False
    report["details"].append({"name": "backend_config", "ok": True, "backend": backend})
    report["passed"] += 1
    return True


def _run_dry_run_validations(report: dict[str, Any]) -> None:
    sys.path.insert(0, str(ROOT))
    from aicrm_next.automation_engine.profile_segments import normalize_profile_segment_template_payload
    from aicrm_next.shared.errors import ContractError

    namespace = report["namespace"]
    token = uuid.uuid4().hex[:8]
    code_prefix = namespace["template_code_prefix"]

    _record(
        report,
        "validate_create_payload",
        lambda: {
            "normalized_code": normalize_profile_segment_template_payload(
                _payload(f"Phase 4M Dry Run {token}", f"{code_prefix}{token}_create")
            )["code"]
        },
    )
    _record(
        report,
        "validate_idempotency_plan",
        lambda: {
            "idempotency_key_prefix": namespace["idempotency_key_prefix"],
            "requires_execute_writes_for_persistence": True,
        },
    )
    _record(
        report,
        "validate_update_payload",
        lambda: {
            "normalized_name": normalize_profile_segment_template_payload(
                {"name": f"Phase 4M Dry Run Update {token}", "status": "inactive", "rules": {}, "conditions": {}},
                partial=True,
                existing=_payload("Existing", f"{code_prefix}{token}_existing"),
            )["name"]
        },
    )

    def dangerous_rejected() -> dict[str, Any]:
        try:
            normalize_profile_segment_template_payload(
                _payload(f"Phase 4M Dangerous {token}", f"{code_prefix}{token}_danger") | {"rules": {"timer": True}}
            )
        except ContractError:
            return {"dangerous_rejected": True}
        raise AssertionError("dangerous field was not rejected")

    _record(report, "validate_dangerous_field_rejection", dangerous_rejected)


def _run_execute_writes(report: dict[str, Any], database_url: str) -> None:
    sys.path.insert(0, str(ROOT))
    from aicrm_next.automation_engine.profile_segment_repository import (
        ProfileSegmentTemplateIdempotencyConflict,
        SqlAlchemyProfileSegmentTemplateRepository,
    )
    from aicrm_next.shared.errors import ContractError, NotFoundError

    engine = _init_engine(database_url)
    report["db_url_safety"]["connected"] = True
    repo = SqlAlchemyProfileSegmentTemplateRepository(engine)
    namespace = report["namespace"]
    token = uuid.uuid4().hex[:8]
    code_prefix = f"{namespace['template_code_prefix']}{token}_"
    idem_prefix = f"{namespace['idempotency_key_prefix']}{token}_"
    operator = namespace["operator"]
    created_ref: dict[str, Any] = {}

    _record(report, "catalog", lambda: {"total": repo.profile_segment_template_catalog()["total"]})
    _record(report, "list", lambda: {"total": repo.list_profile_segment_templates()[1]})
    _record(report, "options", lambda: {"enabled_total": repo.list_profile_segment_templates(enabled_only=True)[1]})

    def create_seed() -> dict[str, Any]:
        result = repo.create_profile_segment_template(
            _payload(f"Phase 4M Seed {token}", f"{code_prefix}seed"),
            idempotency_key=f"{idem_prefix}seed",
            operator=operator,
        )
        created_ref["template_id"] = result["template"]["id"]
        return {"template_id": created_ref["template_id"]}

    _record(report, "create_with_idempotency", create_seed)
    _record(report, "detail", lambda: {"template_id": repo.get_profile_segment_template(int(created_ref["template_id"]))["id"]})

    def create_replay() -> dict[str, Any]:
        payload = _payload(f"Phase 4M Replay {token}", f"{code_prefix}replay")
        first = repo.create_profile_segment_template(payload, idempotency_key=f"{idem_prefix}replay", operator=operator)
        replay = repo.create_profile_segment_template(payload, idempotency_key=f"{idem_prefix}replay", operator=operator)
        if first["template"]["id"] != replay["template"]["id"] or replay.get("idempotent_replay") is not True:
            raise AssertionError("idempotent replay did not return same template")
        return {"template_id": first["template"]["id"], "idempotent_replay": True}

    _record(report, "create_replay", create_replay)

    def create_conflict() -> dict[str, Any]:
        payload = _payload(f"Phase 4M Conflict {token}", f"{code_prefix}conflict")
        repo.create_profile_segment_template(payload, idempotency_key=f"{idem_prefix}conflict", operator=operator)
        try:
            repo.create_profile_segment_template(
                _payload(f"Phase 4M Conflict Other {token}", f"{code_prefix}conflict_other"),
                idempotency_key=f"{idem_prefix}conflict",
                operator=operator,
            )
        except ProfileSegmentTemplateIdempotencyConflict:
            return {"conflict_rejected": True}
        raise AssertionError("idempotency conflict was not rejected")

    _record(report, "create_conflict", create_conflict)

    def duplicate_template() -> dict[str, Any]:
        try:
            repo.create_profile_segment_template(
                _payload(f"Phase 4M Seed {token}", f"{code_prefix}seed"),
                idempotency_key=f"{idem_prefix}duplicate",
                operator=operator,
            )
        except ContractError:
            return {"duplicate_rejected": True}
        raise AssertionError("duplicate template was not rejected")

    _record(report, "duplicate_template_rejected", duplicate_template)

    def update_existing() -> dict[str, Any]:
        result = repo.update_profile_segment_template(
            int(created_ref["template_id"]),
            {
                "name": f"Phase 4M Seed Updated {token}",
                "status": "inactive",
                "rules": {"categories": [{"category_key": f"{code_prefix}updated", "category_name": "Updated", "sort_order": 2}]},
            },
            operator=operator,
        )
        if not result.get("rollback", {}).get("before") or not result.get("rollback", {}).get("after"):
            raise AssertionError("rollback before/after snapshot missing")
        return {"template_id": created_ref["template_id"], "rollback_payload_present": True}

    _record(report, "update_existing", update_existing)

    def update_missing() -> dict[str, Any]:
        try:
            repo.update_profile_segment_template(999999999, {"name": "missing"}, operator=operator)
        except NotFoundError:
            return {"not_found": True}
        raise AssertionError("missing update did not return not-found")

    _record(report, "update_missing", update_missing)

    def invalid_payload() -> dict[str, Any]:
        try:
            repo.create_profile_segment_template(
                {"name": "", "code": f"{code_prefix}invalid", "status": "active", "rules": {}, "conditions": {}},
                idempotency_key=f"{idem_prefix}invalid",
                operator=operator,
            )
        except ContractError:
            return {"invalid_rejected": True}
        raise AssertionError("invalid payload was accepted")

    _record(report, "invalid_payload_rejected", invalid_payload)

    def dangerous_field() -> dict[str, Any]:
        try:
            repo.create_profile_segment_template(
                _payload(f"Phase 4M Dangerous {token}", f"{code_prefix}danger") | {"rules": {"timer": True}},
                idempotency_key=f"{idem_prefix}danger",
                operator=operator,
            )
        except ContractError:
            return {"dangerous_rejected": True}
        raise AssertionError("dangerous field was accepted")

    _record(report, "dangerous_field_rejected", dangerous_field)

    def audit_and_rollback() -> dict[str, Any]:
        events = repo.list_profile_segment_template_audit_events()
        if not events:
            raise AssertionError("audit row missing")
        latest = events[0]
        if "rollback_payload" not in latest or not latest.get("side_effect_safety"):
            raise AssertionError("audit rollback or side-effect evidence missing")
        if any(bool(value) for value in latest["side_effect_safety"].values()):
            raise AssertionError("side-effect flag was true")
        return {"audit_events": len(events), "latest_operation": latest.get("operation")}

    _record(report, "audit_log_created", audit_and_rollback)
    _record(report, "rollback_payload_present", audit_and_rollback)
    _record(report, "side_effect_safety_false", audit_and_rollback)


def run_package(*, execute_writes: bool) -> dict[str, Any]:
    dry_run = not execute_writes
    report = _base_report(dry_run=dry_run, execute_writes=execute_writes)
    database_url = os.environ.get(STAGING_DB_ENV)
    report["db_url_safety"] = _db_url_safety(database_url)
    report["tests_run"] += 1
    if not report["db_url_safety"].get("ok"):
        report["failed"] += 1
        report["details"].append({"name": "db_url_safety", "ok": False, "error": report["db_url_safety"].get("reason")})
        return report
    report["passed"] += 1
    report["details"].append({"name": "db_url_safety", "ok": True, "reason": report["db_url_safety"].get("reason")})

    report["tests_run"] += 1
    if not _validate_backend(report):
        return report

    _run_dry_run_validations(report)
    if dry_run:
        for name in ("catalog", "list", "options", "detail", "create_with_idempotency", "create_replay", "create_conflict", "duplicate_template_rejected", "update_existing", "update_missing", "audit_log_created", "rollback_payload_present", "side_effect_safety_false"):
            _skip(report, name, "dry-run mode; pass --execute-writes for staging DB write smoke after owner approval")
    else:
        _run_execute_writes(report, str(database_url))

    report["ok"] = report["failed"] == 0
    return report


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=_json_default) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4M Profile Segment Template Staging Smoke Package",
        "",
        f"- ok: {str(report.get('ok')).lower()}",
        f"- dry_run: {str(report.get('dry_run')).lower()}",
        f"- execute_writes: {str(report.get('execute_writes')).lower()}",
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
        if detail.get("skipped"):
            status = "SKIP"
        else:
            status = "PASS" if detail.get("ok") else "FAIL"
        lines.append(f"- {detail.get('name')}: {status}")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4M profile segment template staging smoke package.")
    parser.add_argument("--dry-run", action="store_true", default=True, help="Default mode; validates config and payloads without DB writes.")
    parser.add_argument("--execute-writes", action="store_true", help="Owner-approved staging DB write smoke.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)

    report = run_package(execute_writes=bool(args.execute_writes))
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(f"ok: {str(report.get('ok')).lower()}")
    print(f"dry_run: {str(report.get('dry_run')).lower()}")
    print(f"execute_writes: {str(report.get('execute_writes')).lower()}")
    print(f"tests_run: {report.get('tests_run', 0)}")
    print(f"failed: {report.get('failed', 0)}")
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
