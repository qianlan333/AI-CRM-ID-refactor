from __future__ import annotations

import logging
from typing import Any

from aicrm_next.platform_foundation.command_bus import Command, CommandContext

from .config import customer_tags_internal_events_enabled, event_type_allowed, internal_events_enabled, questionnaire_internal_events_enabled
from .consumer_registry import DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY, InternalEventConsumerRegistry
from .models import InternalEvent, InternalEventConsumerResult, InternalEventConsumerRun
from .questionnaire import register_questionnaire_event_consumers
from .service import InternalEventService

LOGGER = logging.getLogger(__name__)

QUESTIONNAIRE_SUBMITTED_EVENT_TYPE = "questionnaire.submitted"
CUSTOMER_TAGGED_EVENT_TYPE = "customer.tagged"
CUSTOMER_UNTAGGED_EVENT_TYPE = "customer.untagged"
AI_CAMPAIGN_CREATED_EVENT_TYPE = "ai_campaign.created"
AI_CAMPAIGN_APPROVED_EVENT_TYPE = "ai_campaign.approved"
AI_CAMPAIGN_STARTED_EVENT_TYPE = "ai_campaign.started"
BROADCAST_TASK_CREATED_EVENT_TYPE = "broadcast_task.created"
OPS_PLAN_APPROVED_EVENT_TYPE = "ops_plan.approved"
OWNER_MIGRATION_EXECUTED_EVENT_TYPE = "owner_migration.executed"


def _text(value: Any) -> str:
    return str(value or "").strip()


def _redact_external_userid(external_userid: str) -> str:
    value = _text(external_userid)
    if not value:
        return ""
    if len(value) <= 8:
        return "<redacted>"
    return f"{value[:4]}...{value[-4:]}"


def _mask_mobile(value: Any) -> str:
    text = _text(value)
    if len(text) < 7:
        return "<redacted>" if text else ""
    return f"{text[:3]}****{text[-4:]}"


def _questionnaire_subject_id(submission: dict[str, Any]) -> str:
    external_userid = _text(submission.get("external_userid"))
    if external_userid:
        return _redact_external_userid(external_userid)
    respondent_key = _text(submission.get("respondent_key"))
    if respondent_key:
        return _redact_external_userid(respondent_key)
    return _mask_mobile(submission.get("mobile"))


def _source_context_source(source_context: dict[str, Any], fallback: str) -> str:
    return _text(source_context.get("source")) or _text(fallback)


def _skipped(reason: str, event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="skipped",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={"skipped": True, "reason": reason},
        result_summary={"reason": reason},
    )


def _succeeded_noop(reason: str, event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return InternalEventConsumerResult(
        status="succeeded",
        request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
        response_summary={"succeeded": True, "reason": reason},
        result_summary={"reason": reason},
    )


def questionnaire_webhook_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("questionnaire_webhook_shadow_only", event, run)


def questionnaire_tag_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("questionnaire_tag_shadow_only", event, run)


def automation_questionnaire_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("automation_questionnaire_not_configured", event, run)


def customer_summary_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("customer_summary_not_configured", event, run)


def tag_external_effect_shadow_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    payload = dict(event.payload_json or {})
    external_effect_job = payload.get("external_effect_job")
    side_effect_plan = payload.get("side_effect_plan")
    if isinstance(external_effect_job, dict) and external_effect_job.get("id"):
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
            response_summary={
                "external_effect_job_reused": True,
                "external_effect_job_created": False,
                "external_effect_job_id": external_effect_job.get("id"),
                "effect_type": _text(external_effect_job.get("effect_type")),
                "execution_mode": _text(external_effect_job.get("execution_mode") or "shadow"),
                "status": _text(external_effect_job.get("status") or "planned"),
                "real_external_call_executed": False,
                "wecom_api_called": False,
            },
            result_summary={
                "external_effect_job_reused": True,
                "external_effect_job_id": external_effect_job.get("id"),
                "reason": "customer_tag_external_effect_already_planned",
            },
        )
    if isinstance(side_effect_plan, dict) and side_effect_plan.get("id"):
        return InternalEventConsumerResult(
            status="succeeded",
            request_summary={"event_id": event.event_id, "consumer_name": run.consumer_name},
            response_summary={
                "side_effect_plan_reused": True,
                "side_effect_plan_id": side_effect_plan.get("id"),
                "real_external_call_executed": False,
                "wecom_api_called": False,
            },
            result_summary={
                "side_effect_plan_reused": True,
                "side_effect_plan_id": side_effect_plan.get("id"),
                "reason": "customer_tag_side_effect_already_planned",
            },
        )
    return _skipped("customer_tag_external_effect_not_configured_or_already_shadow_only", event, run)


