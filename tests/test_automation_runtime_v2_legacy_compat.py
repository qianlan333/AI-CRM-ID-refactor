from __future__ import annotations

from aicrm_next.automation_runtime_v2 import process_event_payload
from aicrm_next.automation_runtime_v2.domain import AutomationEventInput
from aicrm_next.automation_runtime_v2.task_adapter import get_task

from tests.automation_runtime_v2_test_helpers import db, seed_program, seed_task


def test_legacy_trigger_content_mapping_and_projection(next_pg_schema):
    program_id = seed_program("runtime_v2_compat")
    task_id = seed_task(program_id, trigger_type="audience_entered", content_mode="unified", content_text="兼容")
    task = get_task(task_id)
    assert task["runtime_v2"]["trigger_type"] == "on_enter_stage"
    assert task["content_type"] == "fixed_message"

    result = process_event_payload(AutomationEventInput(event_type="questionnaire_submitted", source_type="questionnaire", source_id="compat-sub", program_id=program_id, external_userid="wm_compat", payload_json={"answers": {"a": "b"}}))
    assert result["membership"]["current_stage"] == "operating"

    legacy = db().execute("SELECT current_pool, questionnaire_status, current_audience_code FROM automation_member WHERE external_contact_id = ? LIMIT 1", ("wm_compat",)).fetchone()
    assert legacy["current_pool"] == "operating"
    assert legacy["current_audience_code"] == "operating"
    assert legacy["questionnaire_status"] == "submitted"
