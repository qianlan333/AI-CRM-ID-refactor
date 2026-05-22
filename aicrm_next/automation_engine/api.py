from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aicrm_next.shared.errors import ContractError, NotFoundError
from aicrm_next.shared.runtime import production_data_ready
from aicrm_next.integration_gateway.legacy_automation_facade import (
    LegacyAutomationDataUnavailable,
    get_automation_overview_from_legacy,
    list_automation_pools_from_legacy,
)

from .application import (
    ApplyActivationWebhookCommand,
    ConfirmConversionCommand,
    EnterSilentPoolCommand,
    ExitMarketingCommand,
    GetAutomationMemberDetailQuery,
    GetAutomationOverviewQuery,
    GetAutomationRuntimeContractQuery,
    ListAutomationExecutionRecordsQuery,
    ListAutomationMembersQuery,
    ListAutomationPoolsQuery,
    OverrideFollowupTypeCommand,
    PushMemberContextToOpenClawCommand,
)
from .dto import ActivationWebhookRequest, AutomationActionRequest, OverrideFollowupTypeRequest, PushOpenClawContextRequest

router = APIRouter()


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


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
