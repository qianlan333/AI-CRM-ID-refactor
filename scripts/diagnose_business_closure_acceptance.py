#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from typing import Any

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


SCENARIOS: dict[str, dict[str, Any]] = {
    "group_ops_gray_send": {
        "title": "Group Ops gray send acceptance",
        "capability_owner": "automation_engine",
        "routes": [
            "/api/automation/group-ops/webhooks/{webhook_key}",
            "/api/admin/push-center/jobs/{job_id}/reconciliation",
        ],
        "required_env": ["AICRM_GROUP_OPS_GRAY_SEND_APPROVED", "AICRM_GROUP_OPS_GRAY_SEND_RECEIVER_ALLOWLIST"],
        "checks": [
            "dry-run plan exists before real receiver execution",
            "receiver is allowlisted before any real send",
            "Push Center reconciliation can explain job/effect/attempt status",
        ],
        "success_criteria": "Approved receiver gray send can be reconciled in Push Center.",
    },
    "ops_plan_to_broadcast": {
        "title": "Ops plan approval to broadcast E2E acceptance",
        "capability_owner": "platform_foundation",
        "routes": [
            "/api/admin/internal-events/{event_id}/reconciliation",
            "/api/admin/cloud-orchestrator/campaigns/{campaign_code}/approve",
            "/api/admin/push-center/jobs",
        ],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN"],
        "checks": [
            "approval event creates or reuses one internal_event",
            "consumer run creates or links one business job",
            "duplicate approval does not duplicate jobs",
        ],
        "success_criteria": "Approval can be traced to consumer run, job, and Push Center status.",
    },
    "external_orders_enablement": {
        "title": "External orders enablement acceptance",
        "capability_owner": "commerce",
        "routes": ["/api/external/orders", "/api/external/orders/{order_no}"],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN"],
        "checks": [
            "missing server token remains controlled unavailable",
            "missing or wrong bearer token is rejected",
            "correct bearer token can read local order projection",
        ],
        "success_criteria": "External systems can safely authenticate and read local order state.",
    },
    "external_orders_gray": {
        "title": "External orders gray acceptance",
        "capability_owner": "commerce",
        "routes": [
            "/api/external/orders",
            "/api/admin/wechat-shop/orders/{order_id}/sync",
            "/api/admin/push-center/jobs/{job_id}/reconciliation",
        ],
        "required_env": ["AUTOMATION_INTERNAL_API_TOKEN", "AICRM_EXTERNAL_ORDERS_GRAY_APPROVED"],
        "checks": [
            "gray source is approved before live order calls",
            "duplicate order payload is idempotent",
            "order/customer/channel/source correlation is visible",
        ],
        "success_criteria": "Gray order lifecycle can be reconciled without leaking token or customer data.",
    },
    "wecom_auth_operator": {
        "title": "WeCom auth operator readiness acceptance",
        "capability_owner": "auth_wecom",
        "routes": ["/auth/wecom/start", "/auth/wecom/callback"],
        "required_env": ["WECOM_CORP_ID", "WECOM_AGENT_ID", "ADMIN_LOGIN_REDIRECT_URI"],
        "checks": [
            "auth start route is reachable",
            "missing code and invalid state are controlled failures",
            "token exchange remains blocked unless separately approved",
        ],
        "success_criteria": "Operator auth readiness is explainable without exposing secrets.",
    },
    "wecom_callback_gray": {
        "title": "WeCom callback gray acceptance",
        "capability_owner": "channel_entry",
        "routes": ["/wecom/external-contact/callback", "/api/wecom/events"],
        "required_env": ["WECOM_CORP_ID", "WECOM_CONTACT_SECRET", "AICRM_WECOM_CALLBACK_GRAY_APPROVED"],
        "checks": [
            "invalid signature does not enqueue work",
            "duplicate callback reuses idempotency key",
            "accepted callback can be traced to event/job status",
        ],
        "success_criteria": "Gray callback can be verified, deduplicated, and reconciled.",
    },
    "core_admin_ops": {
        "title": "Core CRM admin operations acceptance",
        "capability_owner": "automation_engine",
        "routes": ["/admin/channels", "/api/admin/channels/{channel_id:int}", "/api/admin/channels/runtime-diagnosis"],
        "required_env": [],
        "checks": [
            "old draft #974 is closed or rebuilt from current main",
            "channel save errors expose FastAPI detail",
            "static asset cache behavior is covered before channel UX work ships",
        ],
        "success_criteria": "Operators can save and diagnose critical admin channel state.",
    },
}


