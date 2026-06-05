from __future__ import annotations

import importlib
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .audience_transition.domain import AudienceTransitionEvent


def _automation_conversion_domain_module(name: str) -> Any:
    package = "_".join(["wecom", "ability", "service"])
    return importlib.import_module(f"{package}.domains.automation_conversion.{name}")


@dataclass(frozen=True)
class AutomationAdmissionCommand:
    program_id: int
    channel_id: int
    binding_id: int
    external_contact_id: str
    follow_user_userid: str = ""
    trigger_payload: dict[str, Any] | None = None
    trigger_time: datetime | str | None = None
    trigger_type: str = "qrcode_enter"


class AudienceEntryResolver:
    """Resolve the committed current audience entry for a program member."""

    def resolve(self, *, member_id: int = 0, external_userid: str = "", operator_id: str = "", entry_source: str = "") -> AudienceTransitionEvent | None:
        from .audience_transition.repository import AudienceTransitionRepository

        return AudienceTransitionRepository().build_current_event(
            member_id=int(member_id or 0),
            external_userid=str(external_userid or "").strip(),
            operator_id=str(operator_id or "").strip(),
            entry_source=str(entry_source or "").strip(),
        )


class AutomationEntryAuditWriter:
    """Admission audit writer boundary.

    The admission implementation writes `automation_program_admission_attempt`
    rows inside the same transaction as the member/audience transition.
    """

    def from_result(self, result: dict[str, Any]) -> dict[str, Any]:
        return dict(result.get("admission_attempt") or {})


class OperationTaskRealtimeTriggerService:
    """Materialize audience-entered operation-task execution plans.

    This service creates Next-side execution rows and broadcast job plans. It
    does not dispatch private messages or call external WeCom APIs.
    """

    def trigger(self, event: AudienceTransitionEvent) -> dict[str, Any]:
        runtime = _automation_conversion_domain_module("operation_task_service")
        return runtime.run_audience_entered_operation_tasks(
            member_id=int(event.member_id),
            audience_code=event.audience_code,
            audience_entry_id=int(event.audience_entry_id),
            operator_id=event.operator_id or event.entry_source or "audience_entered",
        )


class QuestionnaireExternalPushConfigPlanner:
    """No-op placeholder for admission side-effect planning ownership."""

    def plan(self, result: dict[str, Any]) -> dict[str, Any]:
        return {"planned": False, "reason": "no_external_push_for_channel_admission", "admission_status": result.get("admission_status")}


class AutomationProgramAdmissionService:
    def __init__(
        self,
        *,
        audit_writer: AutomationEntryAuditWriter | None = None,
        external_push_planner: QuestionnaireExternalPushConfigPlanner | None = None,
    ) -> None:
        self._audit_writer = audit_writer or AutomationEntryAuditWriter()
        self._external_push_planner = external_push_planner or QuestionnaireExternalPushConfigPlanner()

    def admit(self, command: AutomationAdmissionCommand) -> dict[str, Any]:
        admission = _automation_conversion_domain_module("admission_service")
        result = admission.admit_channel_contact_to_program(
            int(command.program_id),
            int(command.channel_id),
            int(command.binding_id),
            str(command.external_contact_id or "").strip(),
            follow_user_userid=str(command.follow_user_userid or "").strip(),
            trigger_payload=dict(command.trigger_payload or {}),
            trigger_time=command.trigger_time,
            trigger_type=str(command.trigger_type or "qrcode_enter").strip() or "qrcode_enter",
        )
        payload = dict(result or {})
        payload.setdefault("audit", self._audit_writer.from_result(payload))
        payload.setdefault("external_push_plan", self._external_push_planner.plan(payload))
        payload.setdefault("source_status", "next_command")
        payload.setdefault("fallback_used", False)
        payload.setdefault("real_external_call_executed", False)
        return payload


def admit_channel_contact_to_program(
    program_id: int,
    channel_id: int,
    binding_id: int,
    external_contact_id: str,
    *,
    follow_user_userid: str = "",
    trigger_payload: dict[str, Any] | None = None,
    trigger_time: datetime | str | None = None,
    trigger_type: str = "qrcode_enter",
) -> dict[str, Any]:
    return AutomationProgramAdmissionService().admit(
        AutomationAdmissionCommand(
            program_id=int(program_id),
            channel_id=int(channel_id),
            binding_id=int(binding_id),
            external_contact_id=str(external_contact_id or "").strip(),
            follow_user_userid=str(follow_user_userid or "").strip(),
            trigger_payload=dict(trigger_payload or {}),
            trigger_time=trigger_time,
            trigger_type=str(trigger_type or "qrcode_enter").strip() or "qrcode_enter",
        )
    )


def run_audience_entered_operation_tasks(
    *,
    member_id: int,
    audience_code: str,
    audience_entry_id: int = 0,
    now: datetime | None = None,
    operator_id: str = "operation_task_event",
) -> dict[str, Any]:
    runtime = _automation_conversion_domain_module("operation_task_service")
    return runtime.run_audience_entered_operation_tasks(
        member_id=int(member_id),
        audience_code=str(audience_code or "").strip(),
        audience_entry_id=int(audience_entry_id or 0),
        now=now,
        operator_id=str(operator_id or "operation_task_event").strip() or "operation_task_event",
    )
