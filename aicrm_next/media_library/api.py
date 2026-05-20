from __future__ import annotations

from fastapi import APIRouter, HTTPException

from aicrm_next.shared.errors import ContractError, NotFoundError

from .application import (
    DeleteMediaItemCommand,
    GetMediaItemQuery,
    ListMediaFacetsQuery,
    ImportImageFromBase64Command,
    ImportImageFromUrlCommand,
    ListMediaItemsQuery,
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
def list_images(limit: int = 100, offset: int = 0) -> dict:
    return ListMediaItemsQuery("image")(limit=limit, offset=offset)


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
def delete_image(image_id: str) -> dict:
    try:
        return DeleteMediaItemCommand("image")(image_id)
    except Exception as exc:
        _raise_http(exc)


@router.get("/api/admin/attachment-library")
def list_attachments(limit: int = 100, offset: int = 0) -> dict:
    return ListMediaItemsQuery("attachment")(limit=limit, offset=offset)


@router.post("/api/admin/attachment-library")
def create_attachment(payload: AttachmentUpsertRequest) -> dict:
    return UpsertMediaItemCommand("attachment")(payload)


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
def list_miniprograms(limit: int = 100, offset: int = 0) -> dict:
    return ListMediaItemsQuery("miniprogram")(limit=limit, offset=offset)


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
