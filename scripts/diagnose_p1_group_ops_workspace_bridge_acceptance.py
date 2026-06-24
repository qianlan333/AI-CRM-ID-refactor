#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json


ROOT = ensure_repo_root_on_path()

EXPECTED_ROUTES = [
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/bridge-push-center",
    "/api/admin/p1/group-ops-workspace/governance/{review_id}/push-center-bridge",
]

EXPECTED_STATIC_ASSETS = [
    "aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_governance_api.js",
    "aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_layout.js",
    "aicrm_next/frontend_compat/static/admin_console/p1/p1_group_ops_workspace/workspace_view_state.js",
]

EXPECTED_MIGRATIONS = [
    "migrations/versions/0047_group_ops_workspace_drafts.py",
    "migrations/versions/0048_group_ops_workspace_request_review_audit_action.py",
    "migrations/versions/0049_group_ops_workspace_governance.py",
]

FORBIDDEN_EXECUTION_TOKENS = [
    "create_external_effect",
    "external_effect_service",
    "create_broadcast_job",
    "InternalEventService",
    "webhook.send",
    "message_send",
    "execute_external",
]


def _read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def _route_manifest_check() -> dict[str, Any]:
    source = _read("docs/architecture/route_ownership_manifest.yml")
    route_results = []
    for route in EXPECTED_ROUTES:
        route_results.append(
            {
                "route": route,
                "present": route in source,
                "runtime_owner_ai_crm_next": "runtime_owner: ai_crm_next" in source[source.find(route): source.find(route) + 500],
                "capability_owner_automation_engine": "capability_owner: automation_engine" in source[source.find(route): source.find(route) + 500],
                "external_effects_none": "external_effects: none" in source[source.find(route): source.find(route) + 500],
                "requires_auth_true": "requires_auth: true" in source[source.find(route): source.find(route) + 500],
            }
        )
    return {
        "ok": all(
            item["present"]
            and item["runtime_owner_ai_crm_next"]
            and item["capability_owner_automation_engine"]
            and item["external_effects_none"]
            and item["requires_auth_true"]
            for item in route_results
        ),
        "routes": route_results,
    }


def _registered_route_check() -> dict[str, Any]:
    try:
        from aicrm_next.main import app

        registered = {getattr(route, "path", "") for route in app.routes}
        return {
            "ok": all(route in registered for route in EXPECTED_ROUTES),
            "registered_routes": {route: route in registered for route in EXPECTED_ROUTES},
        }
    except Exception as exc:  # pragma: no cover - defensive production diagnostic
        return {"ok": False, "error": f"route_registry_unavailable: {exc}"}


def _auth_fail_closed_check() -> dict[str, Any]:
    try:
        from fastapi.testclient import TestClient

        from aicrm_next.main import app

        client = TestClient(app)
        post = client.post(
            "/api/admin/p1/group-ops-workspace/governance/gowg_diagnostic/bridge-push-center",
            json={
                "idempotency_key": "diagnostic-readonly-no-write",
                "client_snapshot_hash": "diagnostic-safe-snapshot",
                "allowlist_hash": "diagnostic-safe-allowlist",
                "allowlist_count": 0,
            },
        )
        get = client.get("/api/admin/p1/group-ops-workspace/governance/gowg_diagnostic/push-center-bridge")
        responses = [post, get]
        return {
            "ok": all(response.status_code in {401, 403} for response in responses),
            "post_status": post.status_code,
            "get_status": get.status_code,
            "post_real_external_call_executed": (post.json() if post.headers.get("content-type", "").startswith("application/json") else {}).get("real_external_call_executed", False),
            "get_real_external_call_executed": (get.json() if get.headers.get("content-type", "").startswith("application/json") else {}).get("real_external_call_executed", False),
        }
    except Exception as exc:  # pragma: no cover - defensive production diagnostic
        return {"ok": False, "error": f"auth_fail_closed_check_unavailable: {exc}"}


