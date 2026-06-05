from __future__ import annotations

from typing import Any

from .domain import AudienceTransitionEvent


class OperationTaskRealtimeTriggerGateway:
    """Boundary to the existing operation-task runtime and broadcast queue gateway."""

    def trigger(self, event: AudienceTransitionEvent) -> dict[str, Any]:
        from wecom_ability_service.domains.automation_conversion.operation_task_service import (
            run_audience_entered_operation_tasks,
        )

        return run_audience_entered_operation_tasks(
            member_id=int(event.member_id),
            audience_code=event.audience_code,
            audience_entry_id=int(event.audience_entry_id),
            operator_id=event.operator_id or event.entry_source or "audience_entered",
        )


def admit_channel_contact_to_program_with_runtime(
    *,
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    follow_user_userid: str = "",
    trigger_payload: dict[str, Any] | None = None,
    trigger_type: str = "qrcode_enter",
) -> dict[str, Any]:
    from aicrm_next.integration_gateway.legacy_automation_facade import _with_legacy_app_context
    from wecom_ability_service.domains.automation_conversion.admission_service import (
        admit_channel_contact_to_program,
    )

    return _with_legacy_app_context(
        lambda: admit_channel_contact_to_program(
            int(program_id),
            int(channel_id),
            int(binding_id),
            str(external_contact_id or "").strip(),
            follow_user_userid=str(follow_user_userid or "").strip(),
            trigger_payload=dict(trigger_payload or {}),
            trigger_type=str(trigger_type or "qrcode_enter").strip() or "qrcode_enter",
        )
    )
