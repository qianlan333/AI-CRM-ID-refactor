#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys

try:
    from scripts.script_runtime import ensure_repo_root_on_path, print_json
except ModuleNotFoundError:  # pragma: no cover - direct script execution
    from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()

from aicrm_next.ai_audience_ops import register_ai_audience_event_consumers
from aicrm_next.ai_audience_ops.scheduler import (
    DEFAULT_DAILY_REFRESH_TIME,
    DEFAULT_DAILY_TICK_WINDOW_MINUTES,
    emit_due_ticks,
)

register_ai_audience_event_consumers()


def main() -> int:
    parser = argparse.ArgumentParser(description="Write durable AI audience clock intents; never run refresh work inline.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--incremental-only", action="store_true", help="Write compatibility incremental intents without executing them.")
    mode.add_argument("--daily-only", action="store_true", help="Write the daily intent; this is the production timer mode.")
    parser.add_argument("--daily-at", default=DEFAULT_DAILY_REFRESH_TIME)
    parser.add_argument("--daily-window-minutes", type=int, default=DEFAULT_DAILY_TICK_WINDOW_MINUTES)
    args = parser.parse_args()

    include_incremental = bool(args.incremental_only)
    include_daily = not args.incremental_only
    payload = {
        "ticks": emit_due_ticks(
            include_daily=include_daily,
            include_incremental=include_incremental,
            daily_refresh_time=args.daily_at,
            daily_window_minutes=args.daily_window_minutes,
            force_daily=bool(args.daily_only),
        )
    }
    print_json(payload, indent=2)
    return 0 if payload["ticks"].get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
