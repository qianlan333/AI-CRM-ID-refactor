from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    ApplyActivationWebhookCommand,
    CreateAgentCommand,
    GetAgentOutputDetailQuery,
    GetAgentRunDetailQuery,
    ListAgentsQuery,
    ListAgentOutputsQuery,
    ListAgentRunsQuery,
)
from .signup_conversion_read_model import SignupConversionReadModel




from .customer_webhooks import (
    ApplyCustomerActivationWebhookCommand,
    CustomerAutomationWebhookInputError,
    PlanCustomerWebhookDeliveryRetryCommand,
    PlanCustomerWebhookDeliveryRetryDueCommand,
    diagnostics_payload as customer_webhook_diagnostics_payload,
    execute_customer_webhook_command,
    normalize_actor as normalize_customer_webhook_actor,
    normalize_delivery_id,
    normalize_limit as normalize_customer_webhook_limit,
    normalize_mobile,
)
from .dto import (
    ActivationWebhookRequest,
    AgentCreateRequest,
    AgentListRequest,
    AgentOutputDetailRequest,
    AgentOutputListRequest,
    AgentRunDetailRequest,
    AgentRunListRequest,
)
from .group_ops.api import router as group_ops_router

router = APIRouter()
router.include_router(group_ops_router)

_CUSTOMER_WEBHOOK_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Outbound-Webhook-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
    "X-AICRM-WeCom-Send-Executed": "false",
}
_AUTOMATION_READ_MODEL_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
}
_AUTOMATION_PROGRAM_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
}
_RETIRED_AUTOMATION_HEADERS = {
    "X-AICRM-Route-Owner": "ai_crm_next",
    "X-AICRM-Fallback-Used": "false",
    "X-AICRM-Legacy-Automation-Retired": "true",
    "X-AICRM-Real-External-Call-Executed": "false",
    "X-AICRM-Automation-Runtime-Executed": "false",
}


def _retired_automation_response(error: str, *, replacement: str = "/admin/automation-conversion") -> JSONResponse:
    return JSONResponse(
        {
            "ok": False,
            "error": error,
            "message": "旧自动化运营方案 / 阶段 / 任务编排链路已退场，请使用 AI 自动化运营人群包。",
            "replacement": replacement,
            "real_external_call_executed": False,
            "automation_runtime_executed": False,
        },
        status_code=410,
        headers=_RETIRED_AUTOMATION_HEADERS,
    )


@router.api_route(
    "/api/admin/automation-conversion/programs",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_programs_retired",
)
def retired_automation_programs_api() -> JSONResponse:
    return _retired_automation_response("legacy_automation_program_retired")


@router.api_route(
    "/api/admin/automation-conversion/programs/{retired_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_program_detail_retired",
)
def retired_automation_program_detail_api(retired_path: str = "") -> JSONResponse:
    del retired_path
    return _retired_automation_response("legacy_automation_program_retired")


@router.api_route(
    "/api/admin/automation-conversion/member/{retired_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_member_actions_retired",
)
def retired_automation_member_action_api(retired_path: str = "") -> JSONResponse:
    del retired_path
    return _retired_automation_response("legacy_automation_member_action_retired")




@router.api_route(
    "/api/admin/automation-conversion/member",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS", "HEAD"],
    name="api_automation_member_detail_retired",
)
def retired_automation_member_detail_api() -> JSONResponse:
    return _retired_automation_response("legacy_automation_member_action_retired")


@router.api_route(
    "/api/admin/automation-conversion/members/{member_id}/push-openclaw-context",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_member_push_openclaw_retired",
)
def retired_automation_member_push_openclaw_api(member_id: str = "") -> JSONResponse:
    del member_id
    return _retired_automation_response("legacy_automation_member_action_retired")


@router.api_route(
    "/api/admin/automation-conversion/tasks/run-due",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_tasks_run_due_retired",
)
def retired_automation_tasks_run_due_api() -> JSONResponse:
    return _retired_automation_response("legacy_automation_task_runner_retired")


@router.api_route(
    "/api/admin/automation-conversion/execution-items/{execution_item_id}/send-via-bazhuayu",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_execution_item_outbound_retired",
)
def retired_automation_execution_item_outbound_api(execution_item_id: int) -> JSONResponse:
    del execution_item_id
    return _retired_automation_response("legacy_automation_execution_outbound_retired")


