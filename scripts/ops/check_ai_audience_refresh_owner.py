#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

try:
    from scripts.script_runtime import print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from script_runtime import print_json


ROOT = Path(__file__).resolve().parents[2]
SERVICE = ROOT / "deploy" / "openclaw-ai-audience-scheduler.service"
TIMER = ROOT / "deploy" / "openclaw-ai-audience-scheduler.timer"
EVENTS = ROOT / "aicrm_next" / "ai_audience_ops" / "events.py"
INTENTS = ROOT / "aicrm_next" / "ai_audience_ops" / "refresh_intents.py"


def _code_checks() -> dict[str, bool]:
    service = SERVICE.read_text(encoding="utf-8")
    timer = TIMER.read_text(encoding="utf-8")
    events = EVENTS.read_text(encoding="utf-8")
    intents = INTENTS.read_text(encoding="utf-8")
    return {
        "daily_clock_only": "--daily-only" in service and "--run-consumers" not in service and "--execute" not in service,
        "three_minute_timer_retired": "*:0/3:00" not in timer and "02:00:00" in timer,
        "owner_precheck_installed": "check_ai_audience_refresh_owner.py --code-only" in service,
        "single_package_consumer_registered": "REFRESH_REQUESTED_EVENT" in events and "refresh_intent_consumer" in events,
        "legacy_ticks_are_intent_only": "request_due_refreshes(" in events and "run_due(" not in events,
        "coalescing_intent_present": "ai_audience_refresh_intent" in intents and "claim_latest" in intents,
        "no_inline_provider_dispatch": "dispatch_one(" not in intents and ".dispatch(" not in intents,
    }


def _runtime_checks(database_url: str) -> dict[str, Any]:
    import psycopg

    normalized = database_url.replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(normalized) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT active_generation, claim_enabled, rollout_mode
                FROM queue_runtime_control
                WHERE singleton = TRUE
                """
            )
            control = cursor.fetchone()
            cursor.execute(
                """
                SELECT COUNT(*)
                FROM internal_event_consumer_run
                WHERE consumer_name IN (
                    'ai_audience_incremental_refresh_consumer',
                    'ai_audience_daily_refresh_consumer'
                )
                  AND status = 'running'
                """
            )
            legacy_running = int(cursor.fetchone()[0])
    active_generation = int(control[0]) if control else 0
    claim_enabled = bool(control[1]) if control else False
    rollout_mode = str(control[2]) if control else "missing"
    return {
        "active_generation": active_generation,
        "claim_enabled": claim_enabled,
        "rollout_mode": rollout_mode,
        "legacy_refresh_consumer_running_count": legacy_running,
        "runtime_owner_ready": active_generation > 0 and claim_enabled and rollout_mode in {"canary", "execute"} and legacy_running == 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fail-closed AI Audience refresh owner checker.")
    parser.add_argument("--code-only", action="store_true", help="Validate the release contract without reading live DB state.")
    parser.add_argument("--database-url", default="")
    args = parser.parse_args()

    checks = _code_checks()
    payload: dict[str, Any] = {
        "ok": all(checks.values()),
        "code_checks": checks,
        "activation_ready": False,
        "real_external_call_executed": False,
    }
    if not args.code_only:
        database_url = str(args.database_url or os.getenv("DATABASE_URL") or "").strip()
        if not database_url:
            payload["ok"] = False
            payload["error"] = "database_url_required_for_runtime_owner_check"
        else:
            runtime = _runtime_checks(database_url)
            payload["runtime"] = runtime
            payload["activation_ready"] = bool(payload["ok"] and runtime["runtime_owner_ready"])
            payload["ok"] = bool(payload["activation_ready"])
    print_json(payload, indent=2, sort_keys=True)
    return 0 if payload["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
