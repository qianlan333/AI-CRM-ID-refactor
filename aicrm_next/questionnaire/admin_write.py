from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from aicrm_next.platform_foundation.audit_ledger import InMemoryAuditLedger
from aicrm_next.platform_foundation.command_bus import Command, CommandBus, CommandContext, CommandResult
from aicrm_next.platform_foundation.side_effects import InMemorySideEffectPlanRepository, SideEffectPlan
from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import production_data_ready

from .domain import admin_detail_projection, summary_projection
from .dto import QuestionnaireUpsertRequest
from .repo import QuestionnaireRepository, build_questionnaire_repository


class QuestionnaireAdminWriteInputError(ValueError):
    pass


class QuestionnaireAdminWriteNotFoundError(LookupError):
    pass


class QuestionnaireAdminWriteProductionUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True)
class QuestionnaireAdminWriteCommand:
    command_name: str
    questionnaire_id: int | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    command_id: str = field(default_factory=lambda: uuid4().hex)
    idempotency_key: str = ""
    actor_id: str = "questionnaire_admin"
    actor_type: str = "user"
    dry_run: bool = False
    source_route: str = ""
    trace_id: str = field(default_factory=lambda: uuid4().hex)

    def to_payload(self) -> dict[str, Any]:
        return {
            "command_id": self.command_id,
            "idempotency_key": self.idempotency_key,
            "actor_id": self.actor_id,
            "actor_type": self.actor_type,
            "questionnaire_id": self.questionnaire_id,
            "payload": dict(self.payload),
            "dry_run": self.dry_run,
            "source_route": self.source_route,
            "trace_id": self.trace_id,
        }


_audit_ledger = InMemoryAuditLedger()
_side_effect_plans = InMemorySideEffectPlanRepository()
_command_bus = CommandBus()


def reset_questionnaire_admin_write_fixture_state() -> None:
    global _audit_ledger, _side_effect_plans, _command_bus
    _audit_ledger = InMemoryAuditLedger()
    _side_effect_plans = InMemorySideEffectPlanRepository()
    _command_bus = CommandBus(audit_hook=_audit_hook)
    _register_handlers()


def get_questionnaire_admin_write_audit_events() -> list[dict[str, Any]]:
    return [event.to_dict() for event in _audit_ledger.list_events()]


def get_questionnaire_admin_write_side_effect_plans() -> list[dict[str, Any]]:
    return [_plan_response(plan) for plan in _side_effect_plans.list_plans()]


def execute_questionnaire_admin_write(command: QuestionnaireAdminWriteCommand) -> dict[str, Any]:
    _validate_command(command)
    if production_data_ready():
        raise QuestionnaireAdminWriteProductionUnavailableError(
            "questionnaire admin write model is not production-ready for command execution"
        )

    platform_command = Command(
        command_name=command.command_name,
        payload=command.to_payload(),
        command_id=command.command_id,
        idempotency_key=command.idempotency_key,
        context=CommandContext(
            actor_id=command.actor_id,
            actor_type=command.actor_type,
            trace_id=command.trace_id,
            source_route=command.source_route,
            dry_run=command.dry_run,
        ),
    )
    result = _command_bus.execute(platform_command)
    if result.status == "failed":
        if "questionnaire not found" in result.error:
            raise QuestionnaireAdminWriteNotFoundError("questionnaire not found")
        if "is required" in result.error or "Field required" in result.error or "validation error" in result.error or "json object" in result.error:
            raise QuestionnaireAdminWriteInputError(result.error)
        raise QuestionnaireAdminWriteProductionUnavailableError(result.error)

    payload = dict(result.payload)
    payload.setdefault("questionnaire_id", command.questionnaire_id or 0)
    payload.setdefault("write_model_status", "dry_run" if result.status == "dry_run" else "updated")
    return _response_from_result(result, payload)


def _audit_hook(command: Command, result: CommandResult) -> None:
    _audit_ledger.record_event(
        event_type=f"{command.command_name}.{result.status}",
        actor_id=result.actor_id,
        actor_type=result.actor_type,
        target_type="questionnaire",
        target_id=str(result.payload.get("questionnaire_id") or command.payload.get("questionnaire_id") or ""),
        source_route=result.source_route,
        command_id=result.command_id,
        trace_id=result.trace_id,
        payload={
            "status": result.status,
            "write_model_status": result.payload.get("write_model_status") or "",
            "fallback_used": False,
            "real_external_call_executed": False,
        },
    )


