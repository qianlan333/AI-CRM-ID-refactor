from __future__ import annotations

from wecom_ability_service.db import get_db
from wecom_ability_service.domains.automation_conversion.admission_service import admit_channel_contact_to_program
from wecom_ability_service.domains.automation_conversion.channel_binding_service import bind_channels_to_program

from aicrm_next.automation_engine.programs import create_automation_program_operation_task
from automation_channel_admission_helpers import (
    create_channel,
    create_program,
    disabled_entry_rule,
    save_audience_entry_rule,
    table_count,
)


T1 = "2026-05-23 10:00:00"


def _bind(program_id: int, channel_id: int, payload: dict | None = None) -> int:
    return int(bind_channels_to_program(program_id, [channel_id], payload or {}, "pytest")["bindings"][0]["id"])


def _create_audience_entered_task(program_id: int, *, name: str = "Next realtime task", status: str = "active") -> dict:
    return create_automation_program_operation_task(
        program_id,
        {
            "task_name": name,
            "status": status,
            "trigger_type": "audience_entered",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": f"{name} content"},
        },
        operator_id="pytest",
    )["task"]


def _create_scheduled_daily_task(program_id: int) -> dict:
    return create_automation_program_operation_task(
        program_id,
        {
            "task_name": "Next scheduled daily task",
            "status": "active",
            "trigger_type": "scheduled_daily",
            "send_time": "10:00",
            "target_stage_code": "operating",
            "target_audience_code": "operating",
            "audience_day_offset": 1,
            "behavior_filter": "none",
            "content_mode": "unified",
            "unified_content_json": {"content_text": "scheduled daily content"},
        },
        operator_id="pytest",
    )["task"]


def _setup_admission_case(code: str) -> tuple[int, dict, int]:
    program_id = create_program(code)
    channel = create_channel(f"{code}_channel", program_id=program_id)
    binding_id = _bind(program_id, int(channel["id"]))
    save_audience_entry_rule(program_id, disabled_entry_rule())
    return program_id, channel, binding_id


def _job_count(task_id: int, audience_entry_id: int) -> int:
    return table_count(
        "broadcast_jobs",
        "source_type = 'operation_task' AND source_table = 'automation_operation_task_execution' AND source_id = ?",
        (f"{int(task_id)}:audience_entered:{int(audience_entry_id)}",),
    )


def _execution_count(task_id: int, audience_entry_id: int) -> int:
    return table_count(
        "automation_operation_task_execution",
        "task_id = ? AND execution_id = ?",
        (int(task_id), f"actask-event-{int(task_id)}-{int(audience_entry_id)}"),
    )


def test_next_program_admission_triggers_audience_entered_operation_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_trigger")
        task = _create_audience_entered_task(program_id, name="Next admission realtime")

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_001",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_entry_id"] > 0
        assert result["audience_code"] == "operating"
        assert result["entry_reason"] == "audience_entry_rule_passed"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 1
        assert result["realtime_operation_tasks_enqueued_count"] == 1
        assert result["realtime_operation_tasks_results"][0]["execution_id"] == f"actask-event-{task['id']}-{result['audience_entry_id']}"
        assert _execution_count(task["id"], result["audience_entry_id"]) == 1
        assert _job_count(task["id"], result["audience_entry_id"]) == 1

        item = get_db().execute(
            """
            SELECT external_contact_id, status
            FROM automation_operation_task_execution_item
            WHERE execution_id = ?
            LIMIT 1
            """,
            (f"actask-event-{task['id']}-{result['audience_entry_id']}",),
        ).fetchone()
        assert item
        assert item["external_contact_id"] == "wm_next_rt_admission_001"
        assert item["status"] == "queued"


def test_next_program_admission_recheck_is_idempotent_for_audience_entered_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_idempotent")
        task = _create_audience_entered_task(program_id, name="Next admission idempotent")

        first = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_002",
            trigger_time=T1,
        )
        second = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_002",
            trigger_time=T1,
        )

        assert first["realtime_operation_tasks_enqueued_count"] == 1
        assert second["admission_status"] == "duplicate_active"
        assert second["audience_entry_id"] == first["audience_entry_id"]
        assert second["realtime_task_hook"]["ok"] is True
        assert second["realtime_operation_tasks_enqueued_count"] == 0
        assert _execution_count(task["id"], first["audience_entry_id"]) == 1
        assert _job_count(task["id"], first["audience_entry_id"]) == 1


def test_next_program_admission_does_not_trigger_unmatched_audience_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_unmatched")
        task = create_automation_program_operation_task(
            program_id,
            {
                "task_name": "Next unmatched realtime",
                "status": "active",
                "trigger_type": "audience_entered",
                "send_time": "10:00",
                "target_stage_code": "questionnaire_review",
                "target_audience_code": "pending_questionnaire",
                "audience_day_offset": 1,
                "behavior_filter": "none",
                "content_mode": "unified",
                "unified_content_json": {"content_text": "unmatched content"},
            },
            operator_id="pytest",
        )["task"]

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_003",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_code"] == "operating"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 0
        assert result["realtime_operation_tasks_enqueued_count"] == 0
        assert _execution_count(task["id"], result["audience_entry_id"]) == 0
        assert _job_count(task["id"], result["audience_entry_id"]) == 0


def test_next_program_admission_hook_failure_is_reported_without_breaking_admission(app, monkeypatch):
    from aicrm_next.automation_engine.audience_transition.integration_gateway import OperationTaskRealtimeTriggerGateway

    def broken_trigger(self, event):
        raise RuntimeError("realtime hook boom")

    monkeypatch.setattr(OperationTaskRealtimeTriggerGateway, "trigger", broken_trigger)

    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_hook_failure")
        _create_audience_entered_task(program_id, name="Next hook failure")

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_004",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["audience_entry_id"] > 0
        assert result["realtime_task_hook"]["ok"] is False
        assert "realtime hook boom" in result["realtime_operation_tasks_error"]
        assert table_count("automation_operation_task_execution") == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0


def test_next_program_admission_realtime_hook_does_not_trigger_scheduled_daily_task(app):
    with app.app_context():
        program_id, channel, binding_id = _setup_admission_case("next_rt_admission_scheduled_daily_guard")
        task = _create_scheduled_daily_task(program_id)

        result = admit_channel_contact_to_program(
            program_id,
            int(channel["id"]),
            binding_id,
            "wm_next_rt_admission_005",
            trigger_time=T1,
        )

        assert result["admission_status"] == "accepted"
        assert result["realtime_task_hook"]["ok"] is True
        assert result["realtime_operation_tasks_ran"] == 0
        assert result["realtime_operation_tasks_enqueued_count"] == 0
        assert table_count("automation_operation_task_execution", "task_id = ?", (int(task["id"]),)) == 0
        assert table_count("broadcast_jobs", "source_type = 'operation_task'") == 0