@router.api_route(
    "/api/admin/automation-conversion/reply-monitor/{retired_path:path}",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_reply_monitor_retired",
)
def retired_automation_reply_monitor_api(retired_path: str = "") -> JSONResponse:
    del retired_path
    return _retired_automation_response("legacy_automation_reply_monitor_retired")


@router.api_route(
    "/api/admin/automation-conversion/jobs/run-due/preview",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_jobs_run_due_preview_retired",
)
def retired_automation_jobs_run_due_preview_api() -> JSONResponse:
    return _retired_automation_response("legacy_automation_jobs_runner_retired")


@router.api_route(
    "/api/admin/automation-conversion/jobs/run-due",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    name="api_automation_jobs_run_due_retired",
)
def retired_automation_jobs_run_due_api() -> JSONResponse:
    return _retired_automation_response("legacy_automation_jobs_runner_retired")


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _json_result(payload: dict) -> JSONResponse:
    status_code = int(payload.get("status_code") or 200)
    return JSONResponse(payload, status_code=status_code)


def _customer_webhook_error(error: str, *, source_status: str, status_code: int = 400) -> JSONResponse:
    payload = customer_webhook_diagnostics_payload(source_status)
    payload.update(
        {
            "ok": False,
            "error": error,
            "status": "input_error" if status_code == 400 else "error",
            "planned_count": 0,
            "processed_count": 0,
            "sent_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "candidate_count": 0,
            "candidates": [],
            "estimated_actions": {
                "planned_action_count": 0,
                "external_call_count": 0,
                "blocked_external_call_count": 0,
                "local_projection_count": 0,
            },
        }
    )
    return JSONResponse(payload, status_code=status_code, headers=_CUSTOMER_WEBHOOK_HEADERS)


async def _customer_webhook_payload(request: Request) -> dict[str, Any]:
    if request.headers.get("content-type", "").lower().startswith("application/json"):
        try:
            payload = await request.json()
        except Exception as exc:
            raise CustomerAutomationWebhookInputError("payload must be valid JSON") from exc
    else:
        body = await request.body()
        payload = {} if not body else await request.json()
    if payload is None:
        merged: dict[str, Any] = {}
    elif isinstance(payload, dict):
        merged = dict(payload)
    else:
        raise CustomerAutomationWebhookInputError("payload must be an object")
    for key in ("mobile", "phone", "activated_at", "source", "limit", "dry_run"):
        if key not in merged and key in request.query_params:
            merged[key] = request.query_params.get(key)
    return merged


