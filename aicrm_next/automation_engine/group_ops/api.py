from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import JSONResponse

from aicrm_next.shared.errors import ApplicationError, ContractError, NotFoundError

from .application import (
    AddGroupOpsPlanGroupCommand,
    CreateGroupOpsNodeCommand,
    CreateGroupOpsPlanCommand,
    DeleteGroupOpsNodeCommand,
    GetGroupOpsPlanQuery,
    GetGroupOpsWebhookConfigQuery,
    ListGroupOpsGroupsQuery,
    ListGroupOpsNodesQuery,
    ListGroupOpsOwnersQuery,
    ListGroupOpsPlanGroupsQuery,
    ListGroupOpsPlansQuery,
    PreviewGroupOpsGroupsSyncCommand,
    PreviewGroupOpsPlanRunDueCommand,
    ReceiveGroupOpsWebhookCommand,
    RegenerateGroupOpsWebhookCommand,
    RemoveGroupOpsPlanGroupCommand,
    RunGroupOpsPlanDueCommand,
    SyncGroupOpsGroupsCommand,
    UpdateGroupOpsNodeCommand,
    UpdateGroupOpsPlanCommand,
)
from .dto import (
    GroupOpsBindGroupRequest,
    GroupOpsGroupSyncRequest,
    GroupOpsGroupsRequest,
    GroupOpsNodeRequest,
    GroupOpsPlanCreateRequest,
    GroupOpsPlanListRequest,
    GroupOpsRunDueRequest,
    GroupOpsPlanUpdateRequest,
    GroupOpsWebhookReceiveRequest,
)

router = APIRouter()


def _json_result(payload: dict) -> JSONResponse:
    return JSONResponse(payload, status_code=int(payload.get("status_code") or 200))


def _error_code_for(exc: Exception) -> str:
    message = str(exc)
    if "owner_userid must match" in message:
        return "group_owner_mismatch"
    if "content, images, or attachments is required" in message or "content.text or content.attachments" in message:
        return "content_required"
    if "webhook plan is not active" in message:
        return "plan_not_active"
    if "group ops plan is not active" in message:
        return "plan_not_active"
    if "invalid webhook token" in message:
        return "invalid_webhook_token"
    if "allowlist" in message:
        return "allowlist_required"
    if "max_outbound_tasks" in message:
        return "max_outbound_tasks_required"
    if "customer-group sync is disabled" in message or "wecom group sync" in message:
        return "wecom_group_sync_blocked"
    if isinstance(exc, NotFoundError):
        return "not_found"
    if isinstance(exc, ContractError):
        return "contract_error"
    return "application_error"


def _raise_http(exc: Exception) -> None:
    detail = {
        "ok": False,
        "error_code": _error_code_for(exc),
        "detail": str(exc),
        "route_owner": "ai_crm_next",
    }
    if isinstance(exc, ApplicationError):
        raise HTTPException(status_code=int(exc.status_code), detail=detail) from exc
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=detail) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=detail) from exc
    raise HTTPException(status_code=400, detail=detail) from exc


@router.get("/api/admin/automation-conversion/group-ops/plans")
def list_group_ops_plans(
    keyword: str = "",
    plan_type: str = "",
    status: str = "",
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    return _json_result(
        ListGroupOpsPlansQuery()(
            GroupOpsPlanListRequest(keyword=keyword, plan_type=plan_type, status=status, limit=limit, offset=offset)
        )
    )


@router.get("/api/admin/automation-conversion/group-ops/owners")
def list_group_ops_owners() -> JSONResponse:
    try:
        return _json_result(ListGroupOpsOwnersQuery()())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans")
def create_group_ops_plan(payload: GroupOpsPlanCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateGroupOpsPlanCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}")
def get_group_ops_plan(plan_id: int) -> JSONResponse:
    try:
        return _json_result(GetGroupOpsPlanQuery()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/group-ops/plans/{plan_id}")
def update_group_ops_plan(plan_id: int, payload: GroupOpsPlanUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateGroupOpsPlanCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups")
def list_group_ops_plan_groups(plan_id: int) -> JSONResponse:
    try:
        return _json_result(ListGroupOpsPlanGroupsQuery()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups")
def add_group_ops_plan_group(plan_id: int, payload: GroupOpsBindGroupRequest) -> JSONResponse:
    try:
        return _json_result(AddGroupOpsPlanGroupCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/group-ops/plans/{plan_id}/groups/{chat_id}")
def remove_group_ops_plan_group(plan_id: int, chat_id: str) -> JSONResponse:
    try:
        return _json_result(RemoveGroupOpsPlanGroupCommand()(plan_id, chat_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes")
def list_group_ops_nodes(plan_id: int) -> JSONResponse:
    try:
        return _json_result(ListGroupOpsNodesQuery()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes")
def create_group_ops_node(plan_id: int, payload: GroupOpsNodeRequest) -> JSONResponse:
    try:
        return _json_result(CreateGroupOpsNodeCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes/{node_id}")
def update_group_ops_node(plan_id: int, node_id: int, payload: GroupOpsNodeRequest) -> JSONResponse:
    try:
        return _json_result(UpdateGroupOpsNodeCommand()(plan_id, node_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/group-ops/plans/{plan_id}/nodes/{node_id}")
def delete_group_ops_node(plan_id: int, node_id: int) -> JSONResponse:
    try:
        return _json_result(DeleteGroupOpsNodeCommand()(plan_id, node_id))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/groups")
def list_group_ops_groups(
    keyword: str = "",
    owner_userid: str = "",
    plan_id: int | None = None,
    bind_status: str = "",
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    return _json_result(
        ListGroupOpsGroupsQuery()(
            GroupOpsGroupsRequest(
                keyword=keyword,
                owner_userid=owner_userid,
                plan_id=plan_id,
                bind_status=bind_status,
                limit=limit,
                offset=offset,
            )
        )
    )


@router.post("/api/admin/automation-conversion/group-ops/groups/sync/preview")
def preview_group_ops_groups_sync(payload: GroupOpsGroupSyncRequest) -> JSONResponse:
    try:
        return _json_result(PreviewGroupOpsGroupsSyncCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/groups/sync")
def sync_group_ops_groups(payload: GroupOpsGroupSyncRequest) -> JSONResponse:
    try:
        return _json_result(SyncGroupOpsGroupsCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/run-due/preview")
def preview_group_ops_plan_run_due(plan_id: int, payload: GroupOpsRunDueRequest) -> JSONResponse:
    try:
        return _json_result(PreviewGroupOpsPlanRunDueCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/run-due")
def run_group_ops_plan_due(plan_id: int, payload: GroupOpsRunDueRequest) -> JSONResponse:
    try:
        return _json_result(RunGroupOpsPlanDueCommand()(plan_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/group-ops/plans/{plan_id}/webhook")
def get_group_ops_webhook_config(plan_id: int) -> JSONResponse:
    try:
        return _json_result(GetGroupOpsWebhookConfigQuery()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/group-ops/plans/{plan_id}/webhook/regenerate")
def regenerate_group_ops_webhook(plan_id: int) -> JSONResponse:
    try:
        return _json_result(RegenerateGroupOpsWebhookCommand()(plan_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/automation/group-ops/webhooks/{webhook_key}")
def receive_group_ops_webhook(
    webhook_key: str,
    payload: GroupOpsWebhookReceiveRequest,
    authorization: str | None = Header(default=None),
) -> JSONResponse:
    try:
        return _json_result(ReceiveGroupOpsWebhookCommand()(webhook_key, payload, authorization=authorization))
    except Exception as exc:
        _raise_http(exc)
