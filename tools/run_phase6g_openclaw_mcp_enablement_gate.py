#!/usr/bin/env python3
from __future__ import annotations

import json
import os


FAMILY_KEY = "openclaw_mcp_ai_assist"
FAMILY_NAME = "OpenClaw / MCP / AI assist"
ROUTE_FAMILY = "/mcp"
REQUIRED_ENV_GATES = [
    "AICRM_PHASE6G_OPENCLAW_MCP_ENABLEMENT_APPROVED",
    "AICRM_PHASE6G_OPENCLAW_MCP_CONFIG_REVIEWED",
    "AICRM_PHASE6G_OPENCLAW_MCP_ROLLBACK_OWNER_APPROVED",
    "AICRM_PHASE6G_OPENCLAW_MCP_CANARY_TARGET_APPROVED",
]


def build_evidence() -> dict[str, object]:
    missing = [name for name in REQUIRED_ENV_GATES if os.environ.get(name) != "1"]
    return {
        "ok": True,
        "family_key": FAMILY_KEY,
        "family_name": FAMILY_NAME,
        "route_family": ROUTE_FAMILY,
        "required_env_gates": REQUIRED_ENV_GATES,
        "missing_env_gates": missing,
        "result_status": "blocked_missing_required_gates" if missing else "not_executed_owner_reviewed_gate_ready",
        "live_external_call_executed": False,
        "production_owner_changed": False,
        "production_compat_changed": False,
        "fallback_removed": False,
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
