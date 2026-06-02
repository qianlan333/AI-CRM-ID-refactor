from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse

from .application import build_wecom_tag_application_service
from .dto import DryRunTagRequest, LiveTagRequest, ValidateTagIdsRequest
from .read_model import TagCatalogUnavailable, build_tag_catalog_repository
from aicrm_next.shared.runtime import fixture_mode, legacy_production_facade_enabled, production_environment


router = APIRouter()
read_router = APIRouter()


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _ensure_local_fixture_allowed() -> None:
    if production_environment() or legacy_production_facade_enabled() or not fixture_mode():
        raise HTTPException(
            status_code=503,
            detail={
                "ok": False,
                "error": "Next fixture WeCom tag API is disabled outside local fixture mode; production must use the legacy facade or live WeCom API.",
                "source_status": "fixture_disabled",
            },
        )


def _fixture_catalog() -> dict[str, Any]:
    synced_at = _timestamp()
    tags = [
        {
            "tag_id": "tag_fixture_active",
            "tag_name": "活跃客户",
            "group_id": "group_fixture_lifecycle",
            "group_name": "客户阶段",
            "usage_count": 0,
            "synced_at": synced_at,
        },
        {
            "tag_id": "tag_fixture_trial",
            "tag_name": "体验中",
            "group_id": "group_fixture_lifecycle",
            "group_name": "客户阶段",
            "usage_count": 0,
            "synced_at": synced_at,
        },
    ]
    return {
        "ok": True,
        "items": [
            {
                "tag_id": tag["tag_id"],
                "tag_name": tag["tag_name"],
                "group_id": tag["group_id"],
                "group_name": tag["group_name"],
            }
            for tag in tags
        ],
        "groups": [
            {
                "group_key": "group_fixture_lifecycle",
                "group_id": "group_fixture_lifecycle",
                "group_name": "客户阶段",
                "missing_group_id": False,
                "tag_count": len(tags),
                "tags": tags,
            }
        ],
        "total_tags": len(tags),
        "tag_limit": 1000,
        "synced_at": synced_at,
        "source_status": "next_fixture",
    }


def _production_unavailable(exc: Exception) -> JSONResponse:
    return JSONResponse(
        jsonable_encoder(
            {
                "ok": False,
                "degraded": True,
                "error": "WeCom tag catalog read model is unavailable.",
                "error_code": "production_unavailable",
                "source_status": "production_unavailable",
                "read_model_status": "unavailable",
                "route_owner": "ai_crm_next",
                "fallback_used": False,
                "real_external_call_executed": False,
                "page_error": str(exc),
                "groups": [],
                "tags": [],
                "items": [],
                "count": 0,
                "total_tags": 0,
                "tag_limit": 1000,
            }
        ),
        status_code=503,
    )


def _read_catalog_payload() -> dict:
    catalog = build_tag_catalog_repository().list_catalog()
    return catalog.to_payload()


@read_router.get("/api/admin/wecom/tags")
def list_admin_wecom_tags_read_model():
    try:
        return _read_catalog_payload()
    except TagCatalogUnavailable as exc:
        return _production_unavailable(exc)


@read_router.get("/api/admin/wecom/tag-groups")
def list_admin_wecom_tag_groups_read_model():
    try:
        payload = _read_catalog_payload()
    except TagCatalogUnavailable as exc:
        return _production_unavailable(exc)
    return {**payload, "items": payload["groups"], "count": len(payload["groups"])}


@router.post("/api/admin/wecom/tags/sync")
@router.post("/api/admin/wecom/tags/sync-due")
def sync_admin_wecom_tags_fixture() -> dict:
    _ensure_local_fixture_allowed()
    catalog = _fixture_catalog()
    return {
        "ok": True,
        "fetched_groups": len(catalog["groups"]),
        "fetched_tags": len(catalog["items"]),
        "upserted_groups": len(catalog["groups"]),
        "upserted_tags": len(catalog["items"]),
        "marked_deleted_tags": 0,
        "source_status": "next_fixture",
        "error_message": "",
        "synced_at": catalog["synced_at"],
    }


@router.post("/api/admin/wecom/tag-groups")
@router.put("/api/admin/wecom/tag-groups/{group_id}")
@router.delete("/api/admin/wecom/tag-groups/{group_id}")
@router.post("/api/admin/wecom/tags")
@router.put("/api/admin/wecom/tags/{tag_id}")
@router.delete("/api/admin/wecom/tags/{tag_id}")
def mutate_admin_wecom_tags_fixture(group_id: str = "", tag_id: str = "") -> dict:
    _ensure_local_fixture_allowed()
    return {
        "ok": True,
        "result": {
            "source_status": "next_fixture",
            "group_id": group_id,
            "tag_id": tag_id,
            "synced_at": _timestamp(),
        },
    }


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


@router.get("/api/admin/wecom/tags/live/gate")
def list_wecom_tags_live_gate() -> dict:
    return build_wecom_tag_application_service().list_wecom_tags_live()


@router.post("/api/admin/wecom/tags/live/mark")
def mark_tags_live(payload: LiveTagRequest) -> dict:
    return build_wecom_tag_application_service().mark_tags_live(
        external_userid=payload.external_userid,
        tag_ids=payload.tag_ids,
        operator=payload.operator,
        idempotency_key=payload.idempotency_key,
    )


@router.post("/api/admin/wecom/tags/live/unmark")
def unmark_tags_live(payload: LiveTagRequest) -> dict:
    return build_wecom_tag_application_service().unmark_tags_live(
        external_userid=payload.external_userid,
        tag_ids=payload.tag_ids,
        operator=payload.operator,
        idempotency_key=payload.idempotency_key,
    )