def _present(env: dict[str, str], key: str) -> bool:
    return bool(str(env.get(key) or "").strip())


def _missing_env(env: dict[str, str], keys: list[str]) -> list[str]:
    return [key for key in keys if not _present(env, key)]


def _scenario_payload(
    name: str,
    *,
    execute: bool = False,
    receiver_token: str = "",
    order_no: str = "",
    plan_id: str = "",
    event_id: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    env = dict(env or os.environ)
    spec = SCENARIOS[name]
    missing = _missing_env(env, list(spec["required_env"]))
    requires_receiver = name in {"group_ops_gray_send", "wecom_callback_gray"}
    receiver_ready = not requires_receiver or bool(str(receiver_token or "").strip())
    execute_allowed = bool(execute and not missing and receiver_ready)
    unsafe_execute_requested = bool(execute and not execute_allowed)
    status = "blocked" if unsafe_execute_requested else ("ready_for_operator_execute" if execute_allowed else "dry_run_ready")
    return {
        "ok": not unsafe_execute_requested,
        "scenario": name,
        "title": spec["title"],
        "capability_owner": spec["capability_owner"],
        "dry_run": not execute_allowed,
        "execute_requested": bool(execute),
        "operator_execute_allowed": execute_allowed,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
        "status": status,
        "routes": list(spec["routes"]),
        "required_env": [
            {"key": key, "configured": _present(env, key), "value": "[redacted]" if _present(env, key) else ""}
            for key in spec["required_env"]
        ],
        "missing_env": missing,
        "inputs": {
            "receiver_token_configured": bool(receiver_token),
            "receiver_token": "[redacted]" if receiver_token else "",
            "order_no": order_no,
            "plan_id": plan_id,
            "event_id": event_id,
        },
        "checks": list(spec["checks"]),
        "success_criteria": spec["success_criteria"],
        "next_action": _next_action(name, unsafe_execute_requested, execute_allowed),
    }


def _next_action(name: str, unsafe_execute_requested: bool, execute_allowed: bool) -> str:
    if unsafe_execute_requested:
        return "Resolve missing approval/env/receiver inputs before any operator execution."
    if execute_allowed:
        return "Run the documented operator-owned gray acceptance steps; this diagnostic script still performs no external call."
    if name == "core_admin_ops":
        return "Close or rebuild #974 from current main before channel admin UX fixes."
    return "Attach this dry-run payload to the next acceptance PR and keep real execution disabled."


def run(
    *,
    scenario: str,
    execute: bool = False,
    receiver_token: str = "",
    order_no: str = "",
    plan_id: str = "",
    event_id: str = "",
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    names = list(SCENARIOS) if scenario == "all" else [scenario]
    items = [
        _scenario_payload(
            name,
            execute=execute,
            receiver_token=receiver_token,
            order_no=order_no,
            plan_id=plan_id,
            event_id=event_id,
            env=env,
        )
        for name in names
    ]
    return {
        "ok": all(item["ok"] for item in items),
        "scenario": scenario,
        "items": items,
        "real_external_call_executed": False,
        "production_write_executed": False,
        "deploy_or_env_modified": False,
    }


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Dry-run business closure acceptance diagnostics.")
    parser.add_argument("--scenario", choices=["all", *SCENARIOS.keys()], default="all")
    parser.add_argument("--execute", action="store_true", help="Request operator execution readiness; the script still performs no external call.")
    parser.add_argument("--receiver-token", default="")
    parser.add_argument("--order-no", default="")
    parser.add_argument("--plan-id", default="")
    parser.add_argument("--event-id", default="")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    payload = run(
        scenario=args.scenario,
        execute=bool(args.execute),
        receiver_token=args.receiver_token,
        order_no=args.order_no,
        plan_id=args.plan_id,
        event_id=args.event_id,
    )
    print_json(payload)
    return 0 if payload.get("ok") else 2


if __name__ == "__main__":
    sys.exit(main())