def tag_summary_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("customer_tag_summary_not_configured", event, run)


def ai_assist_notify_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("ai_assist_notify_not_configured", event, run)


def campaign_summary_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("campaign_summary_not_configured", event, run)


def broadcast_task_planner_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("broadcast_task_planner_shadow_only", event, run)


def broadcast_queue_projection_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _succeeded_noop("broadcast_queue_projection_shadow_only", event, run)


def push_center_link_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _succeeded_noop("push_center_link_shadow_only", event, run)


def automation_schedule_refresh_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _succeeded_noop("automation_schedule_refresh_shadow_only", event, run)


def audit_projection_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _succeeded_noop("audit_projection_shadow_only", event, run)


def customer_owner_projection_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _succeeded_noop("customer_owner_projection_shadow_only", event, run)


def customer_summary_mark_dirty_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _succeeded_noop("customer_summary_mark_dirty_shadow_only", event, run)


def webhook_owner_migration_consumer(event: InternalEvent, run: InternalEventConsumerRun) -> InternalEventConsumerResult:
    return _skipped("owner_migration_webhook_not_configured", event, run)


def register_shadow_event_consumers(registry: InternalEventConsumerRegistry | None = None) -> None:
    registry = registry or DEFAULT_INTERNAL_EVENT_CONSUMER_REGISTRY
    register_questionnaire_event_consumers(registry)

    for event_type in (CUSTOMER_TAGGED_EVENT_TYPE, CUSTOMER_UNTAGGED_EVENT_TYPE):
        registry.register(event_type, "tag_external_effect_shadow_consumer", tag_external_effect_shadow_consumer, consumer_type="external_effect_planner")
        registry.register(event_type, "tag_summary_consumer", tag_summary_consumer, consumer_type="projection")
        registry.register(event_type, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")

    for event_type in (AI_CAMPAIGN_CREATED_EVENT_TYPE, AI_CAMPAIGN_APPROVED_EVENT_TYPE, AI_CAMPAIGN_STARTED_EVENT_TYPE):
        registry.register(event_type, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")
        registry.register(event_type, "campaign_summary_consumer", campaign_summary_consumer, consumer_type="projection")
        registry.register(event_type, "broadcast_task_planner_consumer", broadcast_task_planner_consumer, consumer_type="orchestration")

    registry.register(BROADCAST_TASK_CREATED_EVENT_TYPE, "broadcast_queue_projection_consumer", broadcast_queue_projection_consumer, consumer_type="projection")
    registry.register(BROADCAST_TASK_CREATED_EVENT_TYPE, "push_center_link_consumer", push_center_link_consumer, consumer_type="projection")
    registry.register(BROADCAST_TASK_CREATED_EVENT_TYPE, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")

    registry.register(OPS_PLAN_APPROVED_EVENT_TYPE, "automation_schedule_refresh_consumer", automation_schedule_refresh_consumer, consumer_type="orchestration")
    registry.register(OPS_PLAN_APPROVED_EVENT_TYPE, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")
    registry.register(OPS_PLAN_APPROVED_EVENT_TYPE, "audit_projection_consumer", audit_projection_consumer, consumer_type="projection")

    registry.register(OWNER_MIGRATION_EXECUTED_EVENT_TYPE, "customer_owner_projection_consumer", customer_owner_projection_consumer, consumer_type="projection")
    registry.register(OWNER_MIGRATION_EXECUTED_EVENT_TYPE, "customer_summary_mark_dirty_consumer", customer_summary_mark_dirty_consumer, consumer_type="projection")
    registry.register(OWNER_MIGRATION_EXECUTED_EVENT_TYPE, "ai_assist_notify_consumer", ai_assist_notify_consumer, consumer_type="orchestration")
    registry.register(OWNER_MIGRATION_EXECUTED_EVENT_TYPE, "webhook_owner_migration_consumer", webhook_owner_migration_consumer, consumer_type="external_effect_planner")


def emit_questionnaire_submitted_shadow_event(
    *,
    command: Command,
    questionnaire: dict[str, Any],
    submission: dict[str, Any],
    score: int,
    final_tags: list[str],
) -> dict[str, Any]:
    if not questionnaire_internal_events_enabled():
        return {"status": "skipped", "reason": "questionnaire_internal_events_disabled"}
    if not event_type_allowed(QUESTIONNAIRE_SUBMITTED_EVENT_TYPE):
        return {"status": "skipped", "reason": "internal_events_disabled_or_event_type_not_allowed"}
    submission_id = _text(submission.get("submission_id"))
    if not submission_id:
        return {"status": "skipped", "reason": "submission_id_missing"}
    register_shadow_event_consumers()
    answer_snapshots = [
        dict(item)
        for item in (submission.get("answer_snapshots") or [])
        if isinstance(item, dict)
    ]
    answer_count = len(answer_snapshots) if answer_snapshots else len(dict(submission.get("answers") or {}))
    external_push_config = dict(questionnaire.get("external_push_config") or {})
    external_push_summary = {
        "enabled": bool(external_push_config.get("enabled") or questionnaire.get("external_push_enabled")),
        "target_url_present": bool(_text(external_push_config.get("webhook_url") or questionnaire.get("external_push_url"))),
        "type": _text(external_push_config.get("type") or questionnaire.get("external_push_type")),
    }
    result = InternalEventService().emit_event(
        event_type=QUESTIONNAIRE_SUBMITTED_EVENT_TYPE,
        event_version=1,
        aggregate_type="questionnaire_submission",
        aggregate_id=submission_id,
        subject_type="customer",
        subject_id=_questionnaire_subject_id(submission),
        idempotency_key=f"questionnaire.submitted:{submission_id}",
        source_module="questionnaire.h5_write",
        source_command_id=command.command_id,
        correlation_id=command.idempotency_key or command.command_id,
        context=CommandContext(
            actor_id=command.context.actor_id,
            actor_type=command.context.actor_type,
            trace_id=command.context.trace_id,
            request_id=command.command_id,
            source_route=command.context.source_route,
            dry_run=command.context.dry_run,
        ),
        payload={
            "questionnaire": {
                "id": questionnaire.get("id"),
                "slug": questionnaire.get("slug"),
                "title": questionnaire.get("title") or questionnaire.get("name"),
                "external_push_config": external_push_config,
                "external_push_enabled": bool(questionnaire.get("external_push_enabled")),
                "external_push_url": questionnaire.get("external_push_url") or "",
            },
            "submission": {
                "submission_id": submission_id,
                "questionnaire_id": int(questionnaire.get("id") or submission.get("questionnaire_id") or 0),
                "slug": questionnaire.get("slug") or submission.get("slug") or "",
                "respondent_key": submission.get("respondent_key") or "",
                "external_userid": submission.get("external_userid") or "",
                "openid_present": bool(_text(submission.get("openid"))),
                "unionid_present": bool(_text(submission.get("unionid"))),
                "mobile_present": bool(_text(submission.get("mobile"))),
                "person_id": submission.get("person_id"),
                "binding_status": submission.get("binding_status") or "",
                "submitted_at": submission.get("submitted_at") or submission.get("created_at") or "",
                "created_at": submission.get("created_at") or "",
                "score": int(score or 0),
                "answer_count": answer_count,
            },
            "answer_snapshots": answer_snapshots,
            "score": score,
            "final_tags": list(final_tags or []),
            "external_push": external_push_summary,
            "source": {
                "source_route": command.context.source_route,
                "trace_id": command.context.trace_id,
                "command_id": command.command_id,
            },
        },
        payload_summary={
            "questionnaire_id": int(questionnaire.get("id") or 0),
            "slug": _text(questionnaire.get("slug")),
            "submission_id": submission_id,
            "external_userid_present": bool(_text(submission.get("external_userid"))),
            "mobile_present": bool(_text(submission.get("mobile"))),
            "answer_count": answer_count,
            "score": int(score or 0),
            "final_tag_count": len(final_tags or []),
        },
    )
    return {"status": "emitted", "event_id": result["event"]["event_id"], "consumer_run_count": len(result.get("consumer_runs") or [])}


def emit_customer_tag_shadow_event(
    *,
    command: Command,
    effect_type: str,
    external_userid: str,
    tag_ids: list[str],
    source_context: dict[str, Any],
    side_effect_plan: dict[str, Any] | None = None,
    external_effect_job: dict[str, Any] | None = None,
) -> dict[str, Any]:
    event_type = CUSTOMER_UNTAGGED_EVENT_TYPE if _text(effect_type) == "wecom.tag.unmark" else CUSTOMER_TAGGED_EVENT_TYPE
    if not customer_tags_internal_events_enabled():
        return {"status": "skipped", "reason": "customer_tags_internal_events_disabled"}
    if not event_type_allowed(event_type):
        return {"status": "skipped", "reason": "internal_events_disabled_or_event_type_not_allowed"}
    if not _text(external_userid):
        return {"status": "skipped", "reason": "external_userid_missing"}
    register_shadow_event_consumers()
    stable_key = command.idempotency_key or command.command_id or f"{event_type}:{external_userid}:{','.join(tag_ids)}"
    source = _source_context_source(source_context, command.context.source_route)
    normalized_tags = list(tag_ids or [])
    external_effect_summary = dict(external_effect_job or {}) if isinstance(external_effect_job, dict) else {}
    side_effect_summary = dict(side_effect_plan or {}) if isinstance(side_effect_plan, dict) else {}
    result = InternalEventService().emit_event(
        event_type=event_type,
        event_version=1,
        aggregate_type="customer",
        aggregate_id=_text(external_userid),
        subject_type="customer",
        subject_id=_redact_external_userid(external_userid),
        idempotency_key=f"{event_type}:{stable_key}",
        source_module="customer_tags.live_mutation",
        source_command_id=command.command_id,
        correlation_id=command.idempotency_key or command.command_id,
        context=command.context,
        payload={
            "external_userid": external_userid,
            "tag_ids": normalized_tags,
            "tag_count": len(normalized_tags),
            "source_context": dict(source_context or {}),
            "effect_type": effect_type,
            "source": {
                "source_module": "customer_tags.live_mutation",
                "source_route": command.context.source_route,
                "command_id": command.command_id,
                "trace_id": command.context.trace_id,
            },
            "side_effect_plan": {
                "id": side_effect_summary.get("id"),
                "effect_type": side_effect_summary.get("effect_type"),
                "status": side_effect_summary.get("status"),
            } if side_effect_summary else {},
            "external_effect_job": {
                "id": external_effect_summary.get("id"),
                "effect_type": external_effect_summary.get("effect_type"),
                "status": external_effect_summary.get("status"),
                "execution_mode": external_effect_summary.get("execution_mode"),
                "idempotency_key": external_effect_summary.get("idempotency_key"),
            } if external_effect_summary else {},
        },
        payload_summary={
            "external_userid_redacted": _redact_external_userid(external_userid),
            "tag_count": len(normalized_tags),
            "tag_ids_count": len(normalized_tags),
            "source": source,
            "effect_type": effect_type,
        },
    )
    return {"status": "emitted", "event_id": result["event"]["event_id"], "consumer_run_count": len(result.get("consumer_runs") or [])}


def emit_ai_campaign_shadow_event(
    *,
    command: Command,
    event_type: str,
    campaign: dict[str, Any],
) -> dict[str, Any]:
    if not _event_enabled(event_type):
        return {"status": "skipped", "reason": "internal_events_disabled_or_event_type_not_allowed"}
    campaign_code = _text(campaign.get("campaign_code") or command.payload.get("campaign_code"))
    if not campaign_code:
        return {"status": "skipped", "reason": "campaign_code_missing"}
    register_shadow_event_consumers()
    stable_key = command.idempotency_key or command.command_id
    result = InternalEventService().emit_event(
        event_type=event_type,
        event_version=1,
        aggregate_type="ai_campaign",
        aggregate_id=campaign_code,
        subject_type="ai_campaign",
        subject_id=campaign_code,
        idempotency_key=f"{event_type}:{campaign_code}:{stable_key}",
        source_module="cloud_orchestrator.campaigns_write",
        source_command_id=command.command_id,
        correlation_id=stable_key,
        context=command.context,
        payload={"campaign": dict(campaign or {})},
        payload_summary={
            "campaign_code": campaign_code,
            "review_status": _text(campaign.get("review_status")),
            "run_status": _text(campaign.get("run_status")),
            "source": command.context.source_route,
        },
    )
    return {"status": "emitted", "event_id": result["event"]["event_id"], "consumer_run_count": len(result.get("consumer_runs") or [])}


def emit_broadcast_task_created_shadow_event(
    *,
    job: dict[str, Any],
    source_module: str,
    source_route: str = "",
    operator: str = "",
    source: str = "",
) -> dict[str, Any]:
    if not _event_enabled(BROADCAST_TASK_CREATED_EVENT_TYPE):
        return {"status": "skipped", "reason": "internal_events_disabled_or_event_type_not_allowed"}
    job_id = _text(job.get("id") or job.get("job_id") or job.get("broadcast_job_id"))
    if not job_id:
        return {"status": "skipped", "reason": "broadcast_job_id_missing"}
    trace_id = _text(job.get("trace_id") or job.get("idempotency_key") or job.get("source_id") or job_id)
    register_shadow_event_consumers()
    result = InternalEventService().emit_event(
        event_type=BROADCAST_TASK_CREATED_EVENT_TYPE,
        event_version=1,
        aggregate_type="broadcast_job",
        aggregate_id=job_id,
        subject_type="broadcast_job",
        subject_id=job_id,
        idempotency_key=f"broadcast_task.created:{job_id}",
        source_module=source_module,
        source_command_id=_text(job.get("source_id")),
        correlation_id=_text(job.get("idempotency_key") or trace_id),
        context=CommandContext(
            actor_id=_text(operator or job.get("created_by")),
            actor_type="admin",
            trace_id=trace_id,
            request_id=f"broadcast_task.created:{job_id}",
            source_route=source_route,
        ),
        payload={"job": dict(job or {})},
        payload_summary={
            "count": int(job.get("target_count") or 0),
            "batch_id": _text(job.get("batch_key") or job.get("source_id") or job_id),
            "operator": _text(operator or job.get("created_by")),
            "source": _text(source or job.get("source_type") or source_module),
        },
    )
    return {"status": "emitted", "event_id": result["event"]["event_id"], "consumer_run_count": len(result.get("consumer_runs") or [])}


def emit_ops_plan_approved_shadow_event(
    *,
    plan: dict[str, Any],
    stats: dict[str, Any] | None = None,
    operator: str = "",
    aggregate_type: str = "cloud_orchestrator_plan",
    source_module: str = "cloud_orchestrator.application",
    source_route: str = "",
) -> dict[str, Any]:
    if not _event_enabled(OPS_PLAN_APPROVED_EVENT_TYPE):
        return {"status": "skipped", "reason": "internal_events_disabled_or_event_type_not_allowed"}
    plan_id = _text(plan.get("plan_id") or plan.get("id") or plan.get("code"))
    if not plan_id:
        return {"status": "skipped", "reason": "plan_id_missing"}
    source = _text(plan.get("source_type") or plan.get("business_domain") or "cloud_orchestrator")
    trace_id = _text(plan.get("trace_id") or plan_id)
    stats = dict(stats or {})
    register_shadow_event_consumers()
    result = InternalEventService().emit_event(
        event_type=OPS_PLAN_APPROVED_EVENT_TYPE,
        event_version=1,
        aggregate_type=aggregate_type,
        aggregate_id=plan_id,
        subject_type=aggregate_type,
        subject_id=plan_id,
        idempotency_key=f"ops_plan.approved:{aggregate_type}:{plan_id}",
        source_module=source_module,
        source_command_id=plan_id,
        correlation_id=trace_id,
        context=CommandContext(
            actor_id=_text(operator),
            actor_type="admin",
            trace_id=trace_id,
            request_id=f"ops_plan.approved:{plan_id}",
            source_route=source_route,
        ),
        payload={"plan": dict(plan or {}), "stats": stats},
        payload_summary={
            "count": int(stats.get("target_count") or plan.get("target_count") or 0),
            "batch_id": plan_id,
            "operator": _text(operator),
            "source": source,
        },
    )
    return {"status": "emitted", "event_id": result["event"]["event_id"], "consumer_run_count": len(result.get("consumer_runs") or [])}


def emit_owner_migration_executed_shadow_event(
    *,
    command: Any,
    result: dict[str, Any],
    source_route: str = "/api/admin/owner-migration/execute",
) -> dict[str, Any]:
    if not _event_enabled(OWNER_MIGRATION_EXECUTED_EVENT_TYPE):
        return {"status": "skipped", "reason": "internal_events_disabled_or_event_type_not_allowed"}
    result_id = _text(result.get("result_id") or result.get("job_id") or result.get("preview_token"))
    if not result_id:
        return {"status": "skipped", "reason": "owner_migration_result_id_missing"}
    rows = result.get("rows") if isinstance(result.get("rows"), list) else []
    external_userids = [
        _text(row.get("external_userid"))
        for row in rows
        if isinstance(row, dict) and _text(row.get("external_userid"))
    ]
    count = int(result.get("crm_updated") or result.get("touched_count") or result.get("requested_external_userids") or len(external_userids) or 0)
    operator = _text(result.get("operator") or getattr(command, "operator", ""))
    trace_id = result_id
    register_shadow_event_consumers()
    result_payload = InternalEventService().emit_event(
        event_type=OWNER_MIGRATION_EXECUTED_EVENT_TYPE,
        event_version=1,
        aggregate_type="owner_migration_session",
        aggregate_id=result_id,
        subject_type="owner_migration_session",
        subject_id=result_id,
        idempotency_key=f"owner_migration.executed:{result_id}",
        source_module="owner_migration.application",
        source_command_id=_text(result.get("preview_token") or result_id),
        correlation_id=_text(result.get("job_id") or result_id),
        context=CommandContext(
            actor_id=operator,
            actor_type="admin",
            trace_id=trace_id,
            request_id=f"owner_migration.executed:{result_id}",
            source_route=source_route,
        ),
        payload={
            "result_id": result_id,
            "job_id": _text(result.get("job_id")),
            "session_id": _text(result.get("session_id") or getattr(command, "session_id", "")),
            "external_userids": external_userids,
            "source_owner_userid": _text(result.get("source_owner_userid") or getattr(command, "source_owner_userid", "")),
            "target_owner_userid": _text(result.get("target_owner_userid") or getattr(command, "target_owner_userid", "")),
        },
        payload_summary={
            "count": count,
            "batch_id": result_id,
            "operator": operator,
            "source": "owner_migration",
        },
    )
    return {"status": "emitted", "event_id": result_payload["event"]["event_id"], "consumer_run_count": len(result_payload.get("consumer_runs") or [])}


def _event_enabled(event_type: str) -> bool:
    return internal_events_enabled() and event_type_allowed(event_type)


def safe_emit(label: str, func, **kwargs: Any) -> dict[str, Any]:
    try:
        return func(**kwargs)
    except Exception:
        LOGGER.exception("internal_event_shadow_emit_failed", extra={"label": label})
        return {"status": "failed", "error": "internal_event_shadow_emit_failed"}