def _bool_payload(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    return default


def _customer_webhook_common(request: Request, payload: dict[str, Any], source_route: str) -> dict[str, Any]:
    return {
        "idempotency_key": str(request.headers.get("Idempotency-Key") or payload.get("idempotency_key") or "").strip(),
        "actor_id": normalize_customer_webhook_actor(
            payload.get("operator_id") or payload.get("operator") or payload.get("actor_id") or request.headers.get("X-AICRM-Actor")
        ),
        "actor_type": str(payload.get("actor_type") or "system").strip(),
        "source_route": source_route,
        "trace_id": str(request.headers.get("X-AICRM-Trace-Id") or payload.get("trace_id") or "").strip(),
        "dry_run": _bool_payload(payload.get("dry_run"), default=True),
    }


def _customer_webhook_response(command, *, source_status: str) -> JSONResponse:
    try:
        payload = execute_customer_webhook_command(command)
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    except Exception as exc:
        return _customer_webhook_error(str(exc) or "customer_automation_webhook_unavailable", source_status=source_status, status_code=503)
    return JSONResponse(payload, headers=_CUSTOMER_WEBHOOK_HEADERS)


@router.options("/api/customers/automation/activation-webhook")
def api_customer_automation_activation_webhook_options() -> JSONResponse:
    return JSONResponse(
        customer_webhook_diagnostics_payload("next_customer_activation_webhook"),
        headers=_CUSTOMER_WEBHOOK_HEADERS,
    )


@router.post("/api/customers/automation/activation-webhook")
async def api_customer_automation_activation_webhook(request: Request) -> JSONResponse:
    source_status = "next_customer_activation_webhook"
    try:
        payload = await _customer_webhook_payload(request)
        command = ApplyCustomerActivationWebhookCommand(
            **_customer_webhook_common(request, payload, "/api/customers/automation/activation-webhook"),
            mobile=normalize_mobile(payload.get("mobile") or payload.get("phone")),
            activated_at=str(payload.get("activated_at") or "").strip(),
            source=str(payload.get("source") or "").strip(),
            raw_payload=payload,
        )
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _customer_webhook_response(command, source_status=source_status)


@router.options("/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry")
def api_customer_automation_webhook_delivery_retry_options(delivery_id: int) -> JSONResponse:
    payload = customer_webhook_diagnostics_payload("next_customer_webhook_retry_plan")
    payload["delivery_id"] = delivery_id
    return JSONResponse(payload, headers=_CUSTOMER_WEBHOOK_HEADERS)


@router.post("/api/customers/automation/webhook-deliveries/{delivery_id:int}/retry")
async def api_plan_customer_automation_webhook_delivery_retry(delivery_id: int, request: Request) -> JSONResponse:
    source_status = "next_customer_webhook_retry_plan"
    try:
        payload = await _customer_webhook_payload(request)
        command = PlanCustomerWebhookDeliveryRetryCommand(
            **_customer_webhook_common(
                request,
                payload,
                f"/api/customers/automation/webhook-deliveries/{delivery_id}/retry",
            ),
            delivery_id=normalize_delivery_id(delivery_id),
        )
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _customer_webhook_response(command, source_status=source_status)


@router.options("/api/customers/automation/webhook-deliveries/retry-due")
def api_customer_automation_webhook_delivery_retry_due_options() -> JSONResponse:
    return JSONResponse(
        customer_webhook_diagnostics_payload("next_customer_webhook_retry_due_plan"),
        headers=_CUSTOMER_WEBHOOK_HEADERS,
    )


@router.post("/api/customers/automation/webhook-deliveries/retry-due")
async def api_plan_customer_automation_webhook_delivery_retry_due(request: Request) -> JSONResponse:
    source_status = "next_customer_webhook_retry_due_plan"
    try:
        payload = await _customer_webhook_payload(request)
        command = PlanCustomerWebhookDeliveryRetryDueCommand(
            **_customer_webhook_common(request, payload, "/api/customers/automation/webhook-deliveries/retry-due"),
            limit=normalize_customer_webhook_limit(payload.get("limit"), default=20),
        )
    except CustomerAutomationWebhookInputError as exc:
        return _customer_webhook_error(str(exc) or "input_error", source_status=source_status, status_code=400)
    return _customer_webhook_response(command, source_status=source_status)


@router.get("/api/admin/automation-conversion/contract")
def automation_contract() -> JSONResponse:
    return _retired_automation_response("legacy_automation_contract_retired")


@router.get("/api/admin/automation-conversion/overview")
def automation_overview() -> JSONResponse:
    return _retired_automation_response("legacy_automation_overview_retired")


@router.get("/api/admin/automation-conversion/pools")
def automation_pools() -> JSONResponse:
    return _retired_automation_response("legacy_automation_pools_retired")


@router.get("/api/admin/automation-conversion/agents")
def list_agents(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_id: int | None = None,
    task_id: int | None = None,
    agent_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = AgentListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_id=node_id,
        task_id=task_id,
        agent_type=agent_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListAgentsQuery()(request))


@router.get("/api/admin/automation-conversion/agents/options")
def agent_options(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_id: int | None = None,
    task_id: int | None = None,
    agent_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> JSONResponse:
    request = AgentListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_id=node_id,
        task_id=task_id,
        agent_type=agent_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListAgentsQuery()(request))


@router.post("/api/admin/automation-conversion/agents")
def create_agent(payload: AgentCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateAgentCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-outputs")
def list_agent_outputs(
    page: int = 1,
    page_size: int = 50,
    request_id: str = "",
    external_contact_id: str = "",
    userid: str = "",
    agent_code: str = "",
    output_type: str = "",
    applied_status: str = "",
    min_confidence: float | None = None,
    max_confidence: float | None = None,
    has_error: bool | None = None,
    visibility: str = "masked",
) -> JSONResponse:
    request = AgentOutputListRequest(
        page=page,
        page_size=page_size,
        request_id=request_id,
        external_contact_id=external_contact_id,
        userid=userid,
        agent_code=agent_code,
        output_type=output_type,
        applied_status=applied_status,
        min_confidence=min_confidence,
        max_confidence=max_confidence,
        has_error=has_error,
        visibility=visibility,
    )
    try:
        return _json_result(ListAgentOutputsQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-outputs/{output_id}")
def get_agent_output_detail(output_id: str, visibility: str = "masked") -> JSONResponse:
    request = AgentOutputDetailRequest(output_id=output_id, visibility=visibility)
    try:
        return _json_result(GetAgentOutputDetailQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-runs")
def list_agent_runs(
    page: int = 1,
    page_size: int = 50,
    request_id: str = "",
    run_id: str = "",
    agent_code: str = "",
    run_status: str = "",
    trigger_source: str = "",
    external_contact_id: str = "",
    userid: str = "",
    task_id: int | None = None,
    workflow_id: int | None = None,
    started_after: str = "",
    started_before: str = "",
    has_error: bool | None = None,
    visibility: str = "masked",
) -> JSONResponse:
    request = AgentRunListRequest(
        page=page,
        page_size=page_size,
        request_id=request_id,
        run_id=run_id,
        agent_code=agent_code,
        run_status=run_status,
        trigger_source=trigger_source,
        external_contact_id=external_contact_id,
        userid=userid,
        task_id=task_id,
        workflow_id=workflow_id,
        started_after=started_after,
        started_before=started_before,
        has_error=has_error,
        visibility=visibility,
    )
    try:
        return _json_result(ListAgentRunsQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/agent-runs/{run_id}")
def get_agent_run_detail(run_id: str, visibility: str = "masked") -> JSONResponse:
    request = AgentRunDetailRequest(run_id=run_id, visibility=visibility)
    try:
        return _json_result(GetAgentRunDetailQuery()(request))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/execution-records")
def automation_execution_records(limit: int = 50, offset: int = 0) -> JSONResponse:
    del limit, offset
    return _retired_automation_response("legacy_automation_execution_records_retired")


@router.post("/api/customer-automation/activation-webhook")
def activation_webhook(payload: ActivationWebhookRequest) -> dict:
    try:
        return ApplyActivationWebhookCommand()(payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/customers/automation/signup-conversion/batches")
def signup_conversion_batches(limit: int = 20, cursor: str = "") -> JSONResponse:
    try:
        payload = SignupConversionReadModel().list_batches(limit=limit, cursor=cursor)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "route_owner": "ai_crm_next"}, status_code=400)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "signup_conversion_batches_unavailable",
                "page_error": str(exc),
                "route_owner": "ai_crm_next",
            },
            status_code=503,
        )
    return JSONResponse({"ok": True, "automation_batches": payload, "route_owner": "ai_crm_next"})


@router.get("/api/customers/automation/signup-conversion/batches/{batch_id}")
def signup_conversion_batch(batch_id: int) -> JSONResponse:
    try:
        payload = SignupConversionReadModel().batch_detail(batch_id)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "signup_conversion_batch_unavailable",
                "page_error": str(exc),
                "route_owner": "ai_crm_next",
            },
            status_code=503,
        )
    if not payload:
        return JSONResponse({"ok": False, "error": "batch not found", "route_owner": "ai_crm_next"}, status_code=404)
    return JSONResponse({"ok": True, "automation_batch": payload, "route_owner": "ai_crm_next"})


@router.get("/api/customers/automation/webhook-deliveries")
def customer_automation_webhook_deliveries(
    event_type: str = "",
    status: str = "",
    limit: int = 50,
) -> JSONResponse:
    try:
        payload = SignupConversionReadModel().list_webhook_deliveries(event_type=event_type, status=status, limit=limit)
    except ValueError as exc:
        return JSONResponse({"ok": False, "error": str(exc), "route_owner": "ai_crm_next"}, status_code=400)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "degraded": True,
                "source_status": "production_unavailable",
                "error_code": "webhook_deliveries_unavailable",
                "page_error": str(exc),
                "route_owner": "ai_crm_next",
            },
            status_code=503,
        )
    return JSONResponse({"ok": True, "deliveries": payload, "route_owner": "ai_crm_next"})
