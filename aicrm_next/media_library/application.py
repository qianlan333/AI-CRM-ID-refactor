from __future__ import annotations

import base64
from typing import Any

from aicrm_next.integration_gateway.media_adapters import build_cloud_storage_adapter, build_wecom_media_adapter, extract_base64_payload
from aicrm_next.shared.errors import ContractError

from .dto import AttachmentUpsertRequest, ImageFromBase64Request, ImageFromUrlRequest, ImageUpsertRequest, MiniprogramUpsertRequest
from .repo import MediaLibraryRepository, build_media_library_repository, normalize_tags


def _side_effect_safety() -> dict[str, bool]:
    return {
        "real_cloud_upload_executed": False,
        "real_wecom_media_upload_executed": False,
        "remote_url_fetched": False,
        "side_effect_executed": False,
    }


def _content_type_from_file_name(file_name: str, fallback: str = "image/png") -> str:
    lower = file_name.lower()
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".gif"):
        return "image/gif"
    if lower.endswith(".webp"):
        return "image/webp"
    if lower.endswith(".pdf"):
        return "application/pdf"
    return fallback


def _media_adapter_summary(cloud_result: dict[str, Any] | None, wecom_result: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "cloud_storage": cloud_result or {},
        "wecom_media": wecom_result or {},
        "side_effect_safety": _side_effect_safety(),
    }


class ListMediaItemsQuery:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, *, limit: int = 100, offset: int = 0, filters: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"ok": True, **self._repo.list_items(self._kind, limit=limit, offset=offset, filters=filters or {})}


class ListMediaFacetsQuery:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self) -> dict[str, Any]:
        return {"ok": True, **self._repo.list_facets(self._kind)}


class GetMediaItemQuery:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, item_id: str, *, include_data: bool = True) -> dict[str, Any]:
        item = self._repo.get_item(self._kind, item_id, include_data=include_data)
        if not item:
            from aicrm_next.shared.errors import NotFoundError

            raise NotFoundError(f"{self._kind} item not found")
        return {"ok": True, "item": item}


class GetImageVariantQuery:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, image_id: str, variant_key: str) -> dict[str, Any]:
        variant = self._repo.get_image_variant(image_id, variant_key)
        if not variant:
            from aicrm_next.shared.errors import NotFoundError

            raise NotFoundError("image variant not found")
        return {"ok": True, "variant": variant}


class UpsertMediaItemCommand:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, payload: dict[str, Any] | ImageUpsertRequest | AttachmentUpsertRequest | MiniprogramUpsertRequest, item_id: str | None = None) -> dict[str, Any]:
        data = payload.model_dump(by_alias=True, exclude_none=True) if hasattr(payload, "model_dump") else dict(payload)
        cloud_result: dict[str, Any] | None = None
        wecom_result: dict[str, Any] | None = None
        if self._kind == "image":
            file_name = str(data.get("file_name") or "image.png")
            data_url = str(data.get("data_url") or "")
            if data_url:
                data_base64 = extract_base64_payload(data_url)
                cloud_result = build_cloud_storage_adapter().put_base64_object(
                    data_base64=data_base64,
                    file_name=file_name,
                    content_type=str(data.get("content_type") or _content_type_from_file_name(file_name)),
                )
                wecom_result = build_wecom_media_adapter().upload_image(data_base64=data_base64, file_name=file_name)
                data = {
                    **data,
                    "storage_key": cloud_result.get("storage_key"),
                    "public_url": cloud_result.get("public_url"),
                    "wecom_media_id": wecom_result.get("media_id"),
                    "side_effect_safety": _side_effect_safety(),
                }
        if self._kind == "attachment":
            file_name = str(data.get("file_name") or "attachment.bin")
            data_base64 = str(data.get("data_base64") or "")
            if data_base64:
                content_type = str(data.get("mime_type") or _content_type_from_file_name(file_name, "application/octet-stream"))
                cloud_result = build_cloud_storage_adapter().put_base64_object(data_base64=data_base64, file_name=file_name, content_type=content_type)
                wecom_result = build_wecom_media_adapter().upload_attachment(data_base64=data_base64, file_name=file_name, content_type=content_type)
                data = {
                    **data,
                    "storage_key": cloud_result.get("storage_key"),
                    "public_url": cloud_result.get("public_url"),
                    "wecom_media_id": wecom_result.get("media_id"),
                    "side_effect_safety": _side_effect_safety(),
                }
        result = {"ok": True, "item": self._repo.save_item(self._kind, data, item_id)}
        if cloud_result or wecom_result:
            result["adapter_result"] = _media_adapter_summary(cloud_result, wecom_result)
        return result


class DeleteMediaItemCommand:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, item_id: str, *, force: bool = False) -> dict[str, Any]:
        return self._repo.delete_item(self._kind, item_id, force=force)


def _validate_image_upload(*, file_bytes: bytes, file_name: str, content_type: str) -> str:
    if not file_bytes:
        raise ContractError("image file is empty")
    if len(file_bytes) > 2 * 1024 * 1024:
        raise ContractError("image file too large; max 2MB")
    lower_name = file_name.lower()
    normalized = "image/jpeg" if content_type in {"image/jpg", "image/jpeg"} or lower_name.endswith((".jpg", ".jpeg")) else content_type
    if normalized not in {"image/png", "image/jpeg"}:
        raise ContractError("only JPG/PNG images are supported")
    if normalized == "image/png" and not file_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ContractError("invalid PNG image")
    if normalized == "image/jpeg" and not file_bytes.startswith(b"\xff\xd8"):
        raise ContractError("invalid JPG image")
    return normalized


