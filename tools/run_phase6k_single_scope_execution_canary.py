#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from typing import Any


ROUTE_FAMILY = "/api/admin/automation-conversion/workflow-nodes*"
CAPABILITY = "workflow_nodes_metadata_execution_simulation"
REQUIRED_ENV_GATES = [
    "AICRM_PHASE6K_EXECUTION_CANARY_APPROVED",
    "AICRM_PHASE6K_EXECUTION_CONFIG_REVIEWED",
    "AICRM_PHASE6K_EXECUTION_ROLLBACK_OWNER_APPROVED",
    "AICRM_PHASE6K_EXECUTION_TARGET_APPROVED",
    "AICRM_PHASE6K_EXECUTION_KILL_SWITCH_REVIEWED",
]


def build_evidence(argv: list[str] | None = None) -> dict[str, Any]:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--shadow-run", action="store_true")
    parser.add_argument("--confirm-single-scope", action="store_true")
    parser.add_argument("--confirm-no-outbound-send", action="store_true")
    parser.add_argument("--confirm-no-live-external-call", action="store_true")
    parser.add_argument("--confirm-kill-switch-ready", action="store_true")
    parser.add_argument("--idempotency-key", default="")
    parser.add_argument("--operator", default="")
    args = parser.parse_args(argv)

    missing_env = [name for name in REQUIRED_ENV_GATES if os.environ.get(name) != "1"]
    missing_args: list[str] = []
    if not (args.dry_run or args.shadow_run):
        missing_args.append("--dry-run-or---shadow-run")
    if not args.confirm_single_scope:
        missing_args.append("--confirm-single-scope")
    if not args.confirm_no_outbound_send:
        missing_args.append("--confirm-no-outbound-send")
    if not args.confirm_no_live_external_call:
        missing_args.append("--confirm-no-live-external-call")
    if not args.confirm_kill_switch_ready:
        missing_args.append("--confirm-kill-switch-ready")
    if not args.idempotency_key:
        missing_args.append("--idempotency-key")
    if not args.operator:
        missing_args.append("--operator")

    mode_name = "dry_run" if args.dry_run else "shadow_run" if args.shadow_run else "not_selected"
    if missing_env:
        result_status = "not_executed_missing_required_gates"
    elif missing_args:
        result_status = "not_executed_missing_required_confirmations"
    else:
        result_status = "not_executed_owner_reviewed_single_scope_gate_ready"

    kill_switch_ready = (
        os.environ.get("AICRM_PHASE6K_EXECUTION_KILL_SWITCH_REVIEWED") == "1"
        and args.confirm_kill_switch_ready
    )
    return {
        "ok": True,
        "result_status": result_status,
        "route_family": ROUTE_FAMILY,
        "capability": CAPABILITY,
        "mode": mode_name,
        "single_scope_confirmed": bool(args.confirm_single_scope),
        "missing_env_gates": missing_env,
        "missing_args": missing_args,
        "timer_execution_triggered": False,
        "run_due_execution_triggered": False,
        "automation_execution_triggered": False,
        "outbound_send_executed": False,
        "live_external_call_executed": False,
        "production_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "delete_ready": False,
        "kill_switch_ready": kill_switch_ready,
        "audit_evidence": {
            "operator": args.operator or None,
            "operator_provided": bool(args.operator),
            "idempotency_key_provided": bool(args.idempotency_key),
            "mode": mode_name,
            "dry_run_requested": bool(args.dry_run),
            "shadow_run_requested": bool(args.shadow_run),
            "rollback_cleanup_evidence": "runner_disabled_by_default_no_cleanup_required",
        },
    }


def main(argv: list[str] | None = None) -> int:
    print(json.dumps(build_evidence(argv), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

