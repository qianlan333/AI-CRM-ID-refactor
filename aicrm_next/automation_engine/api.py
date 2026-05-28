from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import production_data_ready
from aicrm_next.integration_gateway.legacy_automation_facade import (
    LegacyAutomationDataUnavailable,
    get_automation_overview_from_legacy,
    list_automation_pools_from_legacy,
)
from aicrm_next.integration_gateway import legacy_sidebar_read_facade

from .application import (
    ApplyActivationWebhookCommand,
    GetBehaviorSegmentRulesQuery,
    ConfirmConversionCommand,
    CreateAgentCommand,
    CreateTaskCommand,
    CreateWorkflowCommand,
    CreateWorkflowNodeCommand,
    DeleteWorkflowNodeCommand,
    EnterSilentPoolCommand,
    ExitMarketingCommand,
    CreateActionTemplateCommand,
    CreateProfileSegmentTemplateCommand,
    CreateTaskGroupCommand,
    GetAgentOutputDetailQuery,
    GetAgentRunDetailQuery,
    GetTaskDetailQuery,
    ListActionTemplatesQuery,
    ListAgentsQuery,
    ListAgentOutputsQuery,
    ListAgentRunsQuery,
    ListTasksQuery,
    ListTaskGroupsQuery,
    ListWorkflowsQuery,
    ListWorkflowNodesQuery,
    GetProfileSegmentTemplateCatalogQuery,
    GetProfileSegmentTemplateOptionsQuery,
    GetProfileSegmentTemplateQuery,
    GetAutomationMemberDetailQuery,
    GetAutomationOverviewQuery,
    GetAutomationRuntimeContractQuery,
    ListProfileSegmentTemplatesQuery,
    ListAutomationExecutionRecordsQuery,
    ListAutomationMembersQuery,
    ListAutomationPoolsQuery,
    OverrideFollowupTypeCommand,
    PushMemberContextToOpenClawCommand,
    SaveAgentMaterialsCommand,
    SaveBehaviorSegmentSendContentCommand,
    SaveProfileSegmentSendContentCommand,
    SaveUnifiedSendContentCommand,
    UpdateTaskCommand,
    UpdateWorkflowNodeCommand,
    UpdateTaskSendStrategyCommand,
    UpdateProfileSegmentTemplateCommand,
)
from .programs import (
    AutomationProgramDataUnavailable,
    copy_automation_program_operation_task,
    create_automation_program_operation_task,
    create_automation_program_operation_task_group,
    delete_automation_program_operation_task_group,
    list_automation_program_operation_tasks,
    preview_automation_program_operation_task_audience,
    save_automation_program_audience_entry_rule,
    save_automation_program_operation_task_content,
    save_automation_program_segmentation,
    set_automation_program_operation_task_status,
    update_automation_program_operation_task,
    update_automation_program_operation_task_send_strategy,
)
from .dto import (
    ActivationWebhookRequest,
    AgentMaterialsUpdateRequest,
    AgentCreateRequest,
    AgentListRequest,
    AgentOutputDetailRequest,
    AgentOutputListRequest,
    AgentRunDetailRequest,
    AgentRunListRequest,
    ActionTemplateCreateRequest,
    ActionTemplateListRequest,
    AutomationActionRequest,
    BehaviorSegmentSendContentUpdateRequest,
    OverrideFollowupTypeRequest,
    ProfileSegmentSendContentUpdateRequest,
    ProfileSegmentTemplateCreateRequest,
    ProfileSegmentTemplateListRequest,
    ProfileSegmentTemplateUpdateRequest,
    PushOpenClawContextRequest,
    SendStrategyUpdateRequest,
    TaskCreateRequest,
    TaskGroupCreateRequest,
    TaskGroupListRequest,
    TaskListRequest,
    TaskUpdateRequest,
    UnifiedSendContentUpdateRequest,
    WorkflowCreateRequest,
    WorkflowListRequest,
    WorkflowNodeCreateRequest,
    WorkflowNodeListRequest,
    WorkflowNodeUpdateRequest,
)
from .group_ops.api import router as group_ops_router

router = APIRouter()
router.include_router(group_ops_router)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _json_result(payload: dict) -> JSONResponse:
    status_code = int(payload.get("status_code") or 200)
    return JSONResponse(payload, status_code=status_code)


@router.get("/api/admin/automation-conversion/contract")
def automation_contract() -> dict:
    return GetAutomationRuntimeContractQuery()()


@router.get("/api/admin/automation-conversion/overview")
def automation_overview() -> dict:
    if production_data_ready():
        try:
            return get_automation_overview_from_legacy()
        except LegacyAutomationDataUnavailable as exc:
            raise HTTPException(status_code=503, detail=f"legacy automation production data unavailable: {exc}") from exc
    return GetAutomationOverviewQuery()()