class UploadImageCommand:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(
        self,
        *,
        file_bytes: bytes,
        file_name: str,
        content_type: str,
        name: str = "",
        description: str = "",
        tags: Any = None,
        category: str = "",
    ) -> dict[str, Any]:
        mime_type = _validate_image_upload(file_bytes=file_bytes, file_name=file_name, content_type=content_type)
        item = self._repo.save_item(
            "image",
            {
                "name": name or file_name,
                "file_name": file_name,
                "source": "upload",
                "source_url": "",
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
                "mime_type": mime_type,
                "content_type": mime_type,
                "file_size": len(file_bytes),
                "description": description,
                "tags": normalize_tags(tags),
                "category": category,
                "enabled": True,
                "ai_metadata": {},
            },
        )
        return {"ok": True, "item": item}


class UploadAttachmentCommand:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, *, file_bytes: bytes, file_name: str, content_type: str, name: str = "", tags: Any = None) -> dict[str, Any]:
        if not file_bytes:
            raise ContractError("attachment file is empty")
        item = self._repo.save_item(
            "attachment",
            {
                "name": name or file_name,
                "file_name": file_name,
                "mime_type": content_type or "application/octet-stream",
                "file_size": len(file_bytes),
                "data_base64": base64.b64encode(file_bytes).decode("ascii"),
                "tags": normalize_tags(tags),
                "enabled": True,
            },
        )
        return {"ok": True, "item": item}


class TestResolveMiniprogramThumbCommand:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, item_id: str) -> dict[str, Any]:
        item = self._repo.get_item("miniprogram", item_id)
        if not item:
            from aicrm_next.shared.errors import NotFoundError

            raise NotFoundError("miniprogram item not found")
        thumb_media_id = str(item.get("thumb_media_id") or "")
        if thumb_media_id:
            return {"ok": True, "thumb_media_id": thumb_media_id}
        thumb_image_id = item.get("thumb_image_id")
        if not thumb_image_id:
            return {"ok": False, "error": "thumb_image_id is required before resolving WeCom media"}
        image = self._repo.get_item("image", str(thumb_image_id), include_data=True)
        if not image or not image.get("data_base64"):
            return {"ok": False, "error": "thumb image data is unavailable"}
        result = build_wecom_media_adapter().upload_image(
            data_base64=str(image.get("data_base64") or ""),
            file_name=str(image.get("file_name") or "thumb.png"),
        )
        if not result.get("ok"):
            return {"ok": False, "error": result.get("error_message") or result.get("error_code") or "wecom media adapter unavailable"}
        thumb_media_id = str(result.get("media_id") or "")
        updated = self._repo.save_item("miniprogram", {"thumb_media_id": thumb_media_id}, item_id)
        return {"ok": True, "thumb_media_id": thumb_media_id, "item": updated, "adapter_result": result}


class ImportImageFromUrlCommand:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, payload: ImageFromUrlRequest) -> dict[str, Any]:
        name = payload.name or "外链图片样例"
        cloud_result = build_cloud_storage_adapter().put_remote_reference(
            source_url=payload.url,
            file_name="from-url.png",
            content_type="image/png",
        )
        wecom_result = build_wecom_media_adapter().resolve_media_id(
            reference_url=str(cloud_result.get("reference_url") or payload.url),
            file_name="from-url.png",
        )
        item = self._repo.save_item(
            "image",
            {
                "name": name,
                "file_name": "from-url.png",
                "content_type": "image/png",
                "file_size": 16,
                "width": 1,
                "height": 1,
                "data_url": "data:image/png;base64,ZmFrZQ==",
                "source_url": payload.url,
                "tags": payload.tags,
                "source_status": "fake_import",
                "storage_key": cloud_result.get("storage_key"),
                "public_url": cloud_result.get("public_url"),
                "wecom_media_id": wecom_result.get("media_id"),
                "side_effect_safety": _side_effect_safety(),
            },
        )
        return {"ok": True, "item": item, "source_status": "fake_import", "adapter_result": _media_adapter_summary(cloud_result, wecom_result)}


class ImportImageFromBase64Command:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, payload: ImageFromBase64Request) -> dict[str, Any]:
        content_type = _content_type_from_file_name(payload.file_name, "image/png")
        data_base64 = extract_base64_payload(payload.data_base64)
        cloud_result = build_cloud_storage_adapter().put_base64_object(
            data_base64=data_base64,
            file_name=payload.file_name,
            content_type=content_type,
        )
        wecom_result = build_wecom_media_adapter().upload_image(data_base64=data_base64, file_name=payload.file_name)
        item = self._repo.save_item(
            "image",
            {
                "name": payload.name or "Base64 图片样例",
                "file_name": payload.file_name,
                "content_type": content_type,
                "file_size": len(data_base64),
                "width": 1,
                "height": 1,
                "data_url": "data:image/png;base64," + data_base64,
                "tags": payload.tags,
                "source_status": "fake_import",
                "storage_key": cloud_result.get("storage_key"),
                "public_url": cloud_result.get("public_url"),
                "wecom_media_id": wecom_result.get("media_id"),
                "side_effect_safety": _side_effect_safety(),
            },
        )
        return {"ok": True, "item": item, "source_status": "fake_import", "adapter_result": _media_adapter_summary(cloud_result, wecom_result)}
