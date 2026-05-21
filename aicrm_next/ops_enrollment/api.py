from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    ExecuteUserOpsBatchSendCommand,
    GetUserOpsSendRecordQuery,
    GetUserOpsOverviewQuery,
    ListLeadPoolQuery,
    ListUserOpsSendRecordsQuery,
    PreviewUserOpsBatchSendCommand,
    RefreshUserOpsSendRecordStatusCommand,
    SetUserOpsDoNotDisturbCommand,
)
from .dto import BatchSendRequest, DoNotDisturbRequest, UserOpsFilters, UserOpsListRequest

router = APIRouter()


def _filters_from_query(
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
) -> UserOpsFilters:
    return UserOpsFilters(
        wecom_status=wecom_status,
        mobile_binding_status=mobile_binding_status,
        activation_bucket=activation_bucket,
        class_term_no=class_term_no,
        keyword=keyword,
        mobile=mobile,
        owner_userid=owner_userid,
    )


@router.get("/api/admin/user-ops/overview")
def user_ops_overview(
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
) -> dict:
    return GetUserOpsOverviewQuery()(
        UserOpsListRequest(
            filters=_filters_from_query(
                wecom_status,
                mobile_binding_status,
                activation_bucket,
                class_term_no,
                keyword,
                mobile,
                owner_userid,
            )
        )
    )


@router.get("/api/admin/user-ops/list")
def user_ops_list(
    wecom_status: str = "",
    mobile_binding_status: str = "",
    activation_bucket: str = "",
    class_term_no: str = "",
    keyword: str = "",
    mobile: str = "",
    owner_userid: str = "",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    return ListLeadPoolQuery()(
        UserOpsListRequest(
            filters=_filters_from_query(
                wecom_status,
                mobile_binding_status,
                activation_bucket,
                class_term_no,
                keyword,
                mobile,
                owner_userid,
            ),
            limit=limit,
            offset=offset,
        )
    )


@router.post("/api/admin/user-ops/batch-send/preview")
def user_ops_batch_send_preview(request: BatchSendRequest) -> dict:
    try:
        return PreviewUserOpsBatchSendCommand()(request)
    except ContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/user-ops/batch-send/execute")
def user_ops_batch_send_execute(request: BatchSendRequest) -> dict:
    try:
        return ExecuteUserOpsBatchSendCommand()(request)
    except ContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/admin/user-ops/do-not-disturb")
def user_ops_do_not_disturb(request: DoNotDisturbRequest) -> dict:
    try:
        return SetUserOpsDoNotDisturbCommand()(request)
    except ContractError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/admin/user-ops/send-records")
def user_ops_send_records(limit: int = 20, offset: int = 0) -> dict:
    return ListUserOpsSendRecordsQuery()(limit=limit, offset=offset)


@router.get("/api/admin/user-ops/send-records/{record_id}")
def user_ops_send_record_detail(record_id: str) -> dict:
    try:
        return GetUserOpsSendRecordQuery()(record_id=record_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/api/admin/user-ops/send-records/{record_id}/refresh")
def user_ops_send_record_refresh(record_id: str) -> dict:
    try:
        return RefreshUserOpsSendRecordStatusCommand()(record_id=record_id)
    except NotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/api/admin/user-ops/export")
def user_ops_export_stub() -> dict:
    return {"ok": True, "status": "stubbed", "items": [], "filename": "user_ops_export_stub.csv"}
