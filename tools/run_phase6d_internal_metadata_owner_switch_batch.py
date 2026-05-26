#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


ROUTE_FAMILIES = (
    "/api/admin/automation-conversion/task-groups*",
    "/api/admin/automation-conversion/workflow-nodes*",
    "/api/admin/automation-conversion/agent-outputs*",
)


def build_report() -> dict[str, object]:
    per_route = [
        {
            "route_family": route,
            "blocked_by_default": True,
            "owner_switch_executed": False,
            "production_compat_changed": False,
            "fallback_removed": False,
            "shadow_compare_executed": False,
            "rollback_executed": False,
            "timer_execution_triggered": False,
            "automation_execution_triggered": False,
            "outbound_send_triggered": False,
            "external_live_call_triggered": False,
            "destructive_migration_triggered": False,
            "delete_ready": False,
        }
        for route in ROUTE_FAMILIES
    ]
    return {
        "overall": "BLOCKED",
        "ok": True,
        "bundle_type": "phase_6d_internal_metadata_owner_switch_batch_bundle",
        "selected_route_families": list(ROUTE_FAMILIES),
        "per_route": per_route,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-json")
    args = parser.parse_args(argv)
    report = build_report()
    if args.output_json:
        Path(args.output_json).write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
