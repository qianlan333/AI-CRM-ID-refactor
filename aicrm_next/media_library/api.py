from __future__ import annotations

import logging
import time

from fastapi import APIRouter, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse, Response

from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    DeleteMediaItemCommand,
    GetMediaItemQuery,
    GetImageVariantQuery,
    ImportImageFromBase64Command,
    ImportImageFromUrlCommand,
    ListMediaFacetsQuery,
    ListMediaItemsQuery,
    TestResolveMiniprogramThumbCommand,
    UploadAttachmentCommand,
    UploadImageCommand,
    UpsertMediaItemCommand,
)
from .dto import AttachmentUpsertRequest, ImageFromBase64Request, ImageFromUrlRequest, ImageUpsertRequest, MiniprogramUpsertRequest

router = APIRouter()
logger = logging.getLogger(__name__)


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _error_response(exc: Exception, status_code: int = 400, *, headers: dict[str, str] | None = None) -> JSONResponse:
    if isinstance(exc, NotFoundError):
        status_code = 404
    elif isinstance(exc, ContractError):
        status_code = 400
    return JSONResponse(status_code=status_code, content={"ok": False, "error": str(exc)}, headers=headers or {})


@router.get("/api/admin/image-library")
def list_images(
    limit: int = 100,
    offset: int = 0,
    enabled_only: bool = True,
    q: str = "",
    category: str = "",
    tags: str = "",
    only_unlabeled: bool = False,
) -> dict:
    return ListMediaItemsQuery("image")(
        limit=limit,
        offset=offset,
        filters={
            "enabled_only": enabled_only,
            "q": q,
            "category": category,
            "tags": tags,
            "only_unlabeled": only_unlabeled,
        },
    )


@router.get("/api/admin/image-library/facets")
def list_image_facets() -> dict:
    return ListMediaFacetsQuery("image")()


@router.post("/api/admin/image-library")
def create_image(payload: ImageUpsertRequest) -> dict:
    return UpsertMediaItemCommand("image")(payload)


@router.post("/api/admin/image-library/from-url")
def image_from_url(payload: ImageFromUrlRequest) -> dict:
    return ImportImageFromUrlCommand()(payload)


@router.post("/api/admin/image-library/from-base64")
def image_from_base64(payload: ImageFromBase64Request) -> dict:
    return ImportImageFromBase64Command()(payload)


