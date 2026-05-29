"""Automation ops scheduler — materialize due business tasks into broadcast_jobs.

This runner does not send WeCom messages. It only lets business domains enqueue
due work into ``broadcast_jobs`` so ``run_broadcast_queue_worker.py`` remains the
single outbound execution path.
"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any

from script_runtime import ensure_repo_root_on_path, print_json

ensure_repo_root_on_path()


logger = logging.getLogger("automation_ops_scheduler")
DEFAULT_OPERATOR = "automation_ops_scheduler"


def _operation_task_summary(*, now: datetime, operator: str) -> dict[str, Any]:
    from wecom_ability_service.domains.automation_conversion.operation_task_service import (
        run_due_operation_tasks,
    )

    return run_due_operation_tasks(now=now, operator_id=operator)


def _group_ops_summary(*, now: datetime, operator: str) -> dict[str, Any]:
    from aicrm_next.automation_engine.group_ops.scheduler import run_group_ops_due_scheduler

    return run_group_ops_due_scheduler(now=now, operator=operator)


def run(*, now: datetime | None = None, operator: str | None = None) -> dict[str, Any]:
    scanned_at = now or datetime.now(timezone.utc)
    if scanned_at.tzinfo is None:
        scanned_at = scanned_at.replace(tzinfo=timezone.utc)
    actor = (operator or os.getenv("AUTOMATION_OPS_SCHEDULER_OPERATOR", DEFAULT_OPERATOR)).strip() or DEFAULT_OPERATOR
    errors: list[dict[str, Any]] = []
    operation_result: dict[str, Any] = {}
    group_result: dict[str, Any] = {}

    try:
        operation_result = _operation_task_summary(now=scanned_at, operator=actor)
    except Exception as exc:
        logger.exception("operation_task scheduler failed")
        errors.append({"scope": "operation_task", "error": str(exc)})

    try:
        group_result = _group_ops_summary(now=scanned_at, operator=actor)
        errors.extend(list(group_result.get("errors") or []))
    except Exception as exc:
        logger.exception("group_ops scheduler failed")
        errors.append({"scope": "group_ops", "error": str(exc)})

    return {
        "scanned_at": scanned_at.isoformat(),
        "group_ops_scanned_plans": int(group_result.get("group_ops_scanned_plans") or 0),
        "group_ops_due_nodes": int(group_result.get("group_ops_due_nodes") or 0),
        "group_ops_enqueued_jobs": int(group_result.get("group_ops_enqueued_jobs") or 0),
        "group_ops_skipped_future": int(group_result.get("group_ops_skipped_future") or 0),
        "group_ops_skipped_duplicate": int(group_result.get("group_ops_skipped_duplicate") or 0),
        "operation_task_enqueued_jobs": int(operation_result.get("enqueued_count") or 0),
        "errors": errors,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from wecom_ability_service import create_app

    app = create_app()
    with app.app_context():
        summary = run()
    print_json(summary)
    return 0 if not summary.get("errors") else 1


if __name__ == "__main__":
    sys.exit(main())
