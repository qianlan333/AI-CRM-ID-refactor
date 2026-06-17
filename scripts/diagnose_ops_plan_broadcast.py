#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from aicrm_next.platform_foundation.internal_events.ops_plan_broadcast_planner import (  # noqa: E402
    InternalEventOpsPlanBroadcastPlannerService,
)


def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _safe(item) for key, item in value.items() if "external_userid" not in str(key).lower()}
    if isinstance(value, list):
        return [_safe(item) for item in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose ops plan approval to broadcast_jobs readiness.")
    parser.add_argument("plan_id", help="cloud/legacy ops plan id")
    args = parser.parse_args()

    result = InternalEventOpsPlanBroadcastPlannerService().diagnose_plan(args.plan_id)
    print(json.dumps(_safe(result), ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