@router.post("/api/admin/image-library/upload")
async def upload_image(
    image: UploadFile = File(...),
    name: str = Form(""),
    description: str = Form(""),
    tags: str = Form(""),
    category: str = Form(""),
) -> dict:
    try:
        content = await image.read()
        return UploadImageCommand()(
            file_bytes=content,
            file_name=image.filename or "image.png",
            content_type=image.content_type or "application/octet-stream",
            name=name,
            description=description,
            tags=tags,
            category=category,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/image-library/{image_id}")
def get_image(image_id: str, include_data: bool = False, variant: str = "") -> dict:
    try:
        result = GetMediaItemQuery("image")(image_id, include_data=include_data)
        if variant:
            result["variant_url"] = f"/api/admin/image-library/{image_id}/variants/{variant}"
        return result
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/image-library/{image_id}/variants/{variant_key}")
def get_image_variant(image_id: str, variant_key: str, if_none_match: str | None = Header(default=None, alias="If-None-Match")) -> Response:
    try:
        result = GetImageVariantQuery()(image_id, variant_key)
        variant = result["variant"]
        etag = str(variant.get("etag") or "")
        headers = {
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": etag,
        }
        if if_none_match and etag and if_none_match == etag:
            return Response(status_code=304, headers=headers)
        return Response(content=variant.get("bytes") or b"", media_type=str(variant.get("mime_type") or "image/png"), headers=headers)
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/image-library/{image_id}")
def update_image(image_id: str, payload: ImageUpsertRequest) -> dict:
    try:
        return UpsertMediaItemCommand("image")(payload, image_id)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/image-library/{image_id}")
def delete_image(image_id: str, force: bool = Query(False)):
    try:
        result = DeleteMediaItemCommand("image")(image_id, force=force)
        if result.get("references") and result.get("ok") is False:
            return JSONResponse(status_code=409, content=result)
        return result
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/attachment-library")
def list_attachments(limit: int = 100, offset: int = 0, enabled_only: bool = True, q: str = "") -> dict:
    return ListMediaItemsQuery("attachment")(limit=limit, offset=offset, filters={"enabled_only": enabled_only, "q": q})


@router.post("/api/admin/attachment-library")
def create_attachment(payload: AttachmentUpsertRequest) -> dict:
    return UpsertMediaItemCommand("attachment")(payload)


@router.post("/api/admin/attachment-library/upload")
async def upload_attachment(
    attachment: UploadFile = File(...),
    name: str = Form(""),
    tags: str = Form(""),
) -> dict:
    try:
        content = await attachment.read()
        return UploadAttachmentCommand()(
            file_bytes=content,
            file_name=attachment.filename or "attachment.bin",
            content_type=attachment.content_type or "application/octet-stream",
            name=name,
            tags=tags,
        )
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/attachment-library/{attachment_id}")
def get_attachment(attachment_id: str) -> dict:
    try:
        return GetMediaItemQuery("attachment")(attachment_id)
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/attachment-library/{attachment_id}")
def update_attachment(attachment_id: str, payload: AttachmentUpsertRequest) -> dict:
    try:
        return UpsertMediaItemCommand("attachment")(payload, attachment_id)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/attachment-library/{attachment_id}")
def delete_attachment(attachment_id: str) -> dict:
    try:
        return DeleteMediaItemCommand("attachment")(attachment_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/miniprogram-library")
def list_miniprograms(limit: int = 100, offset: int = 0, enabled_only: bool = True, q: str = "") -> dict:
    return ListMediaItemsQuery("miniprogram")(limit=limit, offset=offset, filters={"enabled_only": enabled_only, "q": q})


@router.post("/api/admin/miniprogram-library")
def create_miniprogram(payload: MiniprogramUpsertRequest):
    started = time.perf_counter()
    def duration_headers() -> dict[str, str]:
        duration_ms = int((time.perf_counter() - started) * 1000)
        log = logger.warning if duration_ms > 2000 else logger.info
        log("POST /api/admin/miniprogram-library duration_ms=%s", duration_ms)
        return {"X-AICRM-Media-Library-Duration-Ms": str(duration_ms)}

    try:
        result = UpsertMediaItemCommand("miniprogram")(payload)
        return JSONResponse(content=result, headers=duration_headers())
    except Exception as exc:
        logger.exception("miniprogram library create failed")
        return _error_response(exc, headers=duration_headers())


@router.get("/api/admin/miniprogram-library/{item_id}")
def get_miniprogram(item_id: str) -> dict:
    try:
        return GetMediaItemQuery("miniprogram")(item_id)
    except Exception as exc:
        _raise_http(exc)


@router.put("/api/admin/miniprogram-library/{item_id}")
def update_miniprogram(item_id: str, payload: MiniprogramUpsertRequest) -> dict:
    try:
        return UpsertMediaItemCommand("miniprogram")(payload, item_id)
    except Exception as exc:
        _raise_http(exc)


@router.delete("/api/admin/miniprogram-library/{item_id}")
def delete_miniprogram(item_id: str) -> dict:
    try:
        return DeleteMediaItemCommand("miniprogram")(item_id)
    except Exception as exc:
        _raise_http(exc)


@router.post("/api/admin/miniprogram-library/{item_id}/test-resolve")
def test_resolve_miniprogram(item_id: str) -> dict:
    try:
        return TestResolveMiniprogramThumbCommand()(item_id)
    except Exception as exc:
        _raise_http(exc)
