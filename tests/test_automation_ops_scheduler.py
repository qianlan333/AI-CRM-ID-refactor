from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path


_SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_automation_ops_scheduler as scheduler  # type: ignore[import-not-found]


def test_automation_ops_scheduler_calls_operation_task_and_group_ops(monkeypatch):
    calls: list[str] = []

    def fake_operation_task_summary(*, now, operator):
        calls.append(f"operation_task:{operator}:{now.isoformat()}")
        return {"ok": True, "enqueued_count": 2}

    def fake_group_ops_summary(*, now, operator):
        calls.append(f"group_ops:{operator}:{now.isoformat()}")
        return {
            "group_ops_scanned_plans": 3,
            "group_ops_due_nodes": 4,
            "group_ops_enqueued_jobs": 1,
            "group_ops_skipped_future": 5,
            "group_ops_skipped_duplicate": 6,
            "errors": [],
        }

    monkeypatch.setattr(scheduler, "_operation_task_summary", fake_operation_task_summary)
    monkeypatch.setattr(scheduler, "_group_ops_summary", fake_group_ops_summary)

    now = datetime(2026, 5, 29, 8, 0, tzinfo=timezone.utc)
    summary = scheduler.run(now=now, operator="pytest")

    assert calls == [
        "operation_task:pytest:2026-05-29T08:00:00+00:00",
        "group_ops:pytest:2026-05-29T08:00:00+00:00",
    ]
    assert summary == {
        "scanned_at": "2026-05-29T08:00:00+00:00",
        "group_ops_scanned_plans": 3,
        "group_ops_due_nodes": 4,
        "group_ops_enqueued_jobs": 1,
        "group_ops_skipped_future": 5,
        "group_ops_skipped_duplicate": 6,
        "operation_task_enqueued_jobs": 2,
        "errors": [],
    }
