#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from fastapi.testclient import TestClient
except ModuleNotFoundError:
    venv_python = ROOT / ".venv" / "bin" / "python"
    if venv_python.exists() and not str(sys.executable).startswith(str(ROOT / ".venv")):
        os.execv(str(venv_python), [str(venv_python), *sys.argv])
    raise

TIMER_ROUTES = [
    "/api/admin/automation-conversion/reply-monitor/run-due",
    "/api/admin/automation-conversion/reply-monitor/capture",
    "/api/admin/automation-conversion/jobs/run-due",
    "/api/admin/cloud-orchestrator/campaigns/run-due",
]


@contextmanager
def timer_probe_env():
    keys = {
        "AICRM_NEXT_ENV": os.environ.get("AICRM_NEXT_ENV"),
        "AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE": os.environ.get("AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"),
        "AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN": os.environ.get("AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN"),
        "DATABASE_URL": os.environ.get("DATABASE_URL"),
        "AUTOMATION_INTERNAL_API_TOKEN": os.environ.get("AUTOMATION_INTERNAL_API_TOKEN"),
        "SECRET_KEY": os.environ.get("SECRET_KEY"),
    }
    os.environ["AICRM_NEXT_ENV"] = "production"
    os.environ["AICRM_NEXT_ENABLE_LEGACY_PRODUCTION_FACADE"] = "1"
    os.environ["AICRM_NEXT_ENABLE_PRODUCTION_PROBE_DRY_RUN"] = "1"
    os.environ["DATABASE_URL"] = "postgresql://probe:probe@127.0.0.1:1/aicrm_probe"
    os.environ["AUTOMATION_INTERNAL_API_TOKEN"] = "probe-token"
    os.environ["SECRET_KEY"] = "next-timer-route-readiness"
    try:
        yield
    finally:
        for key, value in keys.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def _client() -> TestClient:
    module = importlib.import_module("aicrm_next.main")
    return TestClient(module.create_app())


def run_check() -> dict[str, Any]:
    with timer_probe_env():
        client = _client()
        results: dict[str, Any] = {}
        for route in TIMER_ROUTES:
            unauth = client.post(route, json={}, follow_redirects=False)
            auth = client.post(
                route,
                json={},
                headers={"Authorization": "Bearer probe-token", "X-AICRM-Dry-Run": "1"},
                follow_redirects=False,
            )
            results[route] = {
                "unauth_status": unauth.status_code,
                "auth_status": auth.status_code,
                "route_not_404": unauth.status_code != 404 and auth.status_code != 404,
                "auth_guard_present": unauth.status_code in {401, 403},
                "dry_run_or_noop_available": auth.status_code != 404,
            }
        overview = client.get("/api/admin/automation-conversion/overview", follow_redirects=False)
        try:
            overview_payload: Any = overview.json()
        except Exception:
            overview_payload = {}
        automation_production_data_ready = (
            overview.status_code == 200
            and str(overview_payload.get("generated_at") or "").strip().lower() != "fixture"
            and str(overview_payload.get("status") or "").strip().lower() != "partial"
            and str(overview_payload.get("source_status") or "").strip().lower() == "production_postgres"
        )
    blockers = [
        route
        for route, payload in results.items()
        if not payload["route_not_404"] or not payload["auth_guard_present"] or not payload["dry_run_or_noop_available"]
    ]
    if not automation_production_data_ready:
        blockers.append("automation_production_data_not_ready")
    result = {
        "ok": not blockers,
        "blockers": blockers,
        "timer_routes": results,
        "automation_overview_status": overview.status_code,
        "automation_overview": overview_payload,
        "automation_production_data_ready": automation_production_data_ready,
        "safe_to_enable_timers": not blockers and automation_production_data_ready,
        "recommendation": "READY_TO_ENABLE_TIMERS_AFTER_SERVER_ENV_TOKEN_VERIFICATION" if not blockers else "TIMER_ROUTES_NOT_READY",
    }
    return result


def write_outputs(result: dict[str, Any], output_md: str | None, output_json: str | None) -> None:
    if output_json:
        Path(output_json).write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if output_md:
        lines = [
            "# Next Timer Route Readiness",
            "",
            f"- ok: {result['ok']}",
            f"- safe_to_enable_timers: {result['safe_to_enable_timers']}",
            f"- automation_production_data_ready: {result['automation_production_data_ready']}",
            f"- blockers: {result['blockers']}",
            "",
            "## Timer Routes",
        ]
        for route, payload in result["timer_routes"].items():
            lines.append(
                f"- {route}: unauth={payload['unauth_status']} auth={payload['auth_status']} "
                f"guard={payload['auth_guard_present']}"
            )
        Path(output_md).write_text("\n".join(lines) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-md")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    result = run_check()
    write_outputs(result, args.output_md, args.output_json)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
