from __future__ import annotations

from flask import Flask, has_app_context

from aicrm_next.automation_engine.automation_program_admission import (
    AutomationAdmissionCommand,
    AutomationProgramAdmissionService,
    OperationTaskRealtimeTriggerService,
    run_audience_entered_operation_tasks,
)
from aicrm_next.automation_engine.audience_transition.domain import AudienceTransitionEvent


def _install_legacy_app(monkeypatch):
    app = Flask(__name__)
    monkeypatch.setattr("aicrm_next.integration_gateway.legacy_automation_facade._legacy_app", lambda: app)
    return app


def test_channel_admission_enters_legacy_app_context(monkeypatch):
    _install_legacy_app(monkeypatch)
    calls: list[dict[str, object]] = []

    class AdmissionRuntime:
        @staticmethod
        def admit_channel_contact_to_program(
            program_id,
            channel_id,
            binding_id,
            external_contact_id,
            *,
            follow_user_userid="",
            trigger_payload=None,
            trigger_time=None,
            trigger_type="qrcode_enter",
        ):
            calls.append(
                {
                    "has_app_context": has_app_context(),
                    "program_id": program_id,
                    "channel_id": channel_id,
                    "binding_id": binding_id,
                    "external_contact_id": external_contact_id,
                    "follow_user_userid": follow_user_userid,
                    "trigger_payload": trigger_payload,
                    "trigger_time": trigger_time,
                    "trigger_type": trigger_type,
                }
            )
            return {"admission_status": "admitted", "admission_attempt": {"id": 123}}

    monkeypatch.setattr(
        "aicrm_next.automation_engine.automation_program_admission._automation_conversion_domain_module",
        lambda name: AdmissionRuntime,
    )

    assert not has_app_context()
    result = AutomationProgramAdmissionService().admit(
        AutomationAdmissionCommand(
            program_id=1,
            channel_id=2,
            binding_id=3,
            external_contact_id=" ext-1 ",
            follow_user_userid="owner-1",
            trigger_payload={"state": "qr"},
            trigger_time="2026-06-06T15:07:39+08:00",
        )
    )

    assert result["admission_status"] == "admitted"
    assert result["audit"] == {"id": 123}
    assert result["source_status"] == "next_command"
    assert calls == [
        {
            "has_app_context": True,
            "program_id": 1,
            "channel_id": 2,
            "binding_id": 3,
            "external_contact_id": "ext-1",
            "follow_user_userid": "owner-1",
            "trigger_payload": {"state": "qr"},
            "trigger_time": "2026-06-06T15:07:39+08:00",
            "trigger_type": "qrcode_enter",
        }
    ]


def test_realtime_trigger_enters_legacy_app_context(monkeypatch):
    _install_legacy_app(monkeypatch)
    calls: list[dict[str, object]] = []

    class OperationTaskRuntime:
        @staticmethod
        def run_audience_entered_operation_tasks(
            *,
            member_id,
            audience_code,
            audience_entry_id=0,
            now=None,
            operator_id="operation_task_event",
        ):
            calls.append(
                {
                    "has_app_context": has_app_context(),
                    "member_id": member_id,
                    "audience_code": audience_code,
                    "audience_entry_id": audience_entry_id,
                    "now": now,
                    "operator_id": operator_id,
                }
            )
            return {"created_execution_count": 1, "created_job_count": 1}

    monkeypatch.setattr(
        "aicrm_next.automation_engine.automation_program_admission._automation_conversion_domain_module",
        lambda name: OperationTaskRuntime,
    )

    assert not has_app_context()
    result = OperationTaskRealtimeTriggerService().trigger(
        AudienceTransitionEvent(
            member_id=42,
            external_userid="ext-42",
            program_id=1,
            source_channel_id=2,
            audience_entry_id=77,
            audience_code="operating",
            entry_reason="audience_entry_rule_passed",
            entry_source="questionnaire_submission",
            operator_id="questionnaire_sync",
        )
    )

    assert result == {"created_execution_count": 1, "created_job_count": 1}
    assert calls == [
        {
            "has_app_context": True,
            "member_id": 42,
            "audience_code": "operating",
            "audience_entry_id": 77,
            "now": None,
            "operator_id": "questionnaire_sync",
        }
    ]


def test_realtime_facade_enters_legacy_app_context(monkeypatch):
    _install_legacy_app(monkeypatch)
    calls: list[dict[str, object]] = []

    class OperationTaskRuntime:
        @staticmethod
        def run_audience_entered_operation_tasks(**kwargs):
            calls.append({"has_app_context": has_app_context(), **kwargs})
            return {"created_job_count": 1}

    monkeypatch.setattr(
        "aicrm_next.automation_engine.automation_program_admission._automation_conversion_domain_module",
        lambda name: OperationTaskRuntime,
    )

    assert not has_app_context()
    result = run_audience_entered_operation_tasks(
        member_id=51,
        audience_code="operating",
        audience_entry_id=88,
        operator_id="manual_stage_change",
    )

    assert result == {"created_job_count": 1}
    assert calls == [
        {
            "has_app_context": True,
            "member_id": 51,
            "audience_code": "operating",
            "audience_entry_id": 88,
            "now": None,
            "operator_id": "manual_stage_change",
        }
    ]