def _register_handlers() -> None:
    _command_bus.register("questionnaire.admin.create", _handle_create)
    _command_bus.register("questionnaire.admin.update", _handle_update)
    _command_bus.register("questionnaire.admin.duplicate", _handle_duplicate)
    _command_bus.register("questionnaire.admin.publish", _handle_publish)
    _command_bus.register("questionnaire.admin.enable", _handle_enable)
    _command_bus.register("questionnaire.admin.disable", _handle_disable)
    _command_bus.register("questionnaire.admin.delete", _handle_delete)
    _command_bus.register("questionnaire.admin.export_preview", _handle_export_preview)
    _command_bus.register("questionnaire.admin.export_audit", _handle_export_preview)


def _validate_command(command: QuestionnaireAdminWriteCommand) -> None:
    if not command.command_id.strip():
        raise QuestionnaireAdminWriteInputError("command_id is required")
    if not command.source_route.strip():
        raise QuestionnaireAdminWriteInputError("source_route is required")
    if not command.actor_id.strip():
        raise QuestionnaireAdminWriteInputError("actor_id is required")
    if command.command_name != "questionnaire.admin.create" and not command.questionnaire_id:
        raise QuestionnaireAdminWriteInputError("questionnaire_id is required")


def _repo() -> QuestionnaireRepository:
    try:
        return build_questionnaire_repository()
    except Exception as exc:
        raise QuestionnaireAdminWriteProductionUnavailableError(str(exc)) from exc


def _upsert_payload(payload: dict[str, Any]) -> dict[str, Any]:
    try:
        return QuestionnaireUpsertRequest.model_validate(payload).model_dump()
    except Exception as exc:
        raise QuestionnaireAdminWriteInputError(str(exc)) from exc


def _handle_create(command: Command) -> dict[str, Any]:
    payload = _upsert_payload(dict(command.payload.get("payload") or {}))
    if not str(payload.get("title") or "").strip():
        raise ContractError("title is required")
    item = _repo().save_questionnaire(payload)
    response = admin_detail_projection(item)
    response.update(
        {
            "questionnaire_id": int(item["id"]),
            "write_model_status": "created",
        }
    )
    plan = _optional_external_push_plan(command, item)
    if plan:
        response["side_effect_plan"] = _plan_response(plan)
    return response


def _handle_update(command: Command) -> dict[str, Any]:
    questionnaire_id = int(command.payload["questionnaire_id"])
    payload = _upsert_payload(dict(command.payload.get("payload") or {}))
    if not str(payload.get("title") or "").strip():
        raise ContractError("title is required")
    item = _repo().save_questionnaire(payload, questionnaire_id)
    if not item:
        raise NotFoundError("questionnaire not found")
    response = admin_detail_projection(item)
    response.update({"questionnaire_id": questionnaire_id, "write_model_status": "updated"})
    plan = _optional_external_push_plan(command, item)
    if plan:
        response["side_effect_plan"] = _plan_response(plan)
    return response


def _handle_duplicate(command: Command) -> dict[str, Any]:
    questionnaire_id = int(command.payload["questionnaire_id"])
    source = _repo().get_questionnaire(questionnaire_id)
    if not source:
        raise NotFoundError("questionnaire not found")
    payload = dict(source)
    requested = dict(command.payload.get("payload") or {})
    payload["title"] = str(requested.get("title") or f"{source.get('title') or source.get('name')} Copy").strip()
    payload["slug"] = str(requested.get("slug") or f"{source.get('slug')}-copy-{command.command_id[:6]}").strip()
    payload["enabled"] = False
    item = _repo().save_questionnaire(payload)
    response = admin_detail_projection(item)
    response.update(
        {
            "questionnaire_id": int(item["id"]),
            "source_questionnaire_id": questionnaire_id,
            "write_model_status": "duplicated",
        }
    )
    return response


def _handle_publish(command: Command) -> dict[str, Any]:
    questionnaire_id = int(command.payload["questionnaire_id"])
    item = _repo().set_enabled(questionnaire_id, True)
    if not item:
        raise NotFoundError("questionnaire not found")
    plan = _create_side_effect_plan(
        command=command,
        effect_type="questionnaire.public_projection.publish",
        adapter_name="questionnaire_projection",
        target_id=str(questionnaire_id),
        payload_summary={"questionnaire_id": questionnaire_id, "publish": True},
        risk_level="medium",
    )
    return {
        "questionnaire_id": questionnaire_id,
        "questionnaire": summary_projection(item),
        "write_model_status": "published",
        "side_effect_plan": _plan_response(plan),
    }


def _handle_enable(command: Command) -> dict[str, Any]:
    return _set_enabled(command, enabled=True, status="enabled")


