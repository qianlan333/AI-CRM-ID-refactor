from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse

from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    DeleteMediaItemCommand,
    GetMediaItemQuery,
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


def _raise_http(exc: Exception) -> None:
    if isinstance(exc, NotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, ContractError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=400, detail=str(exc)) from exc


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
def get_image(image_id: str) -> dict:
    try:
        return GetMediaItemQuery("image")(image_id)
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
def create_miniprogram(payload: MiniprogramUpsertRequest) -> dict:
    return UpsertMediaItemCommand("miniprogram")(payload)


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
