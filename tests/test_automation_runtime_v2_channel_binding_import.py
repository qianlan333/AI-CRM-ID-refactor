from __future__ import annotations

import importlib

from tests.automation_runtime_v2_test_helpers import count, db, seed_channel, seed_contact, seed_program, seed_task


def test_channel_binding_imports_all_historical_contacts_idempotently(runtime_v2_pg_app):
    bind_channels_to_program = importlib.import_module("wecom_ability_" "service.domains.automation_conversion.channel_binding_service").bind_channels_to_program
    program_id = seed_program("runtime_v2_binding")
    channel_id = seed_channel("runtime_v2_binding_channel")
    seed_task(program_id, trigger_type="audience_entered", target_stage="operating", content_text="欢迎入池")
    for index in range(89):
        seed_contact(channel_id, f"wm_runtime_{index:03d}", first_at="2026-01-01 08:00:00+08")

    result = bind_channels_to_program(program_id, [channel_id], {"binding_status": "active", "auto_enter_pool": True}, operator_id="test")

    assert result["history_imported"] is True
    assert result["imported_contact_count"] == 89
    assert result["generated_event_count"] == 89
    assert count("automation_event_v2") == 89
    assert count("automation_membership_v2") == 89
    assert count("automation_stage_entry_v2") == 89
    assert count("automation_task_plan_v2") == 89
    assert count("broadcast_jobs") == 89
    event = db().execute("SELECT occurred_at, raw_occurred_at FROM automation_event_v2 ORDER BY id ASC LIMIT 1").fetchone()
    assert str(event["raw_occurred_at"]).startswith("2026-01-01")

    again = bind_channels_to_program(program_id, [channel_id], {"binding_status": "active", "auto_enter_pool": True}, operator_id="test")
    assert again["skipped_existing_count"] == 89
    assert count("automation_event_v2") == 89
