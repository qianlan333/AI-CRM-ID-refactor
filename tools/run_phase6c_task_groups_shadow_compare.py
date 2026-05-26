#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


REQUIRED_ENV = (
    "AICRM_PHASE6C_TASK_GROUPS_OWNER_SWITCH_APPROVED",
    "AICRM_PHASE6C_TASK_GROUPS_CONFIG_REVIEWED",
)


def build_report(args: argparse.Namespace) -> dict[str, object]:
    missing_env = [name for name in REQUIRED_ENV if os.environ.get(name) != "1"]
    missing_args = [
        flag
        for flag, present in (
            ("--confirm-fallback-retained", args.confirm_fallback_retained),
            ("--confirm-production-compat-unchanged", args.confirm_production_compat_unchanged),
        )
        if not present
    ]
    blocked = bool(missing_env or missing_args)
    return {
        "overall": "BLOCKED" if blocked else "READY_FOR_SHADOW_COMPARE_REVIEW",
        "ok": True,
        "route_family": "/api/admin/automation-conversion/task-groups*",
        "blocked_by_default": blocked,
        "missing_env_gates": missing_env,
        "missing_confirmations": missing_args,
        "shadow_compare_executed": False,
        "shadow_compare_passed": False,
        "owner_switch_executed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
        "timer_execution_triggered": False,
        "automation_execution_triggered": False,
        "outbound_send_triggered": False,
        "destructive_migration_triggered": False,
        "delete_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm-fallback-retained", action="store_true")
    parser.add_argument("--confirm-production-compat-unchanged", action="store_true")
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)
    report = build_report(args)
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
