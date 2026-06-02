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
