from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from aicrm_next.shared.errors import NotFoundError

from aicrm_next.commerce.domain import now_iso


class MediaLibraryRepository(Protocol):
    def list_items(self, kind: str, *, limit: int, offset: int) -> dict[str, Any]: ...
    def list_facets(self, kind: str) -> dict[str, list[str]]: ...
    def get_item(self, kind: str, item_id: str) -> dict[str, Any] | None: ...
    def save_item(self, kind: str, payload: dict[str, Any], item_id: str | None = None) -> dict[str, Any]: ...
    def delete_item(self, kind: str, item_id: str) -> dict[str, Any]: ...


def _seed() -> dict[str, list[dict[str, Any]]]:
    ts = "2026-05-20T12:00:00Z"
    return {
        "image": [
            {
                "id": "image_masked_001",
                "name": "商品封面图样例",
                "file_name": "image_masked_001.png",
                "content_type": "image/png",
                "file_size": 16,
                "width": 1,
                "height": 1,
                "data_url": "data:image/png;base64,ZmFrZQ==",
                "tags": ["commerce"],
                "created_at": ts,
                "updated_at": ts,
                "deleted": False,
            }
        ],
        "attachment": [
            {
                "id": "attachment_masked_001",
                "name": "附件样例",
                "file_name": "attachment_masked_001.pdf",
                "mime_type": "application/pdf",
                "file_size": 32,
                "data_base64": "ZmFrZQ==",
                "tags": ["fixture"],
                "enabled": True,
                "created_at": ts,
                "updated_at": ts,
                "deleted": False,
            }
        ],
        "miniprogram": [
            {
                "id": "miniprogram_masked_001",
                "title": "小程序卡片样例",
                "appid": "appid_masked_001",
                "page_path": "pages/masked/index",
                "thumb_image_id": "image_masked_001",
                "description": "脱敏小程序素材 fixture",
                "tags": ["fixture"],
                "enabled": True,
                "created_at": ts,
                "updated_at": ts,
                "deleted": False,
            }
        ],
    }


class InMemoryMediaLibraryRepository:
    def __init__(self, data: dict[str, list[dict[str, Any]]] | None = None) -> None:
        self._data = deepcopy(data if data is not None else _seed())

    def list_items(self, kind: str, *, limit: int, offset: int) -> dict[str, Any]:
        rows = [deepcopy(item) for item in self._data[kind] if not item.get("deleted")]
        return {"items": rows[offset : offset + limit], "total": len(rows), "limit": limit, "offset": offset}

    def list_facets(self, kind: str) -> dict[str, list[str]]:
        categories: set[str] = set()
        tags: set[str] = set()
        for item in self._data[kind]:
            if item.get("deleted"):
                continue
            category = item.get("category")
            if isinstance(category, str) and category:
                categories.add(category)
            for tag in item.get("tags") or []:
                if isinstance(tag, str) and tag:
                    tags.add(tag)
        return {"categories": sorted(categories), "tags": sorted(tags)}

    def get_item(self, kind: str, item_id: str) -> dict[str, Any] | None:
        for item in self._data[kind]:
            if item["id"] == item_id and not item.get("deleted"):
                return deepcopy(item)
        return None

    def save_item(self, kind: str, payload: dict[str, Any], item_id: str | None = None) -> dict[str, Any]:
        now = now_iso()
        if item_id:
            for index, item in enumerate(self._data[kind]):
                if item["id"] == item_id and not item.get("deleted"):
                    updated = {**item, **payload, "id": item_id, "updated_at": now}
                    self._data[kind][index] = updated
                    return deepcopy(updated)
            raise NotFoundError(f"{kind} item not found")
        item = {
            **payload,
            "id": f"{kind}_masked_{len(self._data[kind]) + 1:03d}",
            "created_at": now,
            "updated_at": now,
            "deleted": False,
        }
        self._data[kind].append(item)
        return deepcopy(item)

    def delete_item(self, kind: str, item_id: str) -> dict[str, Any]:
        for item in self._data[kind]:
            if item["id"] == item_id and not item.get("deleted"):
                item["deleted"] = True
                item["updated_at"] = now_iso()
                return {"ok": True, "deleted": True, "soft_deleted": True, "id": item_id}
        raise NotFoundError(f"{kind} item not found")


_GLOBAL_REPO = InMemoryMediaLibraryRepository()


def build_media_library_repository() -> MediaLibraryRepository:
    return _GLOBAL_REPO


def reset_media_library_fixture_state() -> None:
    global _GLOBAL_REPO
    _GLOBAL_REPO = InMemoryMediaLibraryRepository()