@router.get("/api/admin/automation-conversion/pools")
def automation_pools() -> dict:
    if production_data_ready():
        try:
            return list_automation_pools_from_legacy()
        except LegacyAutomationDataUnavailable as exc:
            raise HTTPException(status_code=503, detail=f"legacy automation production data unavailable: {exc}") from exc
    return ListAutomationPoolsQuery()()


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/segmentation",
    name="api_admin_automation_program_setup_segmentation",
)
def save_automation_program_setup_segmentation(program_id: int, payload: dict) -> dict:
    try:
        result = save_automation_program_segmentation(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "source_status": "ai_crm_next", "route_owner": "ai_crm_next", **result}


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/audience-entry-rule",
    name="api_admin_automation_program_setup_audience_entry_rule",
)
def save_automation_program_setup_audience_entry_rule(program_id: int, payload: dict) -> dict:
    try:
        result = save_automation_program_audience_entry_rule(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"ok": True, "source_status": "ai_crm_next", "route_owner": "ai_crm_next", **result}


@router.get(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks",
    name="api_admin_automation_program_setup_operation_tasks",
)
def list_automation_program_setup_operation_tasks(program_id: int) -> dict:
    try:
        return list_automation_program_operation_tasks(int(program_id))
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups",
    name="api_admin_automation_program_setup_operation_task_groups_create",
)
def create_automation_program_setup_operation_task_group(program_id: int, payload: dict) -> dict:
    try:
        return create_automation_program_operation_task_group(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-task-groups/{group_id}",
    name="api_admin_automation_program_setup_operation_task_groups_delete",
)
def delete_automation_program_setup_operation_task_group(program_id: int, group_id: int) -> dict:
    try:
        return delete_automation_program_operation_task_group(int(program_id), int(group_id), operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks",
    name="api_admin_automation_program_setup_operation_tasks_create",
)
def create_automation_program_setup_operation_task(program_id: int, payload: dict) -> dict:
    try:
        return create_automation_program_operation_task(int(program_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}",
    name="api_admin_automation_program_setup_operation_tasks_get",
)
def get_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        result = list_automation_program_operation_tasks(int(program_id))
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    task = next((item for item in list(result.get("tasks") or result.get("items") or []) if int(item.get("id") or 0) == int(task_id)), None)
    if not task:
        raise HTTPException(status_code=404, detail=f"operation task {task_id} not found")
    return {"ok": True, "route_owner": "ai_crm_next", "source_status": result.get("source_status") or "ai_crm_next", "task": task}


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}",
    name="api_admin_automation_program_setup_operation_tasks_update",
)
def update_automation_program_setup_operation_task(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return update_automation_program_operation_task(int(program_id), int(task_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/copy",
    name="api_admin_automation_program_setup_operation_tasks_copy",
)
def copy_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return copy_automation_program_operation_task(int(program_id), int(task_id), operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/activate",
    name="api_admin_automation_program_setup_operation_tasks_activate",
)
def activate_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return set_automation_program_operation_task_status(int(program_id), int(task_id), "active", operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/pause",
    name="api_admin_automation_program_setup_operation_tasks_pause",
)
def pause_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return set_automation_program_operation_task_status(int(program_id), int(task_id), "paused", operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}",
    name="api_admin_automation_program_setup_operation_tasks_archive",
)
def archive_automation_program_setup_operation_task(program_id: int, task_id: int) -> dict:
    try:
        return set_automation_program_operation_task_status(int(program_id), int(task_id), "archived", operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/preview-audience",
    name="api_admin_automation_program_setup_operation_tasks_preview_audience",
)
def preview_automation_program_setup_operation_task_audience(program_id: int, task_id: int, payload: dict) -> dict:
    del task_id
    try:
        return preview_automation_program_operation_task_audience(int(program_id), payload)
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-strategy",
    name="api_admin_automation_program_setup_operation_tasks_send_strategy",
)
def update_automation_program_setup_operation_task_send_strategy(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return update_automation_program_operation_task_send_strategy(int(program_id), int(task_id), payload, operator_id="admin")
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/unified",
    name="api_admin_automation_program_setup_operation_tasks_send_content_unified",
)
def save_automation_program_setup_operation_task_unified_content(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="unified", operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/profile-segments/{segment_key}",
    name="api_admin_automation_program_setup_operation_tasks_send_content_profile",
)
def save_automation_program_setup_operation_task_profile_content(program_id: int, task_id: int, segment_key: str, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="profile", segment_key=segment_key, operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/behavior-segments/{segment_key}",
    name="api_admin_automation_program_setup_operation_tasks_send_content_behavior",
)
def save_automation_program_setup_operation_task_behavior_content(program_id: int, task_id: int, segment_key: str, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="behavior", segment_key=segment_key, operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/api/admin/automation-conversion/programs/{program_id}/setup/operation-tasks/{task_id}/send-content/agent-materials",
    name="api_admin_automation_program_setup_operation_tasks_send_content_agent",
)
def save_automation_program_setup_operation_task_agent_content(program_id: int, task_id: int, payload: dict) -> dict:
    try:
        return save_automation_program_operation_task_content(
            int(program_id), int(task_id), payload, content_kind="agent", operator_id="admin"
        )
    except AutomationProgramDataUnavailable as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/api/admin/automation-conversion/action-templates")