def _handle_disable(command: Command) -> dict[str, Any]:
    return _set_enabled(command, enabled=False, status="disabled")


def _set_enabled(command: Command, *, enabled: bool, status: str) -> dict[str, Any]:
    questionnaire_id = int(command.payload["questionnaire_id"])
    item = _repo().set_enabled(questionnaire_id, enabled)
    if not item:
        raise NotFoundError("questionnaire not found")
    return {
        "questionnaire_id": questionnaire_id,
        "questionnaire": summary_projection(item),
        "write_model_status": status,
    }


def _handle_delete(command: Command) -> dict[str, Any]:
    questionnaire_id = int(command.payload["questionnaire_id"])
    existing = _repo().get_questionnaire(questionnaire_id)
    if not existing:
        raise NotFoundError("questionnaire not found")
    item = _repo().set_enabled(questionnaire_id, False)
    return {
        "questionnaire_id": questionnaire_id,
        "questionnaire": summary_projection(item or existing),
        "deleted": True,
        "delete_mode": "soft_delete_disable",
        "write_model_status": "soft_deleted",
    }


def _handle_export_preview(command: Command) -> dict[str, Any]:
    questionnaire_id = int(command.payload["questionnaire_id"])
    requested = dict(command.payload.get("payload") or {})
    fields = [str(item) for item in requested.get("fields") or ["submission_id", "external_userid", "answers", "created_at"]]
    result = _repo().list_submissions(questionnaire_id, limit=3, offset=0)
    if result is None:
        raise NotFoundError("questionnaire not found")
    submissions, total = result
    masked_sample = [_mask_submission(row, fields) for row in submissions]
    plan = _create_side_effect_plan(
        command=command,
        effect_type="questionnaire.export.preview",
        adapter_name="storage",
        target_id=str(questionnaire_id),
        payload_summary={"questionnaire_id": questionnaire_id, "fields": fields, "estimated_count": total},
        risk_level="medium",
    )
    return {
        "questionnaire_id": questionnaire_id,
        "write_model_status": "export_preview_planned",
        "export_preview": {
            "fields": fields,
            "estimated_count": total,
            "masked_sample": masked_sample,
            "file_created": False,
        },
        "side_effect_plan": _plan_response(plan),
    }


def _mask_submission(row: dict[str, Any], fields: list[str]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for field in fields:
        value = row.get(field)
        if field in {"mobile", "external_userid", "openid", "unionid", "respondent_key"} and value:
            payload[field] = "masked"
        else:
            payload[field] = value
    return payload


def _optional_external_push_plan(command: Command, item: dict[str, Any]) -> SideEffectPlan | None:
    config = dict(item.get("external_push_config") or {})
    if not bool(config.get("enabled")):
        return None
    return _create_side_effect_plan(
        command=command,
        effect_type="questionnaire.external_push.configure",
        adapter_name="external_push",
        target_id=str(item["id"]),
        payload_summary={"questionnaire_id": int(item["id"]), "external_push_configured": True},
        risk_level="medium",
    )


def _create_side_effect_plan(
    *,
    command: Command,
    effect_type: str,
    adapter_name: str,
    target_id: str,
    payload_summary: dict[str, Any],
    risk_level: str,
) -> SideEffectPlan:
    return _side_effect_plans.create_plan(
        command_id=command.command_id,
        effect_type=effect_type,
        adapter_name=adapter_name,
        adapter_mode="real_blocked",
        target_type="questionnaire",
        target_id=target_id,
        payload={
            "payload_summary": payload_summary,
            "real_external_call_executed": False,
        },
        status="planned",
        risk_level=risk_level,
        requires_approval=True,
    )


def _plan_response(plan: SideEffectPlan) -> dict[str, Any]:
    payload = plan.to_dict()
    summary = dict(payload.pop("payload") or {})
    payload["payload_summary"] = summary.get("payload_summary") or {}
    payload["real_external_call_executed"] = False
    return payload


def _response_from_result(result: CommandResult, payload: dict[str, Any]) -> dict[str, Any]:
    response = {
        "ok": result.status in {"completed", "dry_run"},
        "command_id": result.command_id,
        "command_name": result.command_name,
        "questionnaire_id": int(payload.get("questionnaire_id") or 0),
        "idempotency_key": result.idempotency_key,
        "source_status": "next_command",
        "write_model_status": payload.get("write_model_status") or "updated",
        "route_owner": "ai_crm_next",
        "fallback_used": False,
        "real_external_call_executed": False,
        "audit_recorded": True,
        "command_result_status": result.status,
    }
    response.update(payload)
    return response


reset_questionnaire_admin_write_fixture_state()