def _migration_check() -> dict[str, Any]:
    paths = {path: (ROOT / path).exists() for path in EXPECTED_MIGRATIONS}
    heads = subprocess.run(
        [sys.executable, "-m", "alembic", "heads"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    return {
        "ok": all(paths.values()) and heads.returncode == 0 and "0049_group_ops_workspace_governance" in heads.stdout,
        "migration_files": paths,
        "alembic_heads_ok": heads.returncode == 0,
        "alembic_heads_contains_governance": "0049_group_ops_workspace_governance" in heads.stdout,
        "alembic_error": heads.stderr.strip(),
    }


def _static_asset_check() -> dict[str, Any]:
    assets = {asset: (ROOT / asset).exists() for asset in EXPECTED_STATIC_ASSETS}
    return {"ok": all(assets.values()), "assets": assets}


def _source_inventory_check() -> dict[str, Any]:
    service_source = _read("aicrm_next/automation_engine/group_ops/governance_service.py")
    api_source = _read("aicrm_next/automation_engine/group_ops/governance_api.py")
    frontend_source = _read("frontend/admin/p1_group_ops_workspace/workspace_governance_api.ts")
    bridge_slice = service_source[service_source.find("def bridge_push_center") :]
    forbidden_hits = {
        token: {
            "service_bridge": token in bridge_slice,
            "api": token in api_source,
            "frontend": token in frontend_source,
        }
        for token in FORBIDDEN_EXECUTION_TOKENS
    }
    response_flags_ok = all(
        token in service_source
        for token in [
            '"external_effect_job_created": False',
            '"broadcast_job_created": False',
            '"internal_event_created": False',
            '"real_external_call": False',
            '"execution_status": "push_center_pending_not_sent"',
            '"can_claim_pass_90_plus": False',
        ]
    )
    return {
        "ok": response_flags_ok and not any(any(hit.values()) for hit in forbidden_hits.values()),
        "response_flags_ok": response_flags_ok,
        "forbidden_execution_token_hits": forbidden_hits,
    }


def _business_closure_check() -> dict[str, Any]:
    try:
        from scripts.diagnose_business_closure_acceptance import run

        payload = run(scenario="all")
        summary = payload.get("summary") or {}
        return {
            "ok": payload.get("ok") is True and summary.get("can_claim_90_plus") is False,
            "business_closure_ok": payload.get("ok") is True,
            "can_claim_90_plus": summary.get("can_claim_90_plus"),
            "closeout_status": summary.get("closeout_status"),
            "real_external_call_executed": payload.get("real_external_call_executed"),
            "production_write_executed": payload.get("production_write_executed"),
        }
    except Exception as exc:  # pragma: no cover - defensive production diagnostic
        return {"ok": False, "error": f"business_closure_check_unavailable: {exc}"}


def run(*, allow_write_validation: bool = False) -> dict[str, Any]:
    route_manifest = _route_manifest_check()
    registered_routes = _registered_route_check()
    auth_fail_closed = _auth_fail_closed_check()
    migrations = _migration_check()
    static_assets = _static_asset_check()
    source_inventory = _source_inventory_check()
    business_closure = _business_closure_check()
    write_validation_status = (
        "WRITE_VALIDATION_NOT_IMPLEMENTED_IN_DIAGNOSTIC"
        if allow_write_validation
        else "SKIPPED_WRITE_VALIDATION_SAFE_MODE"
    )
    checks = {
        "route_manifest": route_manifest,
        "registered_routes": registered_routes,
        "auth_fail_closed": auth_fail_closed,
        "migrations": migrations,
        "static_assets": static_assets,
        "source_inventory": source_inventory,
        "business_closure": business_closure,
    }
    ok = all(item.get("ok") is True for item in checks.values())
    return {
        "ok": ok,
        "diagnostic": "p1_group_ops_workspace_bridge_acceptance",
        "mode": "dry_run_read_only",
        "write_validation_status": write_validation_status,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "external_effect_job_created": False,
        "broadcast_job_created": False,
        "internal_event_created": False,
        "can_claim_pass_90_plus": False,
        "checks": checks,
        "summary": {
            "bridge_contract_ready_for_final_closeout": ok,
            "pending_projection_not_sent": True,
            "no_execution_contract": source_inventory.get("ok") is True,
            "auth_fail_closed": auth_fail_closed.get("ok") is True,
            "write_validation": write_validation_status,
            "next_action": "final closeout / acceptance report PR; external effect execution remains out of scope",
        },
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run P1 Group Ops Workspace Push Center bridge acceptance diagnostic.")
    parser.add_argument(
        "--allow-write-validation",
        action="store_true",
        help="Reserved for an explicitly approved operator window. This script still does not implement production writes.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run(allow_write_validation=bool(args.allow_write_validation))
    print_json(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
