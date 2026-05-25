from __future__ import annotations

from fastapi import APIRouter

from .application import build_wecom_tag_application_service
from .dto import DryRunTagRequest, ValidateTagIdsRequest


router = APIRouter()


@router.get("/api/admin/wecom/tags/fake-stub")
def list_wecom_tags() -> dict:
    return build_wecom_tag_application_service().list_wecom_tags()


@router.post("/api/admin/wecom/tags/fake-stub/validate")
def validate_tag_ids(payload: ValidateTagIdsRequest) -> dict:
    return build_wecom_tag_application_service().validate_tag_ids(payload.tag_ids)


@router.post("/api/admin/wecom/tags/fake-stub/dry-run/mark")
def dry_run_mark_tags(payload: DryRunTagRequest) -> dict:
    return build_wecom_tag_application_service().dry_run_mark_tags(
        external_userid=payload.external_userid,
        tag_ids=payload.tag_ids,
        operator=payload.operator,
        idempotency_key=payload.idempotency_key,
    )


@router.post("/api/admin/wecom/tags/fake-stub/dry-run/unmark")
def dry_run_unmark_tags(payload: DryRunTagRequest) -> dict:
    return build_wecom_tag_application_service().dry_run_unmark_tags(
        external_userid=payload.external_userid,
        tag_ids=payload.tag_ids,
        operator=payload.operator,
        idempotency_key=payload.idempotency_key,
    )
