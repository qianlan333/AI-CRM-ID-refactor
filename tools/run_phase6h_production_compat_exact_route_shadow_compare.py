#!/usr/bin/env python3
from __future__ import annotations

import json


PROPOSED_ROUTES = [
    {"source": "internal_accepted", "method": "GET", "exact_route": "/api/admin/automation-conversion/task-groups"},
    {"source": "internal_accepted", "method": "GET", "exact_route": "/api/admin/automation-conversion/workflow-nodes"},
    {"source": "external_low_risk_tooling", "method": "GET", "exact_route": "/api/admin/image-library"},
    {"source": "external_low_risk_tooling", "method": "GET", "exact_route": "/api/admin/image-library/facets"},
    {"source": "external_low_risk_tooling", "method": "GET", "exact_route": "/api/admin/wecom/tags"},
    {"source": "external_low_risk_tooling", "method": "GET", "exact_route": "/api/admin/wecom/tags/live/gate"},
    {"source": "external_low_risk_tooling", "method": "GET", "exact_route": "/mcp"},
]


def build_evidence() -> dict[str, object]:
    return {
        "ok": True,
        "result_status": "proposed_narrowing_only",
        "proposed_routes": PROPOSED_ROUTES,
        "production_compat_changed": False,
        "manifest_written": False,
        "fallback_removed": False,
        "wildcard_narrowing": False,
        "owner_switch_executed": False,
        "live_external_call_executed": False,
        "outbound_send_executed": False,
        "timer_execution_triggered": False,
        "automation_execution_triggered": False,
        "delete_ready": False,
    }


def main() -> int:
    print(json.dumps(build_evidence(), ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
