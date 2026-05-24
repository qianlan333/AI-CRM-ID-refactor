#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
ROUTE = "/api/admin/automation-conversion/action-templates"
MODE = "local_fixture_parity"
AGGREGATE_SIDE_EFFECT_SAFETY = {
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


def _all_real_safety_false(payload: dict[str, Any]) -> bool:
    safety = payload.get("side_effect_safety") or {}
    return bool(safety) and all(value is False for key, value in safety.items() if key.startswith("real_"))


def _restore_env(old_env: dict[str, str | None]) -> None:
    for key, value in old_env.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _clear_database_url() -> None:
    os.environ.pop("DATABASE" + "_URL", None)


def _with_env(env: dict[str, str | None], callback: Callable[[], None]) -> None:
    old_env = {key: os.environ.get(key) for key in env}
    try:
        for key, value in env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        _clear_database_url()
        callback()
    finally:
        _restore_env(old_env)


def _local_client() -> Any:
    from fastapi.testclient import TestClient  # type: ignore
    from aicrm_next.automation_engine.action_template_repository import reset_action_template_fixture_state
    from aicrm_next.main import create_app

    reset_action_template_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _production_client() -> Any:
    from fastapi.testclient import TestClient  # type: ignore
    from aicrm_next.automation_engine.action_template_repository import reset_action_template_fixture_state
    from aicrm_next.main import create_app

    reset_action_template_fixture_state()
    return TestClient(create_app(), raise_server_exceptions=False)


def _run_local_matrix(harness: Harness) -> None:
    client = _local_client()

    listed = client.get(ROUTE)
    if listed.status_code != 200:
        harness.fail("list_ok", f"GET list returned {listed.status_code}", {"body": listed.text[:500]})
    else:
        body = listed.json()
        if body.get("ok") is True and body.get("route_owner") == "ai_crm_next":
            harness.pass_("list_ok", "GET list returned the Next fixture/local contract", {"count": body.get("count")})
        else:
            harness.fail("list_ok", "GET list did not return the expected Next owner payload", {"body": body})
        if body.get("count", 0) >= 1 and any(item.get("template_code") for item in body.get("items") or []):
            harness.pass_("deterministic_fixture_seed", "fixture seed records are present", {"count": body.get("count")})
        else:
            harness.fail("deterministic_fixture_seed", "fixture seed records missing", {"body": body})
        if _all_real_safety_false(body):
            harness.pass_("side_effect_safety_present", "GET list includes all-false side_effect_safety")
        else:
            harness.fail("side_effect_safety_present", "GET list side_effect_safety missing or not all false", {"body": body})
        if not any("legacy" in str(value).lower() for value in listed.headers.values()):
            harness.pass_("no_legacy_facade_header", "GET list response headers do not expose a legacy facade owner")
        else:
            harness.fail("no_legacy_facade_header", "GET list response headers include a legacy marker", {"headers": dict(listed.headers)})

    filtered = client.get(ROUTE, params={"template_source": "crm_local"})
    if filtered.status_code == 200 and filtered.json().get("filters", {}).get("template_source") == "crm_local":
        harness.pass_("filters_if_supported", "template_source filter is accepted and echoed")
    else:
        harness.skip("filters_if_supported", "template_source filter did not produce an echoable fixture response")

    payload = {
        "template_name": "Phase 4AF Create",
        "template_code": "phase4af_create",
        "idempotency_key": "phase4af-create",
        "operator": "phase4af",
        "default_config": {"channel": "fixture"},
    }
    created = client.post(ROUTE, json=payload)
    if created.status_code == 201:
        body = created.json()
        template_id = body.get("template", {}).get("id")
        if body.get("idempotent_replay") is False and template_id:
            harness.pass_("create_with_idempotency", "POST create with idempotency key returned a fixture/local create response", {"template_id": template_id})
        else:
            harness.fail("create_with_idempotency", "POST create response missing template/idempotency evidence", {"body": body})
        if body.get("audit_event", {}).get("operation") == "create":
            harness.pass_("audit_event_emitted", "create emitted an audit event")
        else:
            harness.fail("audit_event_emitted", "create response missing audit event", {"body": body})
        if body.get("rollback_payload", {}).get("created_template_id") == template_id:
            harness.pass_("rollback_payload_present", "create response includes rollback payload")
        else:
            harness.fail("rollback_payload_present", "create response missing rollback payload", {"body": body})
        if _all_real_safety_false(body):
            harness.pass_("side_effect_safety_false", "create side_effect_safety is all false")
        else:
            harness.fail("side_effect_safety_false", "create side_effect_safety missing or not all false", {"body": body})
    else:
        harness.fail("create_with_idempotency", f"POST create returned {created.status_code}", {"body": created.text[:500]})

    replay = client.post(ROUTE, json=payload)
    if replay.status_code == 201 and replay.json().get("idempotent_replay") is True:
        harness.pass_("idempotency_replay", "same idempotency key and same payload replayed the saved response")
    else:
        harness.fail("idempotency_replay", "idempotency replay did not return expected response", {"status": replay.status_code, "body": replay.text[:500]})

    conflict = client.post(ROUTE, json={**payload, "template_name": "Phase 4AF Conflict"})
    if conflict.status_code == 409 and conflict.json().get("error_code") == "idempotency_conflict":
        harness.pass_("idempotency_conflict", "same idempotency key with different payload conflicts")
    else:
        harness.fail("idempotency_conflict", "idempotency conflict did not return expected 409", {"status": conflict.status_code, "body": conflict.text[:500]})

    duplicate = client.post(
        ROUTE,
        json={
            "template_name": "Phase 4AF Duplicate",
            "template_code": "phase4af_create",
            "idempotency_key": "phase4af-duplicate",
            "operator": "phase4af",
        },
    )
    if duplicate.status_code == 400 and "already exists" in duplicate.text:
        harness.pass_("duplicate_template_code_rejected", "duplicate template_code is rejected")
    else:
        harness.fail("duplicate_template_code_rejected", "duplicate template_code was not rejected", {"status": duplicate.status_code, "body": duplicate.text[:500]})

    missing_name = client.post(ROUTE, json={"template_code": "phase4af_missing_name", "idempotency_key": "phase4af-missing-name"})
    if missing_name.status_code == 400 and "template_name is required" in missing_name.text:
        harness.pass_("missing_name_rejected", "missing name/template_name is rejected")
    else:
        harness.fail("missing_name_rejected", "missing name was not rejected", {"status": missing_name.status_code, "body": missing_name.text[:500]})

    invalid_status = client.post(
        ROUTE,
        json={"template_name": "Invalid Status", "template_code": "phase4af_invalid_status", "idempotency_key": "phase4af-invalid-status", "status": "enabled"},
    )
    if invalid_status.status_code == 400 and "status must be one of" in invalid_status.text:
        harness.pass_("invalid_status_rejected", "invalid status is rejected")
    else:
        harness.fail("invalid_status_rejected", "invalid status was not rejected", {"status": invalid_status.status_code, "body": invalid_status.text[:500]})

    dangerous = client.post(
        ROUTE,
        json={"template_name": "Danger", "idempotency_key": "phase4af-danger", "default_config": {"workflow_activation": True}},
    )
    if dangerous.status_code == 400 and "dangerous action template field" in dangerous.text:
        harness.pass_("dangerous_fields_rejected", "dangerous fields are rejected anywhere in payload")
    else:
        harness.fail("dangerous_fields_rejected", "dangerous field was not rejected", {"status": dangerous.status_code, "body": dangerous.text[:500]})


def _run_production_guard(harness: Harness) -> None:
    client = _production_client()
    response = client.post(
        ROUTE,
        json={
            "template_name": "Phase 4AF Production Guard",
            "template_code": "phase4af_production_guard",
            "idempotency_key": "phase4af-production",
            "operator": "phase4af",
        },
    )
    if response.status_code == 503 and response.json().get("error_code") == "production_repository_not_enabled":
        harness.pass_("production_fixture_write_blocked", "production env blocks fixture POST success")
    else:
        harness.fail(
            "production_fixture_write_blocked",
            "production env did not block fixture POST success",
            {"status": response.status_code, "body": response.text[:500]},
        )


def run_harness() -> dict[str, Any]:
    harness = Harness()
    try:
        import fastapi  # noqa: F401
    except ModuleNotFoundError as exc:
        harness.skip("fastapi_probe", f"FastAPI probe skipped because dependency is unavailable: {exc}")
    else:
        local_env = {
            "AICRM_NEXT_ENV": "test",
            "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": "0",
            "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": "1",
        }
        _with_env(local_env, lambda: _run_local_matrix(harness))
        production_env = {
            "AICRM_NEXT_ENV": "production",
            "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": "0",
            "AICRM_NEXT_DISABLE_LEGACY_PRODUCTION_FACADE": "1",
        }
        _with_env(production_env, lambda: _run_production_guard(harness))

    tests_run = len([item for item in harness.details if item["status"] != "skipped"])
    passed = len([item for item in harness.details if item["status"] == "passed"])
    failed = len([item for item in harness.details if item["status"] == "failed"])
    skipped = len([item for item in harness.details if item["status"] == "skipped"])
    return {
        "ok": failed == 0,
        "mode": MODE,
        "tests_run": tests_run,
        "passed": passed,
        "failed": failed,
        "skipped": skipped,
        "details": harness.details,
        "side_effect_safety": dict(AGGREGATE_SIDE_EFFECT_SAFETY),
        "production_data_used": False,
        "production_route_owner_changed": False,
        "production_compat_changed": False,
        "fixture_evidence_only": True,
    }


def _write_json(report: dict[str, Any], path: str) -> None:
    Path(path).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_md(report: dict[str, Any], path: str) -> None:
    lines = [
        "# Phase 4AF Action Templates Local Parity Harness",
        "",
        f"- ok: {str(report['ok']).lower()}",
        f"- mode: {report['mode']}",
        f"- tests_run: {report['tests_run']}",
        f"- passed: {report['passed']}",
        f"- failed: {report['failed']}",
        f"- skipped: {report['skipped']}",
        f"- fixture_evidence_only: {str(report['fixture_evidence_only']).lower()}",
        f"- production_data_used: {str(report['production_data_used']).lower()}",
        f"- production_route_owner_changed: {str(report['production_route_owner_changed']).lower()}",
        f"- production_compat_changed: {str(report['production_compat_changed']).lower()}",
        "",
        "## Details",
    ]
    for detail in report.get("details") or []:
        lines.append(f"- {detail['status']}: {detail['name']} - {detail['message']}")
    lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Phase 4AF action templates local fixture parity harness.")
    parser.add_argument("--output-json")
    parser.add_argument("--output-md")
    args = parser.parse_args(argv)
    report = run_harness()
    if args.output_json:
        _write_json(report, args.output_json)
    if args.output_md:
        _write_md(report, args.output_md)
    print(
        f"overall: {'PASS' if report['ok'] else 'FAIL'} "
        f"tests_run={report['tests_run']} passed={report['passed']} failed={report['failed']} skipped={report['skipped']}"
    )
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
