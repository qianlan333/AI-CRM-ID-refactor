from __future__ import annotations

from datetime import datetime, timezone

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput
from aicrm_next.automation_runtime_v2.task_planner import run_due_scheduled_tasks

from tests.automation_runtime_v2_test_helpers import count, seed_program, seed_task


def test_scheduled_daily_and_stage_day_offset_are_idempotent(runtime_v2_pg_app):
    program_id = seed_program("runtime_v2_scheduled")
    seed_task(program_id, trigger_type="scheduled_daily", target_stage="operating", content_text="每日")
    seed_task(program_id, trigger_type="scheduled", target_stage="operating", content_text="第N天", agent_config={"schedule_type": "stage_day_offset"})
    process_event_payload(AutomationEventInput(event_type="channel_entered", source_type="test", source_id="sched-channel", program_id=program_id, external_userid="wm_sched"))

    result = run_due_scheduled_tasks(program_id=program_id, now=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc))
    assert result["counts"]["planned"] == 2
    assert result["counts"]["enqueued"] == 2
    assert count("automation_task_plan_v2") == 2

    again = run_due_scheduled_tasks(program_id=program_id, now=datetime(2026, 6, 10, 10, 0, tzinfo=timezone.utc))
    assert again["counts"]["planned"] == 0
    assert count("broadcast_jobs") == 2
