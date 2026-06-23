#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json

from aicrm_next.ai_audience_ops.scheduler import emit_due_ticks, run_due_refresh_consumers


def main() -> int:
    parser = argparse.ArgumentParser(description="Emit AI audience refresh ticks and optionally run due internal consumers.")
    parser.add_argument("--run-consumers", action="store_true", help="Run existing internal_event consumers after emitting ticks.")
    parser.add_argument("--execute", action="store_true", help="Execute consumers instead of dry-run preview.")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--incremental-only", action="store_true")
    parser.add_argument("--daily-only", action="store_true")
    args = parser.parse_args()

    include_incremental = not args.daily_only
    include_daily = not args.incremental_only
    payload = {"ticks": emit_due_ticks(include_daily=include_daily, include_incremental=include_incremental)}
    if args.run_consumers:
        payload["consumers"] = run_due_refresh_consumers(dry_run=not args.execute, batch_size=args.batch_size)
    print(json.dumps(payload, ensure_ascii=False, indent=2, default=str))
    return 0 if payload["ticks"].get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