def list_action_templates(
    template_source: str = "",
    category: str = "",
    keyword: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = ActionTemplateListRequest(
        template_source=template_source,
        category=category,
        keyword=keyword,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListActionTemplatesQuery()(request))


@router.post("/api/admin/automation-conversion/action-templates")
def create_action_template(payload: ActionTemplateCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateActionTemplateCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/task-groups")
def list_task_groups(
    program_id: int | None = None,
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = TaskGroupListRequest(
        program_id=program_id,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListTaskGroupsQuery()(request))


@router.post("/api/admin/automation-conversion/task-groups")
def create_task_group(payload: TaskGroupCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateTaskGroupCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/workflows")
def list_workflows(
    program_id: int | None = None,
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = WorkflowListRequest(
        program_id=program_id,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListWorkflowsQuery()(request))


@router.post("/api/admin/automation-conversion/workflows")
def create_workflow(payload: WorkflowCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateWorkflowCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/workflow-nodes")
def list_workflow_nodes(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = WorkflowNodeListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_type=node_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListWorkflowNodesQuery()(request))


@router.post("/api/admin/automation-conversion/workflow-nodes")
def create_workflow_node(payload: WorkflowNodeCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateWorkflowNodeCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/workflows/{workflow_id}/nodes")
def list_workflow_nodes_for_workflow(
    workflow_id: int,
    program_id: int | None = None,
    node_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = WorkflowNodeListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_type=node_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListWorkflowNodesQuery()(request))


@router.post("/api/admin/automation-conversion/workflows/{workflow_id}/nodes")
def create_workflow_node_for_workflow(workflow_id: int, payload: WorkflowNodeCreateRequest) -> JSONResponse:
    try:
        request = payload.model_copy(update={"workflow_id": workflow_id})
        return _json_result(CreateWorkflowNodeCommand()(request))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/workflow-nodes/{node_id}")
def update_workflow_node(node_id: int, payload: WorkflowNodeUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateWorkflowNodeCommand()(node_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/automation-conversion/workflow-nodes/{node_id}")
def delete_workflow_node(node_id: int, operator: str = "system") -> JSONResponse:
    try:
        return _json_result(DeleteWorkflowNodeCommand()(node_id, operator=operator))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/tasks")
def list_tasks(
    program_id: int | None = None,
    workflow_id: int | None = None,
    node_id: int | None = None,
    group_id: int | None = None,
    task_type: str = "",
    status: str = "",
    include_archived: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = TaskListRequest(
        program_id=program_id,
        workflow_id=workflow_id,
        node_id=node_id,
        group_id=group_id,
        task_type=task_type,
        status=status,
        include_archived=include_archived,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListTasksQuery()(request))


@router.post("/api/admin/automation-conversion/tasks")
def create_task(payload: TaskCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateTaskCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/tasks/{task_id}")
def get_task_detail(task_id: int) -> JSONResponse:
    try:
        return _json_result(GetTaskDetailQuery()(task_id))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}")
def update_task(task_id: int, payload: TaskUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateTaskCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-strategy")
def update_task_send_strategy(task_id: int, payload: SendStrategyUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateTaskSendStrategyCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/unified")
def save_unified_send_content(task_id: int, payload: UnifiedSendContentUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveUnifiedSendContentCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/profile-segments/{segment_key}")
def save_profile_segment_send_content(task_id: int, segment_key: str, payload: ProfileSegmentSendContentUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveProfileSegmentSendContentCommand()(task_id, segment_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/behavior-segments/{segment_key}")
def save_behavior_segment_send_content(task_id: int, segment_key: str, payload: BehaviorSegmentSendContentUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveBehaviorSegmentSendContentCommand()(task_id, segment_key, payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/tasks/{task_id}/send-content/agent-materials")
def save_agent_materials(task_id: int, payload: AgentMaterialsUpdateRequest) -> JSONResponse:
    try:
        return _json_result(SaveAgentMaterialsCommand()(task_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/behavior-segment-rules")
def behavior_segment_rules() -> JSONResponse:
    return _json_result(GetBehaviorSegmentRulesQuery()())


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


@router.get("/api/admin/automation-conversion/profile-segment-templates/catalog")
def profile_segment_template_catalog() -> JSONResponse:
    return _json_result(GetProfileSegmentTemplateCatalogQuery()())


@router.get("/api/admin/automation-conversion/profile-segment-templates")
def list_profile_segment_templates(
    enabled_only: bool = False,
    program_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = ProfileSegmentTemplateListRequest(
        enabled_only=enabled_only,
        program_id=program_id,
        limit=limit,
        offset=offset,
    )
    return _json_result(ListProfileSegmentTemplatesQuery()(request))


@router.get("/api/admin/automation-conversion/profile-segment-templates/options")
def profile_segment_template_options(
    enabled_only: bool = True,
    program_id: int | None = None,
    limit: int = 50,
    offset: int = 0,
) -> JSONResponse:
    request = ProfileSegmentTemplateListRequest(
        enabled_only=enabled_only,
        program_id=program_id,
        limit=limit,
        offset=offset,
    )
    return _json_result(GetProfileSegmentTemplateOptionsQuery()(request))


@router.get("/api/admin/automation-conversion/profile-segment-templates/{template_id}")
def get_profile_segment_template(template_id: int) -> JSONResponse:
    try:
        return _json_result(GetProfileSegmentTemplateQuery()(template_id))
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/profile-segment-templates")
def create_profile_segment_template(payload: ProfileSegmentTemplateCreateRequest) -> JSONResponse:
    try:
        return _json_result(CreateProfileSegmentTemplateCommand()(payload))
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/automation-conversion/profile-segment-templates/{template_id}")
def update_profile_segment_template(template_id: int, payload: ProfileSegmentTemplateUpdateRequest) -> JSONResponse:
    try:
        return _json_result(UpdateProfileSegmentTemplateCommand()(template_id, payload))
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/members")
def automation_members(
    current_pool: str = "",
    followup_type: str = "",
    owner_userid: str = "",
    keyword: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return ListAutomationMembersQuery()(
        current_pool=current_pool,
        followup_type=followup_type,
        owner_userid=owner_userid,
        keyword=keyword,
        limit=limit,
        offset=offset,
    )


@router.get("/api/admin/automation-conversion/members/{member_id}")
def automation_member_detail(member_id: str) -> dict:
    try:
        return GetAutomationMemberDetailQuery()(member_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/override-followup-type")
def automation_override_followup_type(member_id: str, payload: OverrideFollowupTypeRequest) -> dict:
    try:
        return OverrideFollowupTypeCommand()(member_id, payload)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/confirm-conversion")
def automation_confirm_conversion(member_id: str, payload: AutomationActionRequest | None = None) -> dict:
    try:
        return ConfirmConversionCommand()(member_id, payload or AutomationActionRequest())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/enter-silent")
def automation_enter_silent(member_id: str, payload: AutomationActionRequest | None = None) -> dict:
    try:
        return EnterSilentPoolCommand()(member_id, payload or AutomationActionRequest())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/exit-marketing")
def automation_exit_marketing(member_id: str, payload: AutomationActionRequest | None = None) -> dict:
    try:
        return ExitMarketingCommand()(member_id, payload or AutomationActionRequest())
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/automation-conversion/members/{member_id}/push-openclaw-context")
def automation_push_openclaw_context(member_id: str, payload: PushOpenClawContextRequest | None = None) -> dict:
    try:
        return PushMemberContextToOpenClawCommand()(member_id, payload or PushOpenClawContextRequest())
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/automation-conversion/execution-records")
def automation_execution_records(limit: int = 50, offset: int = 0) -> dict:
    return ListAutomationExecutionRecordsQuery()(limit=limit, offset=offset)


@router.post("/api/customer-automation/activation-webhook")
def activation_webhook(payload: ActivationWebhookRequest) -> dict:
    try:
        return ApplyActivationWebhookCommand()(payload)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/customers/automation/signup-conversion/batches")
def signup_conversion_batches(limit: int = 20, cursor: str = "") -> JSONResponse:
    try:
        payload = legacy_sidebar_read_facade.signup_conversion_batch_list(limit=limit, cursor=cursor)
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
        payload = legacy_sidebar_read_facade.signup_conversion_batch_detail(batch_id)
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
        payload = legacy_sidebar_read_facade.webhook_delivery_list(event_type=event_type, status=status, limit=limit)
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
