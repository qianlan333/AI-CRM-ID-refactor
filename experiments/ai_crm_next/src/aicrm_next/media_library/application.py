from __future__ import annotations

from typing import Any

from .dto import AttachmentUpsertRequest, ImageFromBase64Request, ImageFromUrlRequest, ImageUpsertRequest, MiniprogramUpsertRequest
from .repo import MediaLibraryRepository, build_media_library_repository


class ListMediaItemsQuery:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, *, limit: int = 100, offset: int = 0) -> dict[str, Any]:
        return {"ok": True, **self._repo.list_items(self._kind, limit=limit, offset=offset)}


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

    def __call__(self, item_id: str) -> dict[str, Any]:
        item = self._repo.get_item(self._kind, item_id)
        if not item:
            from aicrm_next.shared.errors import NotFoundError

            raise NotFoundError(f"{self._kind} item not found")
        return {"ok": True, "item": item}


class UpsertMediaItemCommand:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, payload: dict[str, Any] | ImageUpsertRequest | AttachmentUpsertRequest | MiniprogramUpsertRequest, item_id: str | None = None) -> dict[str, Any]:
        data = payload.model_dump() if hasattr(payload, "model_dump") else dict(payload)
        return {"ok": True, "item": self._repo.save_item(self._kind, data, item_id)}


class DeleteMediaItemCommand:
    def __init__(self, kind: str, repo: MediaLibraryRepository | None = None) -> None:
        self._kind = kind
        self._repo = repo or build_media_library_repository()

    def __call__(self, item_id: str) -> dict[str, Any]:
        return self._repo.delete_item(self._kind, item_id)


class ImportImageFromUrlCommand:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, payload: ImageFromUrlRequest) -> dict[str, Any]:
        name = payload.name or "外链图片样例"
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
            },
        )
        return {"ok": True, "item": item, "source_status": "fake_import"}


class ImportImageFromBase64Command:
    def __init__(self, repo: MediaLibraryRepository | None = None) -> None:
        self._repo = repo or build_media_library_repository()

    def __call__(self, payload: ImageFromBase64Request) -> dict[str, Any]:
        item = self._repo.save_item(
            "image",
            {
                "name": payload.name or "Base64 图片样例",
                "file_name": payload.file_name,
                "content_type": "image/png",
                "file_size": len(payload.data_base64),
                "width": 1,
                "height": 1,
                "data_url": "data:image/png;base64," + payload.data_base64,
                "tags": payload.tags,
                "source_status": "fake_import",
            },
        )
        return {"ok": True, "item": item, "source_status": "fake_import"}
